"""Development-selected routing: choose one policy per task from noisy development rollouts.

Each (task, policy) pair gets a Gaussian prior on its expected task score.  Development
rollouts on instances 311-320 update that prior with a conjugate Gaussian likelihood, and a
policy replaces the task's incumbent ("fallback") only when the posterior gain survives a set
of conservative rules.  Reported instances 301-310 are never an input.

Two prior constructions are provided:

* :func:`transfer_prior` for tasks with public reference results (for example the 2025
  per-task scores of a released checkpoint), scaled by a transfer factor estimated from our
  own development rollouts on *other* tasks;
* :func:`flat_level_prior` for tasks with no reference: a policy-level score estimated from
  the policy's rollouts on other tasks, paired against a reference policy and shrunk toward its
  family, widened by the between-task spread.

This module is a clean reimplementation of the selection logic used for the frozen route.
The frozen decisions themselves are recorded in ``data/route.json``.
"""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Iterable, Mapping, Sequence

from .data import Episode


@dataclass(frozen=True)
class Gaussian:
    mean: float
    sd: float

    @property
    def precision(self) -> float:
        return 1.0 / (self.sd * self.sd)

    def __str__(self) -> str:
        return f"{self.mean:.3f}±{self.sd:.3f}"


def update(prior: Gaussian, scores: Sequence[float], noise_var: float) -> Gaussian:
    """Conjugate update of a Gaussian prior with ``len(scores)`` rollouts of variance ``noise_var``."""
    if not scores:
        return prior
    if noise_var <= 0:
        raise ValueError("noise variance must be positive")
    p0 = prior.precision
    pd = len(scores) / noise_var
    mean = (p0 * prior.mean + pd * (sum(scores) / len(scores))) / (p0 + pd)
    return Gaussian(mean, math.sqrt(1.0 / (p0 + pd)))


def combine(*estimates: Gaussian) -> Gaussian:
    """Precision-weighted combination of independent Gaussian estimates."""
    p = sum(e.precision for e in estimates)
    return Gaussian(sum(e.precision * e.mean for e in estimates) / p, math.sqrt(1.0 / p))


# --------------------------------------------------------------------------- priors

def transfer_prior(reference_q: float, factor: Gaussian, base_sd: float = 0.088) -> Gaussian:
    """Prior from a public reference score scaled by an uncertain transfer factor.

    The variance adds the factor's uncertainty (scaled by the reference) to a base spread that
    covers task-specific deviations from a single global factor.
    """
    mean = factor.mean * reference_q
    var = (reference_q * factor.sd) ** 2 + base_sd ** 2
    return Gaussian(mean, math.sqrt(var))


def estimate_transfer_factor(own: Mapping[int, Sequence[float]], reference: Mapping[int, float],
                             leave_out: int | None = None) -> Gaussian:
    """Ratio estimator ``sum(own means) / sum(reference)`` over tasks with a positive reference.

    ``leave_out`` drops the task being decided, so its own rollouts are not counted twice
    (once in the prior and again in the likelihood).  The standard error comes from the
    delta method over tasks.
    """
    tasks = [t for t in own if t in reference and reference[t] > 0 and own[t] and t != leave_out]
    if len(tasks) < 2:
        raise ValueError("need at least two tasks with reference scores")
    x = [sum(own[t]) / len(own[t]) for t in tasks]
    r = [reference[t] for t in tasks]
    ratio = sum(x) / sum(r)
    resid = [xi - ratio * ri for xi, ri in zip(x, r)]
    n = len(tasks)
    se = math.sqrt(sum(e * e for e in resid) / (n - 1) / n) / (sum(r) / n)
    return Gaussian(ratio, se)


def per_task_scores(rows: Iterable[Episode]) -> dict[str, dict[int, list[float]]]:
    out: dict[str, dict[int, list[float]]] = defaultdict(lambda: defaultdict(list))
    for e in rows:
        out[e.policy][e.task_id].append(e.q)
    return out


def policy_level(scores: Mapping[int, Sequence[float]], leave_out: int | None = None) -> Gaussian | None:
    """Mean of per-task means over tasks other than ``leave_out``, with its standard error."""
    means = [sum(v) / len(v) for t, v in scores.items() if t != leave_out and v]
    if not means:
        return None
    m = sum(means) / len(means)
    if len(means) > 1:
        var = sum((x - m) ** 2 for x in means) / (len(means) - 1)
    else:
        var = 0.1 ** 2  # a single task says little about the level
    return Gaussian(m, math.sqrt(max(var, 1e-4) / len(means)))


def paired_level(candidate: Mapping[int, Sequence[float]], reference: Mapping[int, Sequence[float]],
                 leave_out: int | None = None) -> Gaussian | None:
    """Candidate level = reference level + mean paired difference on shared tasks."""
    ref = policy_level(reference, leave_out)
    shared = [t for t in candidate if t in reference and t != leave_out and candidate[t] and reference[t]]
    if ref is None or not shared:
        return None
    d = [sum(candidate[t]) / len(candidate[t]) - sum(reference[t]) / len(reference[t]) for t in shared]
    md = sum(d) / len(d)
    sd_d = math.sqrt(sum((x - md) ** 2 for x in d) / (len(d) - 1)) if len(d) > 1 else 0.25
    se = math.sqrt(ref.sd ** 2 + max(sd_d, 0.05) ** 2 / len(d))
    return Gaussian(max(0.0, ref.mean + md), se)


def flat_level_prior(level: Gaussian | None, shrink_to: Gaussian = Gaussian(0.1, 0.1),
                     between_task_sd: float = 0.1) -> Gaussian:
    """Task prior from a policy level: shrink the level, then widen by the between-task spread."""
    lv = shrink_to if level is None else combine(level, shrink_to)
    return Gaussian(lv.mean, math.sqrt(lv.sd ** 2 + between_task_sd ** 2))


def noise_variance(scores: Mapping[int, Sequence[float]], default: float = 0.08, prior_dof: float = 4.0,
                   floor: float = 0.01) -> float:
    """Pooled within-task rollout variance, shrunk toward ``default`` with ``prior_dof`` pseudo-dof."""
    ss, dof = 0.0, 0
    for v in scores.values():
        if len(v) > 1:
            m = sum(v) / len(v)
            ss += sum((x - m) ** 2 for x in v)
            dof += len(v) - 1
    return max(floor, (ss + prior_dof * default) / (dof + prior_dof))


# --------------------------------------------------------------------------- decisions

@dataclass(frozen=True)
class Rules:
    """Conservative switching rules ("strict" in the frozen route).

    * ``min_own_rollouts``: a challenger needs this many of its own rollouts on the task.
    * ``dev_guard``: a challenger must beat the fallback on the development instances they
      share (at least ``min_shared`` of them), not only in posterior.
    * ``switch_margin``: minimum posterior gain over the fallback.
    * ``veto_ref_above``: veto a challenger that scored zero on every instance where the
      fallback scored above this value.
    """

    min_own_rollouts: int = 2
    dev_guard: bool = True
    min_shared: int = 2
    switch_margin: float = 0.01
    veto_ref_above: float | None = 0.1


@dataclass
class Candidate:
    policy: str
    prior: Gaussian
    n: int
    dev_mean: float | None
    posterior: Gaussian
    flags: list[str] = field(default_factory=list)

    @property
    def eligible(self) -> bool:
        return not self.flags


@dataclass
class Decision:
    task_id: int
    fallback: str
    choice: str
    reason: str
    candidates: list[Candidate]

    @property
    def switched(self) -> bool:
        return self.choice != self.fallback

    def expected(self, policy: str | None = None) -> float:
        policy = policy or self.choice
        return next(c.posterior.mean for c in self.candidates if c.policy == policy)


def _by_instance(rows: Iterable[Episode]) -> dict[int, list[float]]:
    out: dict[int, list[float]] = defaultdict(list)
    for e in rows:
        out[e.instance].append(e.q)
    return out


def decide(task_id: int, fallback: str, priors: Mapping[str, Gaussian], dev: Sequence[Episode],
           noise: Mapping[str, float], rules: Rules = Rules(), guarded: bool = True) -> Decision:
    """Choose a policy for one task.

    ``guarded`` applies the incumbent-protecting rules (own rollouts and the dev guard).  With
    ``guarded=False`` the highest eligible posterior wins, which suits tasks where the fallback
    itself is only a weak default.
    """
    if fallback not in priors:
        raise ValueError(f"fallback {fallback!r} needs a prior")
    rows = [e for e in dev if e.task_id == task_id]
    fb_inst = _by_instance(e for e in rows if e.policy == fallback)
    cands = []
    for policy, prior in priors.items():
        own = [e.q for e in rows if e.policy == policy]
        post = update(prior, own, noise.get(policy, 0.08))
        c = Candidate(policy, prior, len(own), sum(own) / len(own) if own else None, post)
        if policy != fallback:
            mine = _by_instance(e for e in rows if e.policy == policy)
            shared = sorted(set(mine) & set(fb_inst))
            if guarded and len(own) < rules.min_own_rollouts:
                c.flags.append(f"only {len(own)} own dev rollout(s) (< {rules.min_own_rollouts})")
            if guarded and rules.dev_guard:
                if len(shared) < rules.min_shared:
                    c.flags.append(f"dev guard: {len(shared)} shared instance(s) with the fallback")
                else:
                    a = sum(sum(mine[i]) / len(mine[i]) for i in shared) / len(shared)
                    b = sum(sum(fb_inst[i]) / len(fb_inst[i]) for i in shared) / len(shared)
                    if a <= b:
                        c.flags.append(f"dev guard: {a:.3f} vs fallback {b:.3f} on {len(shared)} shared")
            if rules.veto_ref_above is not None:
                hot = [i for i in shared if max(fb_inst[i]) > rules.veto_ref_above]
                if hot and all(max(mine[i]) == 0 for i in hot):
                    c.flags.append("veto: zero wherever the fallback scored")
        cands.append(c)
    cands.sort(key=lambda c: -c.posterior.mean)
    fb = next(c for c in cands if c.policy == fallback)
    best = next((c for c in cands if c.policy != fallback and c.eligible), None)
    if best is not None and best.posterior.mean - fb.posterior.mean >= rules.switch_margin:
        reason = f"switch: {best.policy} beats fallback by {best.posterior.mean - fb.posterior.mean:+.3f}"
        return Decision(task_id, fallback, best.policy, reason, cands)
    top = cands[0]
    if top.policy != fallback and not top.eligible:
        reason = f"keep fallback; {top.policy} has the top posterior but {top.flags[0]}"
    else:
        reason = "keep fallback: it has the highest eligible posterior"
    return Decision(task_id, fallback, fallback, reason, cands)


def one_per_family(decisions: Sequence[Decision], family: Mapping[str, str]) -> dict[str, str]:
    """Pick a single member per checkpoint family by total posterior gain over the fallbacks.

    Serving one image per family member multiplies disk and qualification cost; when two
    checkpoints of the same family win different tasks, keep the one with the larger summed
    gain (in task points) and route the other's tasks to it.
    """
    gain: dict[str, float] = defaultdict(float)
    for d in decisions:
        fb = d.expected(d.fallback)
        for c in d.candidates:
            if c.eligible or c.policy == d.fallback:
                gain[c.policy] += max(0.0, c.posterior.mean - fb)
    chosen = {d.choice for d in decisions}
    keep: dict[str, str] = {}
    by_fam: dict[str, list[str]] = defaultdict(list)
    for p in chosen:
        by_fam[family.get(p, p)].append(p)
    for members in by_fam.values():
        winner = max(members, key=lambda p: gain[p])
        for p in members:
            keep[p] = winner
    return keep


def select_by_level(tasks: Sequence[int], dev: Sequence[Episode], reference: str,
                    generalists: Sequence[str], specialists: Sequence[str] = (),
                    family: Mapping[str, str] | None = None, rules: Rules = Rules(),
                    min_policy_rollouts: int = 2) -> list[Decision]:
    """Route tasks that have no public reference scores (tasks 50-99 in the frozen route).

    Generalists are candidates on every task.  A specialist is a candidate only on tasks where
    it has its own development rollouts, and only if it has at least ``min_policy_rollouts`` in
    total.  Priors come from :func:`paired_level` against ``reference`` with the task left out.
    The highest eligible posterior wins (``guarded=False``); a second pass keeps one checkpoint
    per family and re-decides the tasks of the family members that were dropped.
    """
    family = dict(family or {})
    scores = per_task_scores(dev)
    pool = [p for p in (*generalists, *specialists) if p == reference or p in scores]

    def priors_for(task: int, allowed: set[str]) -> dict[str, Gaussian]:
        out = {}
        for p in pool:
            if p not in allowed:
                continue
            if p in specialists and (not scores[p].get(task)
                                     or sum(map(len, scores[p].values())) < min_policy_rollouts):
                continue
            level = (policy_level(scores[reference], leave_out=task) if p == reference
                     else paired_level(scores[p], scores[reference], leave_out=task))
            out[p] = flat_level_prior(level)
        return out

    noise = {p: noise_variance(scores.get(p, {})) for p in pool}
    allowed = set(pool)
    first = [decide(t, reference, priors_for(t, allowed), dev, noise, rules, guarded=False) for t in tasks]
    keep = one_per_family(first, family)
    dropped = {p for p, w in keep.items() if p != w}
    if not dropped:
        return first
    allowed -= dropped
    return [decide(t, reference, priors_for(t, allowed), dev, noise, rules, guarded=False) for t in tasks]
