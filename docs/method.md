# Selection method

This page specifies how `policybank.selection` chooses one policy per task from development
rollouts. It covers the model, the two prior constructions, the switching rules, the
one-checkpoint-per-training-run search, the two-stage freeze, a worked example computed with the
released code, and every hyperparameter.

Values marked † come from pipeline logs and reports that are not part of the release. They cannot
be recomputed from `data/`. Every other number on this page is produced by the released code from
the released data.

## What the release can and cannot reproduce

| Part of the route | Tasks | Reproducible from `data/`? |
|---|---|---|
| Stage 2, tasks 50–99 (level-based priors) | 50 | Re-run: `python -m policybank select` (`policybank.analysis.reproduce_stage2`) repeats the selection and agrees with the frozen route on 48 of 50 tasks. |
| Stage 2, tasks 0–49 (transfer priors + guarded rules) | 13 | No. The priors need 2025 per-task reference tables that are not redistributed. The functions are released. |
| Stage 1, tasks 0–49 | 37 | No. These entries came from an earlier route writer that ranked posteriors built from the same priors, without the guard rules†. |

`selection.py` is a clean reimplementation of the logic used for the frozen route. The decisions
themselves are recorded in `data/route.json`. In the two stage-2 disagreements the reimplementation
keeps the reference `s150997` where the frozen route has `comet@ymetz9999`: task 70 is a near tie
(posterior 0.176 against 0.173), and on task 87 the reimplementation prefers the reference (0.288
against 0.229). The original pipeline used a slightly different development table and pooled the two
ymetz steps (see [Paired policy levels](#paired-policy-levels-tasks-5099)).

## Notation

| Symbol | Meaning |
|---|---|
| $t$, $u$ | task ids, 0–99 |
| $p$ | policy label (for example `comet@ymetz9999`) |
| $\theta_{tp}$ | expected score of policy $p$ on task $t$ |
| $y_{tpk}$ | score `q` of the $k$-th eligible development rollout of $p$ on $t$ |
| $n_{tp}$, $\bar y_{tp}$ | number and mean of those rollouts |
| $\mu_{tp}$, $\tau_{tp}$ | prior mean and standard deviation of $\theta_{tp}$ |
| $\sigma_p^2$ | rollout noise variance of policy $p$ |
| $r_{tp}$ | public 2025 reference score (tasks 0–49 only) |
| $\gamma_f$, $s_\gamma$ | transfer factor of checkpoint family $f$ and its standard error |
| $\ell_{p,-t}$ | level of policy $p$ estimated without task $t$ |
| ref | the reference policy for tasks 50–99, `s150997` |

"Eligible" rollouts are the rows returned by `policybank.data.load_dev(selection_only=True)`; see
[data.md](data.md#eligibility-filter).

## Gaussian model and conjugate update

Each (task, policy) pair gets a Gaussian prior, and each development rollout is treated as a
Gaussian observation of the pair's expected score:

$$\theta_{tp} \sim \mathcal N(\mu_{tp}, \tau_{tp}^2), \qquad y_{tpk} \mid \theta_{tp} \sim \mathcal N(\theta_{tp}, \sigma_p^2).$$

With $n$ rollouts of mean $\bar y$ the posterior is

$$\theta_{tp} \mid y \sim \mathcal N\left(\frac{\mu_{tp}/\tau_{tp}^2 + n\bar y/\sigma_p^2}{1/\tau_{tp}^2 + n/\sigma_p^2},\ \left(\frac{1}{\tau_{tp}^2} + \frac{n}{\sigma_p^2}\right)^{-1}\right).$$

`update(prior, scores, noise_var)` implements this. With no scores it returns the prior unchanged,
and it raises `ValueError` if `noise_var <= 0`. `combine(*estimates)` is the precision-weighted
combination of independent Gaussians. `Gaussian(mean, sd)` rejects a non-finite mean or a
non-positive or non-finite `sd`.

Rollout scores are bounded in $[0, 1]$, pile up at 0 and are often bimodal. The Gaussian likelihood
is an approximation whose job is to weigh a prior against a handful of rollouts.
[simulation.md](simulation.md) checks it against zero-inflated Beta outcomes ($c = 4.0$,
$\kappa \approx 6.42$, fitted to the reported episodes), with a plain Beta as a sensitivity check.

## Noise-variance pooling

`noise_variance(scores, default=0.08, prior_dof=4.0, floor=0.01)` pools the within-task variance of
one policy over every task where it has at least two rollouts, and shrinks it toward a default:

$$\hat\sigma_p^2 = \max\left(0.01,\ \frac{\mathrm{SS}_p + \nu_0 \sigma_0^2}{\mathrm{df}_p + \nu_0}\right), \qquad \sigma_0^2 = 0.08,\ \nu_0 = 4,$$

where $\mathrm{SS}_p = \sum_t \sum_k (y_{tpk} - \bar y_{tp})^2$ and $\mathrm{df}_p = \sum_t (n_{tp} - 1)$
over tasks with $n_{tp} \ge 2$. A policy with no repeated rollouts gets exactly 0.08. The pool uses
every task in the ledger that is passed in, including the task being decided. Inside `decide`, a
policy missing from the `noise` map also gets 0.08.

## Priors where public reference results exist (tasks 0–49)

For tasks 0–49, per-task 2025 results of the Comet and winner checkpoints are public. They come from
a different simulator setup and different instances, so `transfer_prior(reference_q, factor,
base_sd=0.088)` scales them by an uncertain transfer factor:

$$\mu_{tp} = \gamma_f r_{tp}, \qquad \tau_{tp}^2 = (r_{tp} s_\gamma)^2 + b^2, \qquad b = 0.088.$$

The first variance term carries the factor's uncertainty. The floor $b$ covers task-specific
deviations from a single global factor.

`estimate_transfer_factor(own, reference, leave_out=None)` is the ratio estimator over the $m$ tasks
$u$ that have a positive reference score and at least one own rollout, excluding `leave_out`:

$$\hat\gamma = \frac{\sum_u \bar y_u}{\sum_u r_u}, \qquad \mathrm{se}(\hat\gamma) = \frac{\sqrt{\frac{1}{m(m-1)}\sum_u (\bar y_u - \hat\gamma r_u)^2}}{\frac{1}{m}\sum_u r_u}.$$

The standard error is the delta-method one and is floored at $10^{-3}$. At least two tasks are
required. `leave_out` drops the task being decided, so its rollouts are not counted twice (once in
the prior, once in the likelihood).

Factors used for the frozen route:

| Family | $\gamma \pm s_\gamma$ | Notes |
|---|---|---|
| Comet `pt50` | 0.55 ± 0.09† | ratio estimator, leave-one-task-out |
| 2025 winner | 0.81 ± 0.10† | fixed before stage 2 and used for stage 2 |
| 2025 winner, empirical Bayes | 0.69 ± 0.11† | estimate from an early subset of winner rollouts; reported for comparison |

`pt12` has no published per-task results of its own and borrows the Comet reference scores†. The
reference tables are not redistributed, so these priors cannot be rebuilt from `data/`.

## Paired policy levels (tasks 50–99)

Tasks 50–99 are new in 2026 and have no per-task reference scores. Each policy gets a *level*
instead, estimated with the decided task $t$ left out.

**Reference level.** The reference policy `s150997` has eligible rollouts on every task.
`policy_level(scores, leave_out=t)` is the mean of its per-task means over the $m$ other tasks:

$$\ell_{\mathrm{ref},-t} = \frac{1}{m}\sum_{u \ne t} \bar y_{u,\mathrm{ref}}, \qquad \mathrm{se}_{\mathrm{ref}} = \sqrt{\max(v,\ 10^{-4}) / m},$$

where $v$ is the sample variance of the per-task means. With a single task, $v = 0.1^2$. With none,
`policy_level` returns `None`.

**Candidate level.** `paired_level(candidate, reference, leave_out=t)` adds the candidate's mean
paired difference over $S_{p,-t}$, the tasks other than $t$ on which both policies have rollouts:

$$\bar d = \frac{1}{|S_{p,-t}|} \sum_{u \in S_{p,-t}} \left(\bar y_{up} - \bar y_{u,\mathrm{ref}}\right), \qquad \ell_{p,-t} = \max\left(0,\ \ell_{\mathrm{ref},-t} + \bar d\right),$$

$$\mathrm{se}(\ell_{p,-t}) = \sqrt{\mathrm{se}_{\mathrm{ref}}^2 + \frac{\max(s_d,\ 0.05)^2}{|S_{p,-t}|}}.$$

Here $s_d$ is the sample standard deviation of the paired differences. The 0.05 floor applies to
$s_d$ before dividing by $|S_{p,-t}|$, not to the standard error. With a single shared task
$s_d = 0.25$. The level's mean is clipped at 0; its standard error is not. `paired_level` returns
`None` when there is no reference level or no shared task.

The two variances are added as if $\ell_{\mathrm{ref},-t}$ and $\bar d$ were independent. They are
not (both contain the reference's per-task means), and the sign of the neglected covariance depends
on the data, so the formula is not conservative in general. In the worked example below every other
task is shared, so the level equals the candidate's own mean over those 49 tasks: the formula gives
a standard error of 0.0353, while the standard error of that mean is 0.0361.

**Prior.** `flat_level_prior(level, shrink_to=HYPERPRIOR, between_task_sd=0.1)` shrinks the level
toward the weak hyperprior $\mathcal N(0.1, 0.1^2)$ and then widens it by the between-task standard
deviation $\tau_b = 0.1$, because a policy's score on one task varies around its level:

$$\mathcal N(m, s^2) = \mathrm{combine}\left(\ell_{p,-t},\ \mathcal N(0.1, 0.1^2)\right), \qquad \mu_{tp} = m, \qquad \tau_{tp} = \sqrt{s^2 + \tau_b^2}.$$

With `level=None` the prior is the hyperprior widened, $\mathcal N(0.1, 0.141^2)$. The reference
policy's prior uses its own `policy_level`; every other candidate uses `paired_level` against the
reference.

The original pipeline also pooled each level with the other step of the same training run†. The
reimplementation uses the hyperprior only.

## Switching rules

`Rules` holds the thresholds; `STRICT = Rules()` is the configuration used for the frozen route.
`decide(task_id, fallback, priors, dev, noise, rules=STRICT, guarded=True)` updates every candidate's
prior with its rollouts on the task, flags challengers that break a rule (the incumbent is never
flagged), sorts candidates by posterior mean, highest first, with ties broken by policy name, and
switches to the first unflagged challenger in that order only if its posterior gain over the
incumbent clears the margin. It raises `ValueError` if the incumbent has no prior. The rules differ
by task range.

### Tasks 0–49 (`guarded=True`)

These rules applied to the 13 stage-2 tasks from 0–49. Each had an incumbent (`fallback`) from an
earlier route: `pt50` on 9 tasks, `winner2` on 3, `pt12` on 1. A challenger must pass every rule:

1. **Own evidence.** At least `min_own_rollouts = 2` of its own rollouts on the task.
2. **Development guard** (`dev_guard = True`). At least `min_shared = 2` development instances that
   both it and the incumbent ran, and on those instances its mean (of per-instance means) must be
   strictly greater than the incumbent's. With `min_shared = 0` and no shared instance the
   comparison is skipped and the guard passes.
3. **Margin.** A posterior gain of at least `switch_margin = 0.01` over the incumbent.
4. **Veto.** Rejected if all of its rollouts scored 0 on every shared instance where the incumbent's
   best score was above `veto_ref_above = 0.1` (the rule applies only when at least one such
   instance exists).

The 37 stage-1 tasks had no incumbent (their `fallback` in `route.json` is `null`); see
[Two-stage freeze](#two-stage-freeze).

### Tasks 50–99 (`guarded=False`, via `select_by_level`)

The incumbent is the reference policy `s150997`, which is weak, so the own-evidence rule and the
development guard are switched off: the challenger with the highest posterior among those not vetoed
replaces the reference if it clears the margin. The rules:

1. **Margin.** Its posterior gain over the reference is at least 0.01.
2. **Veto.** Same rule as above, against the reference's scores on shared instances.
3. **Scope.** A specialist is a candidate only on tasks where it has its own rollouts, and only if it
   has at least `min_policy_rollouts = 2` rollouts in total in the ledger. Generalists are candidates
   everywhere (the reference always; another generalist if it has any rollouts).
4. **One checkpoint per training run.** See the next section.

## One checkpoint per training run

`select_by_level(tasks, dev, reference, generalists, specialists=(), family=None, rules=STRICT,
min_policy_rollouts=2)` takes a map from policy label to a training-run id (the parameter is named
`family`). Two checkpoints of the same training run should not both be served, because each routed
policy needs its own serving image and the two steps are close substitutes.

The search:

1. Decide every task with all candidates allowed.
2. While some training run has more than one of its checkpoints in the route, take the first such run
   and try every one of its still-allowed checkpoints as the keeper, including checkpoints that won
   no task: remove the other checkpoints of that run, re-decide every task, and score the trial route
   by the sum over tasks of the chosen policy's posterior mean. Keep the trial with the highest total
   (the first in sorted label order on a tie) and repeat.
3. The reference policy is never removed, even if it appears in the map.

The keeper search is exhaustive within one run, but runs are resolved one at a time (greedily), so
with several crowded runs the result is not guaranteed to be jointly optimal. In the release the map
is `{"comet@ymetz6000": "ymetz", "comet@ymetz9999": "ymetz"}`: two steps of one public training run,
and the only group. Winner-format specialists are not in the map and are never merged. On the
released stage-2 ledger the unconstrained pass picks `comet@ymetz6000` on 2 tasks and
`comet@ymetz9999` on 39; the search keeps `comet@ymetz9999`, which ends up on 40 tasks.

`one_per_family(decisions, family)` is a quick heuristic kept for inspection (it maps each chosen
policy to the group member with the largest summed gain on the tasks it won). `select_by_level` does
not use it.

## Two-stage freeze

Evaluation compute was the binding constraint, so the route was frozen in two stages. Reported
instances 301–310 were never an input to a routing decision.

| | Stage 1 | Stage 2 |
|---|---|---|
| Tasks | 37, all from 0–49 | 63: 13 from 0–49 and all 50 from 50–99 |
| Selection | earlier route writer: posterior ranking with the same priors, no guard rules† | development posterior: transfer priors (winner factor 0.81†) and guarded rules on 0–49, level-based priors and rules on 50–99 |
| Incumbent (`fallback`) | none | `pt50`, `winner2`, `pt12` on 0–49; `s150997` on 50–99 |
| Evidence cutoff | reported runs began 2026-10-11 (first reported finish 03:04:21 UTC; `analysis.STAGE1_START_UTC = 2026-10-11T03:00:00Z`) | frozen 2026-10-13T12:54:00Z (07:54 CDT; `analysis.FREEZE_UTC`) |
| Reported episodes finished | 2026-10-11T03:04:21Z to 2026-10-11T22:24:02Z | 2026-10-13T13:10:30Z to 2026-10-14T06:38:00Z |

For 25 of the 37 stage-1 tasks, the routed policy had no eligible development rollouts of its own on
the task that finished at or before `analysis.STAGE1_START_UTC`, so its expected score rested on its prior
alone (`calibration_breakdown()["routed_with_zero_own_stage1"]`).

Development evidence at the stage-2 freeze:

| Count | Value |
|---|---|
| Eligible rollouts in the released ledger (all finish times) | 800 |
| ... finished at or before the freeze | 724 |
| ... of those, on tasks 50–99 (used by `select` and the simulation) | 411 |
| ... of those, in candidate cells (the simulation template; see [simulation.md](simulation.md)) | 360 |
| Rows of the original pipeline's development table at freeze | 860† |

The 860† rollouts are the original pipeline's table and cannot be reconciled row by row with the
released ledger.

Each stage's route table was hashed before its reported runs. `data/route.json` records the SHA-256
of both original tables and the canonical hash of the final route; see [data.md](data.md#hashes).

## Worked example: `comet@ymetz9999` on task 69

Task 69 is `vacuuming_floors`. The ledger is the 411 eligible rollouts on tasks 50–99 that finished
at or before the freeze (`policybank.analysis._stage2_setup()`). `worked_example()` in
`tools/make_tables.py` computes the same quantities for the paper.

| Step | Value |
|---|---|
| Reference level $\ell_{\mathrm{ref},-69}$ (`s150997`, 49 other tasks) | 0.0498 ± 0.0144 |
| Shared tasks $\lvert S\rvert$, mean paired difference $\bar d$, s.d. $s_d$ | 49, +0.1294, 0.2257 |
| Level $\ell_{p,-69} = 0.0498 + 0.1294$, s.e. $\sqrt{0.0144^2 + 0.2257^2/49}$ | 0.1792 ± 0.0353 |
| Combined with $\mathcal N(0.1, 0.1^2)$ | 0.1704 ± 0.0333 |
| Prior after widening by $\tau_b = 0.1$ | 0.1704 ± 0.1054 |
| Rollout variance: 73 rollouts on 50 tasks, $\mathrm{SS} = 2.1414$, $\mathrm{df} = 23$, so $(2.1414 + 4 \cdot 0.08)/(23 + 4)$ | 0.0912 |
| Own rollouts on task 69 | one, scored 0.0 |
| Posterior: precisions 90.02 (prior) and 10.97 (data), mean $0.1704 \cdot 90.02 / 100.99$ | 0.152 ± 0.100 |

The reference policy on the same task has prior 0.051 ± 0.101 (its own `policy_level` over the 49
other tasks, combined and widened the same way), rollout variance 0.0194 and three rollouts at 0.0,
giving a posterior of 0.020 ± 0.063. `comet@ymetz9999` beats it by +0.132, above the 0.01 margin,
and no veto applies (the reference scored 0 on every instance), so the task is routed to
`comet@ymetz9999`, as in the frozen route. (`comet@ymetz6000` is not a candidate after the
one-checkpoint-per-training-run search.)

To reproduce:

```python
from policybank.analysis import _stage2_setup
from policybank.selection import flat_level_prior, noise_variance, paired_level, per_task_scores, update

dev, _ = _stage2_setup()
sc = per_task_scores(dev)
level = paired_level(sc["comet@ymetz9999"], sc["s150997"], leave_out=69)   # 0.179±0.035
prior = flat_level_prior(level)                                             # 0.170±0.105
nv = noise_variance(sc["comet@ymetz9999"])                                  # 0.0912
post = update(prior, sc["comet@ymetz9999"][69], nv)                         # 0.152±0.100
```

The original pipeline also pooled the level with the other step of the same training run. Its
candidate report of 12 October gave a prior of 0.184 ± 0.111† moving to 0.160† for the same rollout
(`tests/test_selection.py` checks that arithmetic with a rollout variance of 0.0822†). The frozen
stage-2 table of 13 October, built from more rollouts, records `expected_q = 0.166` for task 69 in
`data/route.json`. The reimplementation's 0.152 is not expected to match it: it does not pool the two
steps, and the pipeline's development table was not the released ledger.

## Hyperparameters

Defaults in the released code. "Used by" names the function or field that holds the value.

| Quantity | Symbol | Value | Used by |
|---|---|---|---|
| Default rollout variance | $\sigma_0^2$ | 0.08 | `noise_variance(default=)`; also the fallback in `decide` for a policy missing from `noise` |
| Pseudo-degrees of freedom | $\nu_0$ | 4.0 | `noise_variance(prior_dof=)` |
| Rollout-variance floor | | 0.01 | `noise_variance(floor=)` |
| Task-specific spread around a transferred score | $b$ | 0.088 | `transfer_prior(base_sd=)` |
| Transfer-factor s.e. floor | | 0.001 | `estimate_transfer_factor` |
| Hyperprior on a policy level | | $\mathcal N(0.1, 0.1^2)$ | `HYPERPRIOR`, `flat_level_prior(shrink_to=)` |
| Between-task s.d. added to a level | $\tau_b$ | 0.1 | `flat_level_prior(between_task_sd=)` |
| Floor on the s.d. of paired differences | | 0.05 | `paired_level` |
| S.d. of paired differences with one shared task | | 0.25 | `paired_level` |
| Lower clip of a candidate level | | 0 | `paired_level` |
| S.d. of per-task means when a policy ran one other task (so the level s.e. is 0.1) | | 0.1 | `policy_level` |
| Floor on the variance of per-task means | | $10^{-4}$ | `policy_level` |
| Switch margin | | 0.01 | `Rules.switch_margin` |
| Own rollouts required (tasks 0–49) | | 2 | `Rules.min_own_rollouts` |
| Development guard on, shared instances required (tasks 0–49) | | `True`, 2 | `Rules.dev_guard`, `Rules.min_shared` |
| Veto threshold on the incumbent's score | | 0.1 | `Rules.veto_ref_above` (`None` disables) |
| Minimum total rollouts for a specialist (tasks 50–99) | | 2 | `select_by_level(min_policy_rollouts=)` |
| Reference policy (tasks 50–99) | | `s150997` | `analysis.reproduce_stage2` |
| Generalists (tasks 50–99) | | `s150997`, `comet@ymetz6000`, `comet@ymetz9999` | `analysis.reproduce_stage2` |
| Specialists (tasks 50–99) | | every label starting with `w100@` in the stage-2 ledger (11; 9 have at least 2 rollouts) | `analysis.reproduce_stage2` |
| Training-run map (the only group) | | `comet@ymetz6000`, `comet@ymetz9999` → `ymetz` | `analysis.reproduce_stage2`, `analysis._stage2_setup` |
| Tie-break when posterior means are equal | | policy name | `decide` |
| Transfer factor, Comet `pt50` | $\gamma$ | 0.55 ± 0.09† | not in the release |
| Transfer factor, 2025 winner (used for stage 2) | $\gamma$ | 0.81 ± 0.10† | not in the release |
| Transfer factor, winner empirical-Bayes estimate | $\gamma$ | 0.69 ± 0.11† | not in the release |
| Rollouts in the original stage-2 table at freeze | | 860† | not in the release |

† From pipeline logs; not recomputable from the release.
