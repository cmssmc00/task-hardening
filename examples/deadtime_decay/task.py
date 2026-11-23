"""Example hardened task (invented for this repository): lifetimes from a pulsed counting experiment.

The easy version of this task hands over a clean decay curve and asks for a lifetime. The hardened version
follows the recipe in docs/RECIPE.md:

* raw data: binned counts summed over many sweeps, plus two blank runs, plus the instrument notes;
* no method given: the instruction states the conventions (dead-time model, how to choose the number of
  components) but not how to fit;
* a choice step: one or two decay components, decided by a stated BIC rule;
* traps that the data reveal: counting dead time (the early bins are suppressed), a background that drifts
  between the blank taken before and the one taken after the run;
* a program graded on 8 hidden cases, each with its own dead time, background drift and decay.
"""
from __future__ import annotations

import math

import numpy as np

from hardening import Case, Check, Claim, HardTask

BIN_S = 0.5e-3          # bin width (s)
N_BINS = 400            # 0-200 ms
TOL = {"lifetime": 0.04, "short_lifetime": 0.08, "amplitude": 0.08, "background": 0.03}   # relative
BIC_GAP = 10.0
LOG_TAU = (math.log(1e-3), math.log(60e-3))     # the stated lifetime range

INSTRUCTION = """\
# Lifetimes from a pulsed counting run

A pulsed source is measured with a counting detector. `/app/data/` holds, for one measurement, `run.json`:
the counts in 0.5 ms bins after the pulse, summed over all sweeps; two blank runs (no source) taken before
and after the measurement; their wall-clock times; and the instrument notes.

Write `/app/solve.py`. It reads one such `run.json` (path as the first argument) and writes a JSON answer
(path as the second argument) with:

- `n_components`: 1 or 2, the number of exponential decay components;
- `lifetimes_ms`: their lifetimes in ms, ascending;
- `amplitudes_cps`: their true (dead-time-free) count rates at t = 0, in counts per second, in the same order;
- `background_cps`: the background rate during the measurement, in counts per second.

Conventions:
- The detector is non-paralysable with the dead time given in the notes (between 2 and 6 microseconds).
- The true rate is `background + sum_i A_i exp(-t / tau_i)`, with `t` at the bin centre.
- Fit by weighted least squares on the dead-time-corrected, background-subtracted rate, with weights from
  Poisson counting statistics propagated through the correction. With `p = 2` parameters per component,
  `BIC = chi2 + p ln N`; report two components only if `BIC_2 < BIC_1 - 10`.
- There are at most two components, with lifetimes between 1 and 60 ms.

Your program is run on 8 hidden measurements, 60 s each. The component count must match the reference;
lifetimes must be within 4 % of it (8 % for the shorter of two), amplitudes within 8 % and the background
within 3 %.
"""


# ---- generator ------------------------------------------------------------------------------------------------
def _true_rate(t, bkg, amps, taus):
    return bkg + sum(a * np.exp(-t / tau) for a, tau in zip(amps, taus))


def _measured(n, dead):
    return n / (1.0 + n * dead)                       # non-paralysable dead time


class DeadtimeDecay(HardTask):
    name = "deadtime-decay"
    instruction = INSTRUCTION

    def make_case(self, seed: int) -> Case:
        rng = np.random.default_rng(seed)
        n_comp = 1 + int(rng.integers(0, 2))
        dead = float(rng.uniform(2e-6, 6e-6))
        sweeps = int(rng.integers(2000, 4000))
        if n_comp == 1:
            taus = [float(rng.uniform(4.0, 30.0))]
            amps = [float(rng.uniform(6e4, 1.4e5))]
        else:
            t1 = float(rng.uniform(2.0, 6.0))
            taus = [t1, float(t1 * rng.uniform(4.0, 9.0))]
            total = float(rng.uniform(8e4, 1.6e5))
            f = float(rng.uniform(0.25, 0.6))
            amps = [total * f, total * (1 - f)]
        taus_s = [x * 1e-3 for x in taus]
        b0 = float(rng.uniform(2e3, 6e3))
        drift = float(rng.uniform(0.3, 0.7)) * (1 if rng.random() < 0.5 else -1)
        b1 = b0 * (1 + drift)
        t_before, t_run, t_after = 0.0, float(rng.uniform(600, 1800)), 2400.0      # seconds, wall clock
        bkg = b0 + (b1 - b0) * (t_run - t_before) / (t_after - t_before)
        t = (np.arange(N_BINS) + 0.5) * BIN_S
        expo = sweeps * BIN_S
        counts = rng.poisson(expo * _measured(_true_rate(t, bkg, amps, taus_s), dead))
        blank_live = 120.0
        blanks = [int(rng.poisson(blank_live * _measured(b, dead))) for b in (b0, b1)]
        inputs = {
            "bin_width_s": BIN_S, "sweeps": sweeps, "counts": counts.tolist(),
            "blanks": [{"wall_clock_s": t_before, "live_time_s": blank_live, "counts": blanks[0]},
                       {"wall_clock_s": t_after, "live_time_s": blank_live, "counts": blanks[1]}],
            "run_wall_clock_s": t_run,
            "notes": {"dead_time_s": dead, "dead_time_model": "non-paralysable"},
        }
        truth = {"n_components": n_comp, "lifetimes_ms": taus, "amplitudes_cps": amps, "background_cps": bkg}
        return Case(seed, inputs, truth)

    def truth_answer(self, case: Case) -> dict:
        return dict(case.truth)

    # ---- reference ------------------------------------------------------------------------------------------
    def reference(self, inputs: dict) -> dict:
        return solve(inputs)

    def second_opinion(self, inputs: dict) -> dict:
        return solve(inputs, search="nelder-mead")

    # ---- grading --------------------------------------------------------------------------------------------
    def grade(self, case: Case, answer: dict, ref: dict) -> list[Check]:
        checks = []
        n = answer.get("n_components")
        checks.append(Check("n_components", n == ref["n_components"], n, ref["n_components"]))
        if n != ref["n_components"]:
            return checks
        for key in ("lifetimes_ms", "amplitudes_cps"):
            got = answer.get(key) or []
            for i, want in enumerate(ref[key]):
                tol = TOL["amplitude"] if key == "amplitudes_cps" else \
                    TOL["short_lifetime"] if (n == 2 and i == 0) else TOL["lifetime"]
                v = got[i] if i < len(got) else float("nan")
                ok = isinstance(v, (int, float)) and math.isfinite(v) and abs(v - want) <= tol * abs(want)
                checks.append(Check(f"{key}[{i}]", ok, v, want, tol * abs(want)))
        v, want = answer.get("background_cps", float("nan")), ref["background_cps"]
        ok = isinstance(v, (int, float)) and math.isfinite(v) and abs(v - want) <= TOL["background"] * want
        checks.append(Check("background_cps", ok, v, want, TOL["background"] * want))
        return checks

    def claims(self) -> list[Claim]:
        return [
            Claim("dead time between 2 and 6 us", lambda c, r: 2e-6 <= c.inputs["notes"]["dead_time_s"] <= 6e-6),
            Claim("at most two components", lambda c, r: c.truth["n_components"] in (1, 2)),
            Claim("lifetimes between 1 and 60 ms", lambda c, r: all(1 <= x <= 60 for x in c.truth["lifetimes_ms"])),
            Claim("the run lies between the two blanks", lambda c, r:
                  c.inputs["blanks"][0]["wall_clock_s"] < c.inputs["run_wall_clock_s"]
                  < c.inputs["blanks"][1]["wall_clock_s"]),
            Claim("the BIC rule picks the true component count",
                  lambda c, r: r["n_components"] == c.truth["n_components"]),
        ]

    # ---- controls -------------------------------------------------------------------------------------------
    def negatives(self) -> dict:
        return {
            "no dead-time correction": lambda x: solve(x, deadtime=False),
            "background from the first blank only": lambda x: solve(x, background="first"),
            "always two components": lambda x: solve(x, force_components=2),
        }

    def fairness(self) -> dict:
        return {
            "Nelder-Mead instead of a grid": lambda x: solve(x, search="nelder-mead"),
            "finer grid": lambda x: solve(x, grid=120),
        }

    def public_examples(self) -> list[Case]:
        return [self.make_case(s) for s in (90001, 90002)]


# ---- the reference solver and its variants ---------------------------------------------------------------------
def _background(inputs, which="interpolate", blank_deadtime=True):
    dead = inputs["notes"]["dead_time_s"]
    rates = []
    for b in inputs["blanks"]:
        m = b["counts"] / b["live_time_s"]
        rates.append(m / (1 - m * dead) if blank_deadtime else m)
    if which == "first":
        return rates[0]
    (t0, t1), tr = (inputs["blanks"][0]["wall_clock_s"], inputs["blanks"][1]["wall_clock_s"]), inputs["run_wall_clock_s"]
    return rates[0] + (rates[1] - rates[0]) * (tr - t0) / (t1 - t0)


def _project(t, y, w, taus):
    """Weighted linear least squares for the amplitudes at fixed lifetimes; returns (chi2, amplitudes)."""
    X = np.exp(-t[:, None] / np.asarray(taus)[None, :])
    sw = np.sqrt(w)
    amps, *_ = np.linalg.lstsq(X * sw[:, None], y * sw, rcond=None)
    r = (y - X @ amps) * sw
    return float(r @ r), amps


def _grid_fit(t, y, w, k, grid):
    lo, hi = LOG_TAU
    g = np.exp(np.linspace(lo, hi, grid))
    best = (math.inf, None, None)
    if k == 1:
        for a in g:
            c, amps = _project(t, y, w, [a])
            if c < best[0]:
                best = (c, [a], amps)
    else:
        for i, a in enumerate(g):
            for b in g[i + 1:]:
                c, amps = _project(t, y, w, [a, b])
                if c < best[0] and np.all(amps > 0):
                    best = (c, [a, b], amps)
    # local refinement: shrink a log-scale step around the best point
    taus = np.log(best[1])
    step = (hi - lo) / grid
    while step > 1e-5:
        improved = False
        for j in range(k):
            for s in (-step, step):
                trial = taus.copy()
                trial[j] += s
                if (k == 2 and trial[0] >= trial[1]) or trial.min() < lo or trial.max() > hi:
                    continue
                c, amps = _project(t, y, w, np.exp(trial))
                if c < best[0] and np.all(amps > 0):
                    best, taus, improved = (c, list(np.exp(trial)), amps), trial, True
        if not improved:
            step /= 2
    return best


def _nelder_mead(f, x0, scale=0.3, iters=400):
    pts = [np.array(x0, float)] + [np.array(x0, float) + scale * np.eye(len(x0))[i] for i in range(len(x0))]
    vals = [f(p) for p in pts]
    for _ in range(iters):
        order = np.argsort(vals)
        pts, vals = [pts[i] for i in order], [vals[i] for i in order]
        centroid = np.mean(pts[:-1], axis=0)
        xr = centroid + (centroid - pts[-1])
        fr = f(xr)
        if fr < vals[0]:
            xe = centroid + 2 * (centroid - pts[-1])
            fe = f(xe)
            pts[-1], vals[-1] = (xe, fe) if fe < fr else (xr, fr)
        elif fr < vals[-2]:
            pts[-1], vals[-1] = xr, fr
        else:
            xc = centroid + 0.5 * (pts[-1] - centroid)
            fc = f(xc)
            if fc < vals[-1]:
                pts[-1], vals[-1] = xc, fc
            else:
                pts = [pts[0] + 0.5 * (p - pts[0]) for p in pts]
                vals = [f(p) for p in pts]
    i = int(np.argmin(vals))
    return pts[i], vals[i]


def _nm_fit(t, y, w, k):
    def f(logt):
        if min(logt) < LOG_TAU[0] or max(logt) > LOG_TAU[1]:
            return 1e30
        taus = np.exp(np.sort(logt))
        c, amps = _project(t, y, w, taus)
        return c if np.all(amps > 0) else c + 1e12
    best = (math.inf, None)
    starts = [[math.log(x)] for x in (2e-3, 8e-3, 30e-3)] if k == 1 else \
        [[math.log(a), math.log(b)] for a in (1.5e-3, 4e-3) for b in (12e-3, 30e-3, 50e-3)]
    for s in starts:
        x, v = _nelder_mead(f, s)
        if v < best[0]:
            best = (v, x)
    taus = np.exp(np.sort(best[1]))
    c, amps = _project(t, y, w, taus)
    return c, list(taus), amps


def solve(inputs, deadtime=True, background="interpolate", force_components=None, search="grid", grid=60,
          blank_deadtime=True) -> dict:
    counts = np.asarray(inputs["counts"], float)
    expo = inputs["sweeps"] * inputs["bin_width_s"]
    t = (np.arange(len(counts)) + 0.5) * inputs["bin_width_s"]
    dead = inputs["notes"]["dead_time_s"] if deadtime else 0.0
    m = counts / expo
    n = m / (1 - m * dead)
    var = np.maximum(counts, 1.0) / expo ** 2 / (1 - m * dead) ** 4     # Poisson, propagated through the correction
    bkg = _background(inputs, background, blank_deadtime)
    y, w = n - bkg, 1.0 / var
    fits = {}
    for k in (1, 2):
        c, taus, amps = _grid_fit(t, y, w, k, grid) if search == "grid" else _nm_fit(t, y, w, k)
        fits[k] = (c + 2 * k * math.log(len(y)), taus, amps)
    k = force_components or (2 if fits[2][0] < fits[1][0] - BIC_GAP else 1)
    _, taus, amps = fits[k]
    order = np.argsort(taus)
    return {"n_components": k, "lifetimes_ms": [float(taus[i] * 1e3) for i in order],
            "amplitudes_cps": [float(amps[i]) for i in order], "background_cps": float(bkg)}


TASK = DeadtimeDecay()
