# task-hardening

Make program-writing tasks for terminal agents harder without making them unfair.

A task is *hardened* when a solver that takes the obvious shortcut fails it, while a solver that does the work
correctly, by any valid method, passes. This repository holds the recipe and the checks:

- **a task interface** (`hardening/task.py`): seeded case generator, reference solver, grader with explicit
  tolerances, executable instruction claims, negative and fairness controls;
- **automatic gates** (`hardening/gates.py`): determinism, reference vs. truth, second opinion, claims,
  tolerance headroom, controls, and lazy-solver probes; no model needed;
- **frozen references** (`hardening/freeze.py`): hidden cases and references with a SHA-256 manifest;
- **mutation negatives** (`hardening/mutate.py`): single-token mutants of the reference, to find traps you did
  not plan and code the grader does not constrain;
- **failure review** (`hardening/review.py`): is a failed attempt one of the planted mistakes, or its own answer?
- **difficulty screen** (`hardening/screen.py`): classify tasks from k attempts of a stand-in model.

The method is described step by step in [docs/RECIPE.md](docs/RECIPE.md).

## Quick start

```bash
python -m pytest -q                                   # fast tests, standard library only
pip install numpy
python examples/deadtime_decay/run_gates.py          # gates, freezing, mutants and a review on the example
```

The example ([examples/deadtime_decay](examples/deadtime_decay)) is an invented counting experiment: lifetimes
from pulsed, binned counts with detector dead time, a background that drifts between two blank runs, and a choice
between one and two decay components by a stated BIC rule. Its gate report:

```
gates for deadtime-decay: PASS
  [ok  ] reference recovers the generator's truth: 8/8 cases
  [ok  ] second-opinion solver agrees with the reference: 8/8 cases
  [ok  ] fairness control passes: Nelder-Mead instead of a grid: 8/8 cases
  [ok  ] negative control fails: no dead-time correction: fails 8/8 cases
  [ok  ] negative control fails: background from the first blank only: fails 8/8 cases
  [ok  ] negative control fails: always two components: fails 5/8 cases
  [ok  ] probe scores 0: copy the nearest public example: passes 0/8 cases
  ...
```

## Writing your own task

```python
from hardening import Case, Check, Claim, HardTask, run_gates

class MyTask(HardTask):
    name = "my-task"
    def make_case(self, seed): ...            # raw inputs + hidden truth
    def truth_answer(self, case): ...         # the answer implied by the truth (enables the headroom gate)
    def reference(self, inputs): ...
    def second_opinion(self, inputs): ...     # an independent solver
    def grade(self, case, answer, ref): ...   # -> [Check(name, ok, value, expected, tolerance)]
    def claims(self): ...                     # -> [Claim("text from the instruction", predicate)]
    def negatives(self): ...                  # one wrong solver per trap; each must score 0
    def fairness(self): ...                   # valid alternatives; each must score 1
    def public_examples(self): ...

print(run_gates(MyTask(), seeds=list(range(1, 9))).to_text())
```

Packaging a task for a particular runner (Harbor / Terminal-Bench layout, Docker image, test script) is left to
that runner; `freeze` produces the hidden cases and references such a test script reads.

## Related

[verifiable-task-synthesis-notes](https://github.com/cmssmc00/verifiable-task-synthesis-notes): design notes on
generating and checking verifiable terminal tasks, including the grading and failure-attribution ideas used here.

## What is not here

No tasks other than the invented example, no hidden cases or references of real tasks, and no model run data.

## License

MIT
