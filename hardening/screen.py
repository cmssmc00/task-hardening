"""Difficulty screen: classify tasks from k model attempts each.

Run a cheap stand-in model k times (k = 2 is enough to drop the easy ones), then classify:

* too easy     every attempt passed                      -> drop or harden further
* passed once  some attempts passed                      -> keep for later, run the target model
* near miss    no pass, but one attempt passed >= half the tests  -> review the trajectories first
* hard         no pass, few tests passed                 -> review, then run the target model

A fail by a weaker stand-in is weak evidence: the target model must still fail before a task counts as hard.
Input is a CSV with columns task, attempt, reward, tests_passed, tests_total (one row per attempt):

    python -m hardening.screen attempts.csv
"""
from __future__ import annotations

import argparse
import csv
from collections import defaultdict


def classify(rows: list[dict], near: float = 0.5) -> dict[str, str]:
    by = defaultdict(list)
    for r in rows:
        by[r["task"]].append(r)
    out = {}
    for task, rs in by.items():
        passes = sum(float(r["reward"]) >= 1 for r in rs)
        best = max((int(r["tests_passed"]) / max(int(r["tests_total"]), 1)) for r in rs)
        if passes == len(rs):
            out[task] = "too easy"
        elif passes:
            out[task] = "passed once"
        elif best >= near:
            out[task] = "near miss"
        else:
            out[task] = "hard"
    return out


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="classify tasks from k attempts each")
    ap.add_argument("attempts_csv")
    a = ap.parse_args(argv)
    rows = list(csv.DictReader(open(a.attempts_csv)))
    res = classify(rows)
    counts = defaultdict(int)
    for task in sorted(res):
        print(f"{res[task]:<12} {task}")
        counts[res[task]] += 1
    print("\n" + ", ".join(f"{k}: {v}" for k, v in sorted(counts.items())))


if __name__ == "__main__":
    main()
