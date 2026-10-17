"""Challenge scoring.

BEHAVIOR-1K scores each episode with partial credit ``q`` in [0, 1]: the fraction of the
task's BDDL goal predicates satisfied at the end (``q = 1`` is a full success).  The
challenge score ``Q`` is the mean over the 100 tasks of the per-task mean over the reported
instances.  A missing (task, instance) cell counts as zero, so the per-task mean always
divides by the contract's instance count, not by the number of files present.
"""
from __future__ import annotations

import math
import random
from collections import defaultdict
from typing import Iterable, Sequence

from . import N_TASKS, REPORT_INSTANCES
from .data import Episode


def task_means(episodes: Iterable[Episode], n_instances: int = len(REPORT_INSTANCES)) -> dict[int, float]:
    """Per-task mean ``q`` with missing instances counted as zero."""
    sums: dict[int, float] = defaultdict(float)
    seen: dict[int, set[int]] = defaultdict(set)
    for e in episodes:
        if e.instance in seen[e.task_id]:
            raise ValueError(f"duplicate cell task={e.task_id} instance={e.instance}; resolve provenance first")
        seen[e.task_id].add(e.instance)
        sums[e.task_id] += e.q
    return {t: s / n_instances for t, s in sums.items()}


def challenge_q(episodes: Iterable[Episode], n_tasks: int = N_TASKS,
                n_instances: int = len(REPORT_INSTANCES)) -> float:
    """The challenge score: mean over all tasks (absent tasks score zero)."""
    means = task_means(episodes, n_instances)
    if len(means) > n_tasks:
        raise ValueError("more tasks than the contract allows")
    return sum(means.values()) / n_tasks


def success_rate(episodes: Sequence[Episode]) -> float:
    return sum(e.success for e in episodes) / len(episodes) if episodes else float("nan")


def bootstrap_q(episodes: Sequence[Episode], n_boot: int = 10_000, seed: int = 0,
                alpha: float = 0.05) -> tuple[float, float, float]:
    """Point estimate and percentile CI for Q, resampling instances within each task.

    Stratifying by task keeps the 100-task composition fixed, so the interval reflects
    rollout-to-rollout noise rather than which tasks happened to be drawn.
    """
    by_task: dict[int, list[float]] = defaultdict(list)
    for e in episodes:
        by_task[e.task_id].append(e.q)
    tasks = [by_task[t] for t in sorted(by_task)]
    rng = random.Random(seed)
    stats = []
    for _ in range(n_boot):
        total = 0.0
        for qs in tasks:
            k = len(qs)
            total += sum(qs[rng.randrange(k)] for _ in range(k)) / k
        stats.append(total / N_TASKS)
    stats.sort()
    lo = stats[int(math.floor(alpha / 2 * n_boot))]
    hi = stats[int(math.ceil((1 - alpha / 2) * n_boot)) - 1]
    point = sum(sum(qs) / len(qs) for qs in tasks) / N_TASKS
    return point, lo, hi


def within_task_sd(episodes: Iterable[Episode]) -> float:
    """Pooled within-task standard deviation of episode ``q`` (rollout noise)."""
    by_task: dict[int, list[float]] = defaultdict(list)
    for e in episodes:
        by_task[e.task_id].append(e.q)
    ss, dof = 0.0, 0
    for qs in by_task.values():
        if len(qs) < 2:
            continue
        m = sum(qs) / len(qs)
        ss += sum((q - m) ** 2 for q in qs)
        dof += len(qs) - 1
    return math.sqrt(ss / dof) if dof else float("nan")


def rollouts_for_effect(delta: float, sd: float, alpha: float = 0.05, power: float = 0.8,
                        paired_rho: float = 0.0) -> int:
    """Rollouts per arm needed to detect a mean difference ``delta`` with a two-sided z-test.

    ``paired_rho`` is the correlation between arms evaluated on the same instances; pairing
    shrinks the variance of the difference by ``(1 - rho)``.
    """
    z = {0.05: 1.959964, 0.1: 1.644854}[alpha]
    zb = {0.8: 0.841621, 0.9: 1.281552}[power]
    var_diff = 2 * sd * sd * (1 - paired_rho)
    return math.ceil((z + zb) ** 2 * var_diff / (delta * delta))
