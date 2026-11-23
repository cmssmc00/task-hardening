"""Run the gates on the example task, freeze its hidden cases, screen mutants of the reference solver and
review a simulated failed attempt.

    python examples/deadtime_decay/run_gates.py
"""
import inspect
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))       # the repository root, for `hardening`
sys.path.insert(0, str(Path(__file__).resolve().parent))

import task as example                                               # noqa: E402
from hardening import freeze, run_gates, verify                     # noqa: E402
from hardening import mutate, review                                 # noqa: E402

HIDDEN_SEEDS = list(range(101, 109))

if __name__ == "__main__":
    report = run_gates(example.TASK, HIDDEN_SEEDS)
    print(report.to_text())

    with tempfile.TemporaryDirectory() as d:
        out = freeze(example.TASK, HIDDEN_SEEDS, Path(d) / "tests")
        print(f"\nfrozen {len(HIDDEN_SEEDS)} hidden cases; manifest intact: {verify(out) == []}")

    print("\nmutants of the reference solver (first 40):")
    src = inspect.getsource(example.solve)
    for r in mutate.screen(example.TASK, src, "solve", HIDDEN_SEEDS, namespace=vars(example), limit=40):
        m = r["mutation"]
        print(f"  line {m.line:>2} {m.kind:<10} {m.description:<22} {r['status']}")
    print("\nreview of a simulated failed attempt (it used only the first blank):")
    case = example.TASK.make_case(HIDDEN_SEEDS[0])
    attempt = review.flatten(example.solve(case.inputs, background="first"))
    negs = {n: review.flatten(f(case.inputs)) for n, f in example.TASK.negatives().items()}
    verdict = review.review(attempt, review.flatten(example.TASK.reference(case.inputs)), negs)
    print(f"  {verdict.label}")
    sys.exit(0 if report.ok else 1)
