# The hardening recipe

How to turn an easy, well-specified computing task into a hard one that is still fair, and how to check that
it worked. Each step names the code in this repository that checks it.

## 1. Make the task harder

**Start from raw data.** Hand the solver what an instrument or a logger actually produces: binned counts, raw
traces, vendor exports, field sheets with their notes. Most real difficulty lives in getting from raw data to the
quantity of interest, not in the final formula.

**Remove the recipe, keep the conventions.** State every convention the answer depends on (units, sign and time
conventions, which model, which selection rule, which reporting rule). Do not state the method. A solver that
knows the field can find the method; a solver that has to guess a convention cannot be graded fairly.

**Plant traps that the data reveal.** Each trap is a plausible shortcut that gives a wrong answer, and the data
must contain the evidence that the shortcut is wrong: a detector dead time that suppresses the early bins, a
background that drifts between two blanks, a calibration standard measured at another temperature, a logger
clock that drifts against the reference clock. Aim for at least three per task. A trap that nothing in the data reveals is not a trap; it is
an unstated convention.

**Add a choice step.** Make the solver decide something by a stated rule: the number of components, the model
class, which runs to exclude. Choice steps punish solvers that fit one model and stop.

**Grade a program on hidden cases.** The solver ships a program; it runs on several hidden cases that differ in
the regime (weak signals, boundary optima, missing data, aliasing). Visible examples are allowed but must not be
among the hidden cases.

**Set tolerances from the reference error, not from taste.** Run the reference on many seeds, measure its error
against the generator's truth, and set each bar at 2-3x that error, then check that every negative control
lands outside it.

## 2. Check that it is still fair (no model needed)

`hardening.gates.run_gates` runs all of these on a task:

| Gate | Why |
|---|---|
| Determinism; distinct hidden cases; examples not hidden | the task is well defined |
| Reference recovers the generator's truth | the reference is right |
| Second-opinion solver agrees | the reference is not right by accident |
| Every instruction claim holds on every case | the instruction does not lie |
| Tolerance headroom (reference error / bar <= 0.5) | the bar is not tighter than the method spread |
| Fairness controls score 1 | valid alternative methods are not punished |
| Negative controls score 0, and on how many cases | each trap bites, and not by luck on one case |
| No-op, replay-an-example, copy-the-nearest-example probes score 0 | the task cannot be gamed |

`hardening.mutate` finds negatives you did not plan: single-token mutants of the reference that still run.
A mutant that passes every hidden case marks code the grader does not constrain. In the example, the Poisson
weights are such a place: changing them barely moves the answer, so they are not a trap and should not be sold
as one.

`hardening.freeze` writes the hidden cases and references with a SHA-256 manifest. Grade against the frozen
references; never recompute them at test time.

## 3. Check that it is hard (models)

**Screen with a cheap stand-in model first**, k = 2 attempts per task (`hardening.screen`). Drop the tasks it
passes twice. A fail by a weaker stand-in is weak evidence, so the target model must still fail before a task
counts as hard.

**Review every failure before trusting it** (`hardening.review`). Compare the failed attempt's output with the
reference and with each negative control's output:

- *matches a negative*: the solver fell into that trap. The task works as designed.
- *closer to a negative*: probably that trap plus something else.
- *own answer*: read the trajectory. It is a method error, a near miss, or a task defect.

Task defects found this way, and what to do about them:

| Defect | Sign in the trajectory | Fix |
|---|---|---|
| Unrealistic data | the solver says the data look truncated, impossible or inconsistent | make the generator physical: instrument response times, capacity limits, conservation |
| Unstated constant | every result is off by the same factor; both attempts identical | state the constant in the notes; the task should test the data, not recall |
| Bar too tight | the solver's answer moves by more than the tolerance with an analysis choice | widen the bar or add data; recheck the headroom gate |
| Format | a misspelt key, a missing file | make the output contract explicit and validate it in the grader |

A good hard task fails solvers for the reasons you planted. If most failures are *own answer* with defects,
fix the task before counting it.

## 4. Watch for shallow tasks

A task can be hard and still shallow: a strong model writes the whole program in one or two commands without
looking at any output. To measure this, state a turn cap in the instruction and enforce it as the step limit,
for caps 1, 2, 3, 5, 10, 20, 40, 80, and take the smallest cap under which the task still passes. Steps that only
running and inspecting reveal (the traps above) are what make a task deep.
