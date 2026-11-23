"""Fast tests on a tiny task (standard library only). Run: python -m pytest -q  (or python tests/test_hardening.py)"""
import csv
import json
import random
import statistics
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hardening import Case, Check, Claim, HardTask, freeze, run_gates, verify   # noqa: E402
from hardening import mutate, review, screen                                     # noqa: E402

SRC = '''
def solve(inputs):
    xs = sorted(inputs["readings"])
    keep = [x for x in xs if abs(x - xs[len(xs) // 2]) < 5 * inputs["noise"]]
    return {"level": sum(keep) / len(keep) - inputs["offset"]}
'''
NS: dict = {}
exec(SRC, NS)
solve = NS["solve"]


class Level(HardTask):
    """Mean level of noisy readings with a few spikes and a stated instrument offset."""
    name = "toy-level"

    def make_case(self, seed):
        rng = random.Random(seed)
        level, noise, offset = rng.uniform(10, 20), rng.uniform(0.1, 0.3), rng.uniform(1, 2)
        xs = [level + offset + rng.gauss(0, noise) for _ in range(200)]
        for i in rng.sample(range(200), 6):
            xs[i] += rng.choice([-1, 1]) * rng.uniform(30, 60)          # spikes
        return Case(seed, {"readings": xs, "noise": noise, "offset": offset}, {"level": level})

    def truth_answer(self, case):
        return dict(case.truth)

    def reference(self, inputs):
        return solve(inputs)

    def second_opinion(self, inputs):
        xs = [x for x in inputs["readings"] if abs(x - statistics.median(inputs["readings"])) < 4 * inputs["noise"]]
        return {"level": statistics.fmean(xs) - inputs["offset"]}

    def grade(self, case, answer, ref):
        v = answer.get("level", float("nan"))
        return [Check("level", abs(v - ref["level"]) <= 0.05, v, ref["level"], 0.05)]

    def claims(self):
        return [Claim("noise below 0.3", lambda c, r: c.inputs["noise"] <= 0.3)]

    def negatives(self):
        return {"plain mean (keeps spikes)": lambda x: {"level": statistics.fmean(x["readings"]) - x["offset"]},
                "offset ignored": lambda x: {"level": solve(x)["level"] + x["offset"]}}

    def fairness(self):
        return {"median": lambda x: {"level": statistics.median(x["readings"]) - x["offset"]}}

    def public_examples(self):
        return [self.make_case(s) for s in (900, 901)]


SEEDS = list(range(1, 9))


def test_gates_pass():
    rep = run_gates(Level(), SEEDS)
    assert rep.ok, rep.to_text()
    assert rep.negatives == {"plain mean (keeps spikes)": 8, "offset ignored": 8}


def test_gates_catch_a_bad_negative():
    class Weak(Level):
        def negatives(self):
            return {"actually fine": lambda x: solve(x)}
    rep = run_gates(Weak(), SEEDS)
    assert not rep.ok and any("actually fine" in g.name and not g.ok for g in rep.gates)


def test_freeze_and_verify():
    with tempfile.TemporaryDirectory() as d:
        out = freeze(Level(), SEEDS, d)
        assert verify(out) == []
        p = out / "ref" / "case_00.json"
        p.write_text(p.read_text().replace("1", "2", 1))
        assert verify(out) == ["ref/case_00.json"]


def test_mutants():
    res = mutate.screen(Level(), SRC, "solve", SEEDS)
    kinds = {r["status"] for r in res}
    assert any(s.startswith("negative") or s.startswith("subtle") for s in kinds)


def test_review_labels():
    ref = review.flatten({"a": 1.0, "b": [2.0, 3.0]})
    neg = review.flatten({"a": 1.5, "b": [2.0, 3.0]})
    assert review.review(neg, ref, {"one": neg}).label == "matches negative: one"
    assert review.review(ref, ref, {"one": neg}).label.startswith("own answer")


def test_screen_classes(tmp_path=None):
    rows = [{"task": "a", "reward": 1, "tests_passed": 3, "tests_total": 3}] * 2 + \
           [{"task": "b", "reward": 0, "tests_passed": 2, "tests_total": 3},
            {"task": "b", "reward": 0, "tests_passed": 0, "tests_total": 3},
            {"task": "c", "reward": 0, "tests_passed": 0, "tests_total": 3},
            {"task": "c", "reward": 1, "tests_passed": 3, "tests_total": 3},
            {"task": "d", "reward": 0, "tests_passed": 0, "tests_total": 3},
            {"task": "d", "reward": 0, "tests_passed": 1, "tests_total": 3}]
    assert screen.classify(rows) == {"a": "too easy", "b": "near miss", "c": "passed once", "d": "hard"}


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
