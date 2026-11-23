# Example: lifetimes from a pulsed counting run (invented)

- `task.py`: the task: instruction text, seeded generator, reference and second-opinion solvers, grader,
  instruction claims, three negative controls (one per trap) and two fairness controls.
- `run_gates.py`: runs every gate, freezes the hidden cases, screens mutants of the reference solver and
  reviews a simulated failed attempt.

```bash
pip install numpy
python examples/deadtime_decay/run_gates.py
```

The traps, and what in the data gives each away:

| Trap | Evidence in the data | Negative control |
|---|---|---|
| detector dead time | early bins are suppressed: the corrected curve is steeper than the raw one | `no dead-time correction` |
| drifting background | the two blank runs disagree by 30-70 % | `background from the first blank only` |
| over-fitting | the stated BIC rule rejects the second component | `always two components` |
