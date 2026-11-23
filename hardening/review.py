"""Failure review: is a failed attempt a trap the task meant to set, or a defect of the task?

When a solver fails, compare its output value by value with the reference output and with the output of every
negative control (each negative is one known mistake). Three outcomes:

* matches a negative   - the solver made that mistake: the trap worked as designed;
* closer to a negative - probably that mistake, combined with others;
* its own answer       - read the trajectory: a method error, a near miss, or a task defect
                         (unstated constant, unrealistic data, a bar tighter than the method spread).

Works on JSON and CSV outputs. Usage from the shell:

    python -m hardening.review --answer out/ --reference ref/ --negative no_deadtime=neg1/ --negative ...
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import math
import statistics
from dataclasses import dataclass
from pathlib import Path

MATCH = 0.005           # mean relative distance that counts as "the same answer"


def flatten(obj, prefix: str = "") -> dict:
    out = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.update(flatten(v, f"{prefix}/{k}"))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out.update(flatten(v, f"{prefix}[{i}]"))
    else:
        out[prefix] = obj
    return out


def _csv_leaves(text: str) -> dict:
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        return {}
    head, body = rows[0], [r for r in rows[1:] if r]
    keys = [r[0] for r in body]
    use_key = len(set(keys)) == len(keys)
    out = {}
    for i, r in enumerate(body):
        rk = r[0] if use_key else str(i)
        for col, v in zip(head, r):
            try:
                v = float(v)
            except ValueError:
                v = v.strip()
            out[f"/{rk}/{col}"] = v
    return out


def load(path: str | Path) -> dict:
    """Leaves of every .json / .csv file under a directory (or of a single file), keyed by file and path."""
    p = Path(path)
    files = [p] if p.is_file() else sorted(q for q in p.rglob("*") if q.suffix in (".json", ".csv"))
    out = {}
    for f in files:
        rel = f.name if p.is_file() else f.relative_to(p).as_posix()
        text = f.read_text()
        leaves = flatten(json.loads(text)) if f.suffix == ".json" else _csv_leaves(text)
        out.update({rel + k: v for k, v in leaves.items()})
    return out


def distance(a, b) -> float:
    """Relative distance, capped at 10; 0/1 for non-numeric values."""
    num = (int, float)
    if isinstance(a, bool) or isinstance(b, bool) or not isinstance(a, num) or not isinstance(b, num):
        return 0.0 if a == b else 1.0
    if not (math.isfinite(a) and math.isfinite(b)):
        return 0.0 if a == b else 1.0
    if a == b:
        return 0.0
    return min(abs(a - b) / max(abs(b), 1e-12), 10.0)


@dataclass
class Verdict:
    label: str
    nearest: str
    distances: dict          # variant -> mean relative distance over the compared values
    differing: dict          # key -> (answer, reference) for values that differ from the reference


def review(answer: dict, reference: dict, negatives: dict[str, dict], keys: list[str] | None = None) -> Verdict:
    """All arguments are flattened outputs (see `load`). `keys` restricts the comparison, e.g. to the values
    the grader reported as failing."""
    variants = {"reference": reference, **negatives}
    dists = {}
    for name, var in variants.items():
        common = [k for k in var if k in answer and (keys is None or k in keys)]
        dists[name] = statistics.fmean(distance(answer[k], var[k]) for k in common) if common else math.inf
    nearest = min(dists, key=dists.get)
    ref_d = dists["reference"]
    if nearest == "reference" or math.isinf(dists[nearest]):
        label = "own answer (closest to the reference)" if nearest == "reference" else "no comparable output"
    elif dists[nearest] <= MATCH and ref_d > 3 * dists[nearest] + 0.002:
        label = f"matches negative: {nearest}"
    elif dists[nearest] < 0.5 * ref_d:
        label = f"closer to negative: {nearest}"
    else:
        label = "own answer (no negative is close)"
    differing = {k: (answer[k], reference[k]) for k in reference
                 if k in answer and distance(answer[k], reference[k]) > 0 and (keys is None or k in keys)}
    return Verdict(label, nearest, dists, differing)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--answer", required=True, help="the failed attempt's output file or directory")
    ap.add_argument("--reference", required=True, help="the reference solver's output")
    ap.add_argument("--negative", action="append", default=[], metavar="NAME=PATH",
                    help="a negative control's output (repeat for each)")
    a = ap.parse_args(argv)
    negs = {n: load(p) for n, p in (x.split("=", 1) for x in a.negative)}
    v = review(load(a.answer), load(a.reference), negs)
    print(v.label)
    for name, d in sorted(v.distances.items(), key=lambda kv: kv[1]):
        print(f"  {name:<32} mean relative distance {d:.4g}")
    for k, (got, ref) in list(v.differing.items())[:12]:
        print(f"  {k}: answer {got!r}, reference {ref!r}")


if __name__ == "__main__":
    main()
