"""The task interface that every hardened task implements.

A hardened task is a program-writing task: the solver ships one program, and the program is run on hidden
cases it has never seen. The author supplies five things, all in code:

* a seeded case generator (raw, realistic inputs plus the hidden truth used only for checks),
* a reference solver and, ideally, an independent second-opinion solver,
* a grader that returns named checks with explicit tolerances,
* executable versions of every factual statement made in the instruction ("claims"),
* controls: wrong solvers that must fail (negatives) and valid alternative solvers that must pass (fairness).

Scoring is all-or-nothing, as in terminal-agent benchmarks: an answer scores 1 only if every check passes on
every hidden case.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Callable

Solver = Callable[[dict], dict]          # inputs -> answer (JSON-serialisable)


@dataclass
class Check:
    """One graded quantity on one case."""
    name: str
    ok: bool
    value: Any = None        # the solver's value
    expected: Any = None     # the reference value
    tolerance: Any = None    # the bar that was applied
    detail: str = ""


@dataclass
class Case:
    """One generated case: what the solver sees, and the truth that only the checks may use."""
    seed: int
    inputs: dict
    truth: dict = field(default_factory=dict)

    def digest(self) -> str:
        """SHA-256 of the canonical JSON of the inputs; used for the determinism check and the manifest."""
        blob = json.dumps(self.inputs, sort_keys=True, separators=(",", ":"), default=_jsonable).encode()
        return hashlib.sha256(blob).hexdigest()


@dataclass
class Claim:
    """A factual statement from the instruction, written as a predicate over a case and its reference."""
    text: str
    holds: Callable[[Case, dict], bool]


class HardTask:
    """Subclass this. Only `make_case`, `reference` and `grade` are required."""

    name: str = "unnamed-task"
    instruction: str = ""

    # --- required -------------------------------------------------------------------------------------
    def make_case(self, seed: int) -> Case:
        raise NotImplementedError

    def reference(self, inputs: dict) -> dict:
        raise NotImplementedError

    def grade(self, case: Case, answer: dict, reference: dict) -> list[Check]:
        raise NotImplementedError

    # --- strongly recommended ------------------------------------------------------------------------
    def second_opinion(self, inputs: dict) -> dict | None:
        """An independently written solver (different algorithm or library). None if there is none."""
        return None

    def claims(self) -> list[Claim]:
        """Every factual statement the instruction makes about the data, as an executable predicate."""
        return []

    def negatives(self) -> dict[str, Solver]:
        """Solvers that each make one plausible mistake (one trap each). Every one must score 0."""
        return {}

    def fairness(self) -> dict[str, Solver]:
        """Valid alternative methods the instruction allows. Every one must score 1."""
        return {}

    def public_examples(self) -> list[Case]:
        """Worked examples shipped to the solver. They must not be among the hidden cases."""
        return []

    # --- scoring ---------------------------------------------------------------------------------------
    def score(self, solver: Solver, cases: list[Case], references: list[dict]) -> "Score":
        per_case = []
        for case, ref in zip(cases, references):
            try:
                answer = solver(case.inputs)
                checks = self.grade(case, answer, ref)
            except Exception as exc:  # a crash fails the case, it does not stop the gate run
                checks = [Check("runs", False, detail=f"{type(exc).__name__}: {exc}")]
            per_case.append(checks)
        return Score(per_case)


@dataclass
class Score:
    per_case: list[list[Check]]

    @property
    def cases_passed(self) -> int:
        return sum(all(c.ok for c in checks) for checks in self.per_case)

    @property
    def value(self) -> int:
        """All-or-nothing task score."""
        return int(self.cases_passed == len(self.per_case))

    def failures(self) -> list[tuple[int, Check]]:
        return [(i, c) for i, checks in enumerate(self.per_case) for c in checks if not c.ok]


def _jsonable(x):
    try:
        import numpy as np
        if isinstance(x, np.ndarray):
            return x.tolist()
        if isinstance(x, np.generic):
            return x.item()
    except ImportError:
        pass
    raise TypeError(f"not JSON-serialisable: {type(x)}")
