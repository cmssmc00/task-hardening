"""Candidate negative controls by single-token mutation of the reference solver.

Hand-written negatives encode the traps you planted on purpose. Mutations find the ones you did not think of:
each mutant changes one operator, comparison, constant or function name in the reference. A mutant is a
useful negative when it still runs on every hidden case (a crash is too easy to spot) and fails at least one
of them; it is a *subtle* one when it also reproduces the public examples. A mutant that passes every hidden
case shows a part of the reference the grader does not constrain: either the bar is loose there or that code
does not matter.
"""
from __future__ import annotations

import ast
import types
from dataclasses import dataclass

from .task import Case, HardTask

BINOP_SWAP = {ast.Add: ast.Sub, ast.Sub: ast.Add, ast.Mult: ast.Div, ast.Div: ast.Mult}
CMP_SWAP = {ast.Lt: ast.LtE, ast.LtE: ast.Lt, ast.Gt: ast.GtE, ast.GtE: ast.Gt}
NAME_SWAP = {"log": "log10", "log10": "log", "max": "min", "min": "max", "argmin": "argmax",
             "argmax": "argmin", "mean": "median", "median": "mean", "sum": "mean"}


@dataclass
class Mutation:
    index: int
    kind: str
    line: int
    description: str


class _Mutator(ast.NodeTransformer):
    """Applies the k-th applicable edit (k = target) and records every applicable edit when target is None."""

    def __init__(self, target: int | None):
        self.target, self.count, self.found = target, 0, []

    def _hit(self, node, kind, desc) -> bool:
        idx = self.count
        self.count += 1
        if self.target is None:
            self.found.append(Mutation(idx, kind, getattr(node, "lineno", 0), desc))
            return False
        return idx == self.target

    def visit_BinOp(self, node):
        self.generic_visit(node)
        if type(node.op) in BINOP_SWAP and self._hit(node, "operator", f"{type(node.op).__name__} -> "
                                                       f"{BINOP_SWAP[type(node.op)].__name__}"):
            node.op = BINOP_SWAP[type(node.op)]()
        return node

    def visit_Compare(self, node):
        self.generic_visit(node)
        if len(node.ops) == 1 and type(node.ops[0]) in CMP_SWAP and self._hit(
                node, "comparison", f"{type(node.ops[0]).__name__} -> {CMP_SWAP[type(node.ops[0])].__name__}"):
            node.ops = [CMP_SWAP[type(node.ops[0])]()]
        return node

    def visit_Constant(self, node):
        if isinstance(node.value, (int, float)) and not isinstance(node.value, bool) and node.value not in (0, 1):
            new = node.value * 1.1 if isinstance(node.value, float) else node.value + 1
            if self._hit(node, "constant", f"{node.value!r} -> {new!r}"):
                return ast.copy_location(ast.Constant(new), node)
        return node

    def visit_Attribute(self, node):
        self.generic_visit(node)
        if node.attr in NAME_SWAP and self._hit(node, "function", f".{node.attr} -> .{NAME_SWAP[node.attr]}"):
            node.attr = NAME_SWAP[node.attr]
        return node


def candidates(source: str) -> list[Mutation]:
    m = _Mutator(None)
    m.visit(ast.parse(source))
    return m.found


def build(source: str, index: int, func_name: str, namespace: dict | None = None):
    """Compile the source with mutation `index` applied and return the function `func_name`."""
    tree = _Mutator(index).visit(ast.parse(source))
    ast.fix_missing_locations(tree)
    mod = types.ModuleType("mutant")
    mod.__dict__.update(namespace or {})
    exec(compile(tree, "<mutant>", "exec"), mod.__dict__)
    return getattr(mod, func_name)


def screen(task: HardTask, source: str, func_name: str, seeds: list[int], namespace: dict | None = None,
           limit: int | None = None) -> list[dict]:
    """Score every mutant of `func_name` (defined in `source`) on the hidden cases and public examples."""
    cases = [task.make_case(s) for s in seeds]
    refs = [task.reference(c.inputs) for c in cases]
    examples: list[Case] = task.public_examples()
    ex_refs = [task.reference(c.inputs) for c in examples]
    out = []
    for mut in candidates(source)[:limit]:
        try:
            fn = build(source, mut.index, func_name, namespace)
        except Exception as exc:
            out.append({"mutation": mut, "status": f"does not compile: {exc}"})
            continue
        s = task.score(fn, cases, refs)
        crashed = any(c.name == "runs" for _, c in s.failures())
        ex = task.score(fn, examples, ex_refs) if examples else None
        if crashed:
            status = "crashes (too easy to find)"
        elif s.value == 1:
            status = "passes every hidden case (unconstrained code or loose bar)"
        elif ex is not None and ex.value == 1:
            status = "subtle negative (fails hidden, passes examples)"
        else:
            status = "negative"
        out.append({"mutation": mut, "status": status, "hidden_failed": len(cases) - s.cases_passed})
    return out
