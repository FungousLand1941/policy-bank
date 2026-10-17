"""Posterior-predictive simulation of the selection procedure.

The frozen route can be scored only once, so we ask the counterfactual questions with a model
calibrated to our own data:

* How optimistic should the selector's expected scores be, given how it chooses?
* Do the strict switching rules help compared with simpler rules (best development mean,
  best posterior, reference policy only), and how far are they from an oracle?
* How much would more development rollouts have bought?

Each simulated "world" draws a true score for every (task, candidate) pair from the selector's
own posterior on the real development ledger.  Development rollouts are then re-drawn with the
same cells and counts as the real ledger (optionally replicated), each episode score drawn from
a zero-inflated Beta: with probability ``(1 - theta) ** c`` the score is exactly 0 (most
failed episodes satisfy no goal condition), otherwise it is Beta with the mean that keeps the
overall mean at ``theta``; ``c`` and the Beta concentration are fitted to the within-task spread
of the reported episodes.  Every rule then picks a route from the simulated rollouts, and we
record the true score of what it picked and the score it claimed.

The study covers tasks 50-99, whose priors are built only from released development data.
"""
from __future__ import annotations

import math
import random
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from statistics import mean

from .data import Episode
from .selection import (
    Rules,
    flat_level_prior,
    noise_variance,
    paired_level,
    per_task_scores,
    policy_level,
    select_by_level,
    update,
)


def fit_beta_concentration(episodes: Sequence[Episode]) -> float:
    """Method-of-moments ``kappa`` such that var(q | task) = m(1-m) / (kappa + 1), pooled over tasks."""
    by_task: dict[int, list[float]] = defaultdict(list)
    for e in episodes:
        by_task[e.task_id].append(e.q)
    num = den = 0.0
    for qs in by_task.values():
        if len(qs) < 2:
            continue
        m = sum(qs) / len(qs)
        num += m * (1 - m)
        den += sum((q - m) ** 2 for q in qs) / (len(qs) - 1)
    if den <= 0:
        raise ValueError("no within-task variation to fit")
    return max(0.05, num / den - 1)


@dataclass(frozen=True)
class BetaOutcome:
    """Episode scores ``Beta(theta * kappa, (1 - theta) * kappa)``: never exactly zero."""

    kappa: float

    def draw(self, theta: float, rng: random.Random) -> float:
        return rng.betavariate(*_ab(theta, self.kappa))


@dataclass(frozen=True)
class ZeroInflatedOutcome:
    """Exactly 0 with probability ``(1 - theta) ** c``, else Beta with mean ``theta / (1 - pi0)``.

    Real episode scores are 0 far more often than a Beta allows (636 of the 1,000 reported
    episodes), and the selector's veto rule only reacts to exact zeros, so the simulation needs
    them too.
    """

    c: float
    kappa: float

    def draw(self, theta: float, rng: random.Random) -> float:
        theta = min(0.995, max(0.0, theta))
        pi0 = (1.0 - theta) ** self.c
        m = theta / (1.0 - pi0) if pi0 < 1.0 else 0.0
        if m > 0.98:                    # keep the nonzero part a proper Beta; adjust the zero mass
            m, pi0 = 0.98, 1.0 - theta / 0.98
        if m <= 0.0 or rng.random() < pi0:
            return 0.0
        return rng.betavariate(*_ab(m, self.kappa))


def fit_zero_inflated(episodes: Sequence[Episode]) -> ZeroInflatedOutcome:
    """Fit ``c`` by least squares on per-task zero fractions and ``kappa`` on the nonzero scores."""
    by_task: dict[int, list[float]] = defaultdict(list)
    for e in episodes:
        by_task[e.task_id].append(e.q)
    pairs = [(sum(v) / len(v), sum(q == 0 for q in v) / len(v)) for v in by_task.values()]
    pairs = [(m, z) for m, z in pairs if 0 < m < 1]
    if not pairs:
        raise ValueError("need tasks with mean strictly between 0 and 1")
    grid = [0.5 + 0.05 * i for i in range(400)]
    c = min(grid, key=lambda c: sum((z - (1 - m) ** c) ** 2 for m, z in pairs))
    num = den = 0.0
    for v in by_task.values():
        nz = [q for q in v if q > 0]
        if len(nz) < 2:
            continue
        m = sum(nz) / len(nz)
        num += m * (1 - m)
        den += sum((q - m) ** 2 for q in nz) / (len(nz) - 1)
    kappa = max(0.05, num / den - 1) if den > 0 else 2.0
    return ZeroInflatedOutcome(c, kappa)


def _outcome(model) -> BetaOutcome | ZeroInflatedOutcome:
    return BetaOutcome(float(model)) if isinstance(model, (int, float)) else model


@dataclass
class Setup:
    tasks: list[int]
    reference: str
    generalists: list[str]
    specialists: list[str]
    family: dict[str, str]
    template: list[Episode]          # real development rows that define cells and counts
    candidates: dict[int, list[str]]  # per-task candidate set (scope rule applied)

    @classmethod
    def from_ledger(cls, dev: Sequence[Episode], tasks: Sequence[int], reference: str,
                    generalists: Sequence[str], specialists: Sequence[str],
                    family: dict[str, str] | None = None) -> Setup:
        scores = per_task_scores(dev)
        specs = [p for p in specialists if p in scores and sum(map(len, scores[p].values())) >= 2]
        cands = {}
        for t in tasks:
            cands[t] = [p for p in generalists if p == reference or p in scores] + \
                       [p for p in specs if scores[p].get(t)]
        keep = {(t, p) for t, ps in cands.items() for p in ps}
        template = [e for e in dev if (e.task_id, e.policy) in keep]
        return cls(list(tasks), reference, list(generalists), specs, dict(family or {}), template, cands)


def posterior_truth(setup: Setup, dev: Sequence[Episode]) -> dict[tuple[int, str], tuple[float, float]]:
    """Posterior mean and s.d. for every (task, candidate) cell on the real ledger."""
    scores = per_task_scores(dev)
    noise = {p: noise_variance(scores.get(p, {})) for p in setup.generalists + setup.specialists}
    out = {}
    for t in setup.tasks:
        for p in setup.candidates[t]:
            level = (policy_level(scores[setup.reference], leave_out=t) if p == setup.reference
                     else paired_level(scores[p], scores[setup.reference], leave_out=t))
            post = update(flat_level_prior(level), scores[p].get(t, []), noise[p])
            out[(t, p)] = (post.mean, post.sd)
    return out


def draw_world(truth: dict, rng: random.Random) -> dict[tuple[int, str], float]:
    return {k: min(1.0, max(0.0, rng.gauss(m, s))) for k, (m, s) in truth.items()}


def draw_ledger(setup: Setup, world: dict, kappa, rng: random.Random, replicate: int = 1) -> list[Episode]:
    """Redraw the template's rollouts in a world; ``kappa`` is a Beta concentration or an outcome model."""
    model = _outcome(kappa)
    out = []
    for k in range(replicate):
        for e in setup.template:
            q = model.draw(world[(e.task_id, e.policy)], rng)
            out.append(Episode(task_id=e.task_id, task=e.task, instance=e.instance + 100 * k,
                               policy=e.policy, q=q, success=q >= 0.999))
    return out


# ------------------------------------------------------------------ rules

Rule = Callable[[Setup, list[Episode], dict], tuple[dict[int, str], dict[int, float]]]


def rule_reference(setup, dev, world):
    return {t: setup.reference for t in setup.tasks}, None


def rule_oracle(setup, dev, world):
    pick = {t: max(setup.candidates[t], key=lambda p: world[(t, p)]) for t in setup.tasks}
    return pick, {t: world[(t, p)] for t, p in pick.items()}


def rule_best_mean(setup, dev, world):
    cell = defaultdict(list)
    for e in dev:
        cell[(e.task_id, e.policy)].append(e.q)
    pick, claim = {}, {}
    for t in setup.tasks:
        seen = [(sum(v) / len(v), p) for p in setup.candidates[t] if (v := cell.get((t, p)))]
        m, p = max(seen) if seen else (None, setup.reference)
        pick[t], claim[t] = p, m if m is not None else 0.0
    return pick, claim


def _rule_selector(rules: Rules, consolidate: bool):
    def run(setup, dev, world):
        ds = select_by_level(setup.tasks, dev, setup.reference, setup.generalists, setup.specialists,
                             setup.family if consolidate else {}, rules)
        return {d.task_id: d.choice for d in ds}, {d.task_id: d.expected() for d in ds}
    return run


RULES: dict[str, Rule] = {
    "reference only": rule_reference,
    "best dev mean": rule_best_mean,
    "best posterior": _rule_selector(Rules(min_own_rollouts=0, dev_guard=False, switch_margin=0.0,
                                           veto_ref_above=None), consolidate=False),
    "strict rules (ours)": _rule_selector(Rules(), consolidate=True),
    "oracle": rule_oracle,
}


def _ab(theta: float, kappa: float) -> tuple[float, float]:
    th = min(0.995, max(0.005, theta))
    return th * kappa, (1 - th) * kappa


def run_study(setup: Setup, dev: Sequence[Episode], kappa, sims: int = 200, seed: int = 0,
              replicate: int = 1, rules: dict[str, Rule] | None = None,
              report_instances: int = 10) -> dict[str, dict]:
    """Return, per rule, the mean true Q (over the setup's tasks), claimed Q and optimism, with
    5th/95th percentiles of the true Q across simulated worlds."""
    rules = rules or RULES
    model = _outcome(kappa)
    truth = posterior_truth(setup, dev)
    rng = random.Random(seed)
    acc: dict[str, dict[str, list[float]]] = {
        k: {"true": [], "claimed": [], "regret": [], "raw_gap": [], "reported": []} for k in rules}
    for _ in range(sims):
        world = draw_world(truth, rng)
        ledger = draw_ledger(setup, world, kappa, rng, replicate)
        cell = defaultdict(list)
        for e in ledger:
            cell[(e.task_id, e.policy)].append(e.q)
        best = mean(max(world[(t, p)] for p in setup.candidates[t]) for t in setup.tasks)
        for name, rule in rules.items():
            pick, claim = rule(setup, ledger, world)
            true_q = mean(world[(t, p)] for t, p in pick.items())
            acc[name]["true"].append(true_q)
            acc[name]["regret"].append(best - true_q)
            # One simulated reporting run: ``report_instances`` fresh episodes per task.
            rep = [sum(model.draw(world[(t, p)], rng) for _ in range(report_instances))
                   / report_instances for t, p in pick.items()]
            acc[name]["reported"].append(mean(rep))
            acc[name]["claimed"].append(mean(claim.values()) if claim else float("nan"))
            # Raw development mean of the chosen policy minus its true score, on tasks where the
            # chosen policy has rollouts: the selection bias a naive reader of the ledger would see.
            seen = [(sum(v) / len(v)) - world[(t, p)] for t, p in pick.items() if (v := cell.get((t, p)))]
            acc[name]["raw_gap"].append(mean(seen) if seen else float("nan"))
    out = {}
    for name, a in acc.items():
        tr = sorted(a["true"])
        claimed = [c for c in a["claimed"] if not math.isnan(c)]
        out[name] = {
            "true": mean(a["true"]), "true_p05": tr[int(0.05 * len(tr))], "true_p95": tr[int(0.95 * len(tr)) - 1],
            "claimed": mean(claimed) if claimed else None,
            "optimism": (mean(claimed) - mean(a["true"])) if claimed else None,
            "regret": mean(a["regret"]),
            "reported": sorted(a["reported"]),
            "raw_dev_gap": mean(g for g in a["raw_gap"] if not math.isnan(g)) if any(
                not math.isnan(g) for g in a["raw_gap"]) else None,
        }
    return out
