"""Automatic gates: everything a hardened task must pass before any model sees it.

The gates use no model. They answer five questions:

1. Is the task well defined?      determinism, distinct hidden cases, examples kept out of the hidden set
2. Is the reference right?        reference against the generator's truth, second-opinion solver, claims
3. Is the bar fair?               tolerance margins (reference error vs. tolerance), fairness controls pass
4. Do the traps bite?             every negative control scores 0, and by how many cases
5. Can it be gamed?               no-op, replay-an-example and nearest-example probes all score 0
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field

from .task import Case, Check, HardTask, Score

TIGHT_MARGIN = 0.5      # reference error above half the tolerance: the bar is too tight (want >= 2x headroom)
WEAK_NEGATIVE = 2       # a negative that fails fewer hidden cases than this is a fragile trap


@dataclass
class Gate:
    name: str
    ok: bool
    detail: str = ""
    warn: bool = False


@dataclass
class GateReport:
    task: str
    gates: list[Gate] = field(default_factory=list)
    margins: dict[str, float] = field(default_factory=dict)        # check name -> worst |ref-truth|/tol
    negatives: dict[str, int] = field(default_factory=dict)        # negative -> hidden cases it fails

    @property
    def ok(self) -> bool:
        return all(g.ok for g in self.gates)

    def add(self, name: str, ok: bool, detail: str = "", warn: bool = False) -> None:
        self.gates.append(Gate(name, ok, detail, warn))

    def to_text(self) -> str:
        lines = [f"gates for {self.task}: {'PASS' if self.ok else 'FAIL'}"]
        for g in self.gates:
            mark = "ok  " if g.ok and not g.warn else ("WARN" if g.ok else "FAIL")
            lines.append(f"  [{mark}] {g.name}" + (f": {g.detail}" if g.detail else ""))
        if self.margins:
            lines.append("  tolerance use by the reference (worst case, 1.0 = at the bar):")
            for k, v in sorted(self.margins.items()):
                lines.append(f"    {k:<28} {v:5.2f}" + ("   <- tight" if v > TIGHT_MARGIN else ""))
        return "\n".join(lines)

    def to_json(self) -> str:
        return json.dumps({"task": self.task, "ok": self.ok, "gates": [g.__dict__ for g in self.gates],
                           "margins": self.margins, "negatives": self.negatives}, indent=1)


def _ratio(check: Check) -> float | None:
    """|value - expected| / tolerance for numeric checks with a numeric tolerance."""
    try:
        v, e, t = float(check.value), float(check.expected), float(check.tolerance)
    except (TypeError, ValueError):
        return None
    if not (math.isfinite(v) and math.isfinite(e)) or t <= 0:
        return None
    return abs(v - e) / t


def run_gates(task: HardTask, seeds: list[int]) -> GateReport:
    rep = GateReport(task.name)
    cases = [task.make_case(s) for s in seeds]
    refs = [task.reference(c.inputs) for c in cases]

    # 1. well defined ---------------------------------------------------------------------------------
    again = [task.make_case(s).digest() for s in seeds]
    digests = [c.digest() for c in cases]
    rep.add("determinism (same seed, same case)", again == digests)
    rep.add("hidden cases are distinct", len(set(digests)) == len(digests))
    examples = task.public_examples()
    ex_digests = {c.digest() for c in examples}
    rep.add("public examples are not hidden cases", not (ex_digests & set(digests)),
            f"{len(examples)} examples")
    canon = [json.dumps(r, sort_keys=True, default=str) for r in refs]
    rep.add("reference answers differ across cases", len(set(canon)) == len(canon))

    # 2. reference is right ---------------------------------------------------------------------------
    if hasattr(task, "truth_answer"):
        worst: dict[str, float] = {}
        bad = 0
        for case, ref in zip(cases, refs):
            checks = task.grade(case, ref, task.truth_answer(case))
            bad += not all(c.ok for c in checks)
            for c in checks:
                r = _ratio(c)
                if r is not None:
                    worst[c.name] = max(worst.get(c.name, 0.0), r)
        rep.margins = worst
        rep.add("reference recovers the generator's truth", bad == 0, f"{len(cases) - bad}/{len(cases)} cases")
        tight = [k for k, v in worst.items() if v > TIGHT_MARGIN]
        rep.add("tolerances leave >= 2x headroom over the reference error", True,
                ("tight: " + ", ".join(sorted(tight))) if tight else "", warn=bool(tight))
    so = task.second_opinion(cases[0].inputs) if cases else None
    if so is not None:
        s = task.score(task.second_opinion, cases, refs)
        rep.add("second-opinion solver agrees with the reference", s.value == 1,
                f"{s.cases_passed}/{len(cases)} cases")
    for claim in task.claims():
        held = sum(bool(claim.holds(c, r)) for c, r in zip(cases, refs))
        held_ex = sum(bool(claim.holds(c, task.reference(c.inputs))) for c in examples)
        rep.add(f"claim holds: {claim.text}", held == len(cases) and held_ex == len(examples),
                f"{held}/{len(cases)} hidden, {held_ex}/{len(examples)} examples")

    # 3. fair bar ------------------------------------------------------------------------------------------
    for name, solver in task.fairness().items():
        s = task.score(solver, cases, refs)
        rep.add(f"fairness control passes: {name}", s.value == 1, f"{s.cases_passed}/{len(cases)} cases")

    # 4. traps bite ----------------------------------------------------------------------------------------
    for name, solver in task.negatives().items():
        s = task.score(solver, cases, refs)
        failed = len(cases) - s.cases_passed
        rep.negatives[name] = failed
        rep.add(f"negative control fails: {name}", s.value == 0, f"fails {failed}/{len(cases)} cases",
                warn=0 < failed < WEAK_NEGATIVE)
    if not task.negatives():
        rep.add("at least one negative control per trap", False, "no negatives declared")

    # 5. cannot be gamed --------------------------------------------------------------------------------
    for name, solver in _probes(task, examples).items():
        s = task.score(solver, cases, refs)
        rep.add(f"probe scores 0: {name}", s.value == 0, f"passes {s.cases_passed}/{len(cases)} cases")
    return rep


# ---- lazy-solver probes -------------------------------------------------------------------------------------
def _flat_numbers(x) -> list[float]:
    if isinstance(x, dict):
        return [v for k in sorted(x) for v in _flat_numbers(x[k])]
    if isinstance(x, (list, tuple)):
        return [v for e in x for v in _flat_numbers(e)]
    if isinstance(x, (int, float)) and not isinstance(x, bool):
        return [float(x)]
    try:  # numpy arrays and scalars
        return [float(v) for v in x.ravel()]  # type: ignore[attr-defined]
    except AttributeError:
        return []


def _probes(task: HardTask, examples: list[Case]):
    probes = {"no-op (empty answer)": lambda inputs: {}}
    if examples:
        answers = [task.reference(c.inputs) for c in examples]
        probes["replay the first public example"] = lambda inputs, a=answers[0]: a
        fps = [_flat_numbers(c.inputs)[:64] for c in examples]

        def nearest(inputs, fps=fps, answers=answers):
            fp = _flat_numbers(inputs)[:64]
            d = [sum((a - b) ** 2 for a, b in zip(fp, f)) for f in fps]
            return answers[d.index(min(d))]
        probes["copy the nearest public example"] = nearest
    return probes
