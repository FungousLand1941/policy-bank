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
from collections.abc import Iterable, Sequence
from statistics import NormalDist

from . import N_TASKS, REPORT_INSTANCES
from .data import Episode


def task_means(episodes: Iterable[Episode], n_instances: int = len(REPORT_INSTANCES), *,
               instances: Sequence[int] | None = REPORT_INSTANCES, n_tasks: int = N_TASKS) -> dict[int, float]:
    """Per-task mean ``q`` with missing instances counted as zero.

    Cells outside the contract (unknown task ids or, unless ``instances`` is ``None``, instances
    other than the reporting ones) and duplicate cells are rejected rather than silently counted.
    """
    allowed = None if instances is None else set(instances)
    sums: dict[int, float] = defaultdict(float)
    seen: dict[int, set[int]] = defaultdict(set)
    for e in episodes:
        if not 0 <= e.task_id < n_tasks:
            raise ValueError(f"task id {e.task_id} outside 0..{n_tasks - 1}")
        if allowed is not None and e.instance not in allowed:
            raise ValueError(f"instance {e.instance} of task {e.task_id} is not a reporting instance")
        if e.instance in seen[e.task_id]:
            raise ValueError(f"duplicate cell task={e.task_id} instance={e.instance}; resolve provenance first")
        if not 0.0 <= e.q <= 1.0:
            raise ValueError(f"q={e.q} outside [0, 1] for task {e.task_id} instance {e.instance}")
        seen[e.task_id].add(e.instance)
        sums[e.task_id] += e.q
    return {t: s / n_instances for t, s in sums.items()}


def challenge_q(episodes: Iterable[Episode], n_tasks: int = N_TASKS,
                n_instances: int = len(REPORT_INSTANCES)) -> float:
    """The challenge score: mean over all tasks (absent tasks and cells score zero)."""
    means = task_means(episodes, n_instances, n_tasks=n_tasks)
    return sum(means.values()) / n_tasks


def success_rate(episodes: Sequence[Episode]) -> float:
    return sum(e.success for e in episodes) / len(episodes) if episodes else float("nan")


def bootstrap_q(episodes: Sequence[Episode], n_boot: int = 10_000, seed: int = 0, alpha: float = 0.05,
                n_instances: int = len(REPORT_INSTANCES), n_tasks: int = N_TASKS,
                rescale: bool = True) -> tuple[float, float, float]:
    """Q and a percentile CI, resampling instances within each task (missing cells count zero).

    Stratifying by task keeps the 100-task composition fixed, so the interval reflects
    instance-and-rollout variation within tasks; it does not cover the choice of route, a
    simulator-version shift or the draw of hidden instances.  With ``rescale`` the deviation of
    each resampled task mean from the observed one is scaled by ``sqrt(k / (k - 1))``, undoing
    the plain bootstrap's ``(k - 1) / k`` variance shrinkage for ``k`` instances.
    """
    if n_boot < 1:
        raise ValueError("n_boot must be at least 1")
    by_task: dict[int, list[float]] = defaultdict(list)
    for e in episodes:
        by_task[e.task_id].append(e.q)
    tasks = []
    for t in range(n_tasks):
        qs = sorted(by_task.get(t, []))    # a multiset: independent of row order and instance labels
        tasks.append(qs + [0.0] * max(0, n_instances - len(qs)))
    point = challenge_q(episodes, n_tasks, n_instances)
    rng = random.Random(seed)
    stats = []
    for _ in range(n_boot):
        total = 0.0
        for qs in tasks:
            k = len(qs)
            m = sum(qs) / k
            b = sum(qs[rng.randrange(k)] for _ in range(k)) / k
            total += m + (b - m) * (math.sqrt(k / (k - 1)) if rescale and k > 1 else 1.0)
        stats.append(total / n_tasks)
    stats.sort()
    lo = stats[int(math.floor(alpha / 2 * n_boot))]
    hi = stats[int(math.ceil((1 - alpha / 2) * n_boot)) - 1]
    return point, lo, hi


def within_task_sd(episodes: Iterable[Episode]) -> float:
    """Pooled within-task standard deviation of episode ``q``.

    In the reporting set every task has one rollout on each of ten instances, so this mixes
    instance-to-instance difficulty with rollout-to-rollout randomness.
    """
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


def _z(p: float) -> float:
    return NormalDist().inv_cdf(p)


def rollouts_for_effect(delta: float, sd: float, alpha: float = 0.05, power: float = 0.8,
                        paired_rho: float = 0.0) -> int:
    """Rollouts per arm for a two-sided z-test to detect a mean difference ``delta``.

    ``paired_rho`` is the correlation between arms evaluated on the same instances; pairing
    shrinks the variance of the difference by ``(1 - rho)``.  With ``paired_rho=0`` this is an
    upper bound for paired designs.
    """
    var_diff = 2 * sd * sd * (1 - paired_rho)
    return math.ceil((_z(1 - alpha / 2) + _z(power)) ** 2 * var_diff / (delta * delta))


def rollouts_for_selection(delta: float, sd: float, p_correct: float = 0.8, paired_rho: float = 0.0) -> int:
    """Rollouts per policy so that the policy with the higher sample mean is the truly better one
    with probability ``p_correct`` (two policies, true difference ``delta``, normal approximation).

    This is the question routing asks.  It needs far fewer rollouts than a significance test,
    because a wrong pick between two nearly equal policies costs little.
    """
    return math.ceil(2 * (1 - paired_rho) * (_z(p_correct) * sd / delta) ** 2)
