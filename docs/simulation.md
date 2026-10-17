# Posterior-predictive simulation

The frozen route could be scored only once. `policybank.simulate` asks counterfactual questions about
the selection procedure with a model fitted to the team's own data:

- How optimistic should the selector's expected scores be, given how it chooses?
- How do the strict switching rules compare with simpler rules (reference only, best raw development
  mean, best posterior) and with an oracle?
- How much would a larger development budget have bought?

The study covers tasks 50–99, whose priors are built entirely from released development data. Tasks
0–49 need the unreleased 2025 reference tables. All numbers below come from
`results/summary.json["simulation"]` unless marked otherwise.

## What is simulated

**Ledger and candidates.** The study starts from the same evidence as the stage-2 reproduction
(`policybank.analysis._stage2_setup()`): the 411 eligible development rollouts on tasks 50–99 that
finished at or before the freeze (2026-10-13T12:54:00Z). `Setup.from_ledger` applies the scope rule:

- the reference `s150997` and the generalists `comet@ymetz6000` and `comet@ymetz9999` are candidates on
  every task;
- each `w100@` specialist with at least two rollouts in the ledger (9 of the 11 `w100@` labels) is a
  candidate only on the tasks it ran;
- the training-run map is `{comet@ymetz6000, comet@ymetz9999} -> ymetz`, the only group.

The **template** keeps the rows whose (task, policy) is a candidate cell: 360 of the 411 rows. The
other 51 rows are dropped: 49 rows of `pt12`, which is not a candidate on tasks 50–99, and one row
each of the two `w100@` labels with a single rollout. Every simulated ledger has exactly the
template's cells and counts.

**One world** (`run_study`, repeated `sims` times with `random.Random(seed)`):

1. **Truth.** `posterior_truth` computes the selector's own posterior mean and s.d. for every
   (task, candidate) cell on the real ledger, with the same priors and rollout variances that
   `select_by_level` uses. `draw_world` draws a true score
   $\theta_{tp} \sim \mathcal N(\text{mean}, \text{sd}^2)$ independently per cell and clips it to
   $[0, 1]$.
2. **Development rollouts.** `draw_ledger` redraws every template row from the outcome model below,
   given the cell's $\theta$. With `replicate = m` the template is repeated $m$ times (instances
   shifted by 100 per copy) to emulate an $m$-times larger budget.
3. **Rules.** Each of the five rules picks a policy per task from the simulated ledger and, where it
   has one, states the score it expects (its claim).
4. **Scoring.** For each rule the study records the true score of the route it picked, its claim,
   its regret against the oracle, the raw development mean of the picked policies, and one simulated
   reporting run of ten fresh episodes per task.

All five rules see the same worlds and the same simulated ledgers, so differences between rules are
paired.

## Outcome model

Real episode scores are exactly 0 far more often than a Beta distribution allows: 63.6% of the 1,000
reported episodes and 74.0% of the 411 development rows score 0. The veto rule reacts only to exact
zeros, so the simulation needs them. `simulation_study` therefore uses a zero-inflated Beta
(`ZeroInflatedOutcome`):

$$P(q = 0) = \pi_0 = (1 - \theta)^c, \qquad q \mid q > 0 \sim \mathrm{Beta}\left(m\kappa,\ (1 - m)\kappa\right), \qquad m = \frac{\theta}{1 - \pi_0},$$

so the mean score is $\theta$. If $m$ would exceed 0.98 it is capped at 0.98 and $\pi_0$ is lowered
to keep the mean; $\theta$ is clamped to $[0, 0.995]$.

`fit_zero_inflated` fits both parameters to the reported episodes:

- $c$ by least squares between each task's share of zeros and $(1 - \bar q_t)^c$, over tasks whose
  mean $\bar q_t$ is strictly between 0 and 1, on the grid 0.5, 0.55, ..., 20.45;
- $\kappa$ by the method of moments on each task's nonzero scores (tasks with at least two), pooled:
  $\kappa = \sum_t m_t(1 - m_t) / \sum_t s_t^2 - 1$, floored at 0.05, where $m_t$ and $s_t^2$ are the
  mean and sample variance of task $t$'s nonzero scores (if those scores never vary, $\kappa = 2$).

| Parameter | Value |
|---|---|
| $c$ (`zero_c`) | 4.0 |
| $\kappa$ (`kappa`) | 6.42 |

Reported episodes mix instance difficulty with rollout randomness, so the fitted spread is, if
anything, too wide for repeated rollouts on one instance.

The plain Beta model, $q \sim \mathrm{Beta}(\theta\kappa, (1-\theta)\kappa)$, is also available
(`fit_beta_concentration`, `BetaOutcome`; its moment fit on the reported episodes gives
$\kappa = 1.48$). It is used below as a sensitivity check. Neither outcome model is Gaussian, so the
study also probes the selector's Gaussian likelihood.

## The five rules

| Key in `RULES` | Picks | Claims |
|---|---|---|
| `reference only` | `s150997` on every task | nothing |
| `best dev mean` | the candidate with the highest raw development mean on the task (the reference, with claim 0, if no candidate has rollouts; on tasks 50–99 the reference always has some) | that raw mean |
| `best posterior` | `select_by_level` with `Rules(min_own_rollouts=0, dev_guard=False, switch_margin=0.0, veto_ref_above=None)` and no training-run consolidation: the highest posterior | its posterior mean |
| `strict rules (ours)` | `select_by_level` with `Rules()` and the training-run map: margin 0.01, veto, scope, one checkpoint per training run | its posterior mean |
| `oracle` | the candidate with the highest true score | the true score |

Both posterior rules call `select_by_level`, which decides tasks 50–99 with `guarded=False`, so the
own-evidence rule and the development guard play no part here (see [method.md](method.md#switching-rules)).
The scope rule applies to both, because it defines the candidate sets.

## Outputs

`run_study` returns, per rule:

| Key | Meaning |
|---|---|
| `true` | mean over worlds of the true score of the picked route (mean over the 50 tasks) |
| `true_p05`, `true_p95` | 5th and 95th percentiles of that score across worlds (the "90% range") |
| `claimed` | mean over worlds of the rule's claimed route score (`None` for `reference only`) |
| `optimism` | `claimed - true` (`None` without claims) |
| `raw_dev_gap` | raw development mean of the picked policies minus their true score, averaged over tasks where the picked policy has simulated rollouts: the selection bias a naive reader of the ledger would see |
| `regret` | oracle `true` minus the rule's `true` |
| `reported` | sorted simulated reporting runs (ten fresh episodes per task); used for the observed percentile and then removed from the summary |

`simulation_study` adds:

- `curve`: `true` and its 90% range for `strict rules (ours)`, `best dev mean` and `oracle` at budget
  multipliers 1 (the main run), 2, 4 and 8 (`curve_sims` worlds each, seed `seed + m`);
- `observed`: the real counterparts on the same 50 tasks: the frozen route's mean `expected_q`
  (`claimed`), the realized mean score over instances 301–310 (`realized`), their difference
  (`optimism`), the routed policies' raw development mean on the pre-freeze ledger
  (`raw_dev_mean_routed`, over the `tasks_with_dev` tasks where the routed policy has rollouts) minus
  the realized score on those tasks (`realized_on_those`), stored as `raw_dev_gap`, and where the
  realized score falls among the simulated reporting runs of the strict rule (`reported_percentile`,
  the share of runs at or below it, with that distribution's 5th and 95th percentiles
  `reported_p05`, `reported_p95`);
- `kappa`, `zero_c`, `sims`, `template_rollouts`, `zero_share_official`, `zero_share_dev`.

## Results (300 worlds, seed 0)

Main study, zero-inflated outcome model:

| Rule | True | 90% range | Claimed | Optimism | Raw gap | Regret |
|---|---|---|---|---|---|---|
| Reference only | 0.062 | 0.052–0.073 | – | – | −0.001 | 0.167 |
| Best raw development mean | 0.182 | 0.158–0.204 | 0.299 | +0.117 | +0.117 | 0.047 |
| Best posterior, no rules | 0.196 | 0.173–0.218 | 0.198 | +0.002 | +0.079 | 0.033 |
| Strict rules (ours) | 0.186 | 0.153–0.211 | 0.189 | +0.002 | +0.045 | 0.043 |
| Oracle | 0.229 | 0.212–0.248 | 0.229 | +0.000 | −0.001 | 0.000 |

The reference-only rule and the oracle do not choose from the simulated ledger, so their raw gap is
zero up to Monte Carlo error; the paper's table prints "–" for them. For `best dev mean` the claim is
the raw mean itself, so its optimism and raw gap coincide.

Budget curve (true score with its 90% range; the 1× point is the main run, 300 worlds with seed 0;
2×, 4× and 8× use 120 worlds each with seeds 2, 4 and 8):

| Budget | Strict rules (ours) | Best raw development mean | Oracle |
|---|---|---|---|
| 1× | 0.186 (0.153–0.211) | 0.182 (0.158–0.204) | 0.229 (0.212–0.248) |
| 2× | 0.190 (0.163–0.212) | 0.200 (0.178–0.220) | 0.229 (0.212–0.245) |
| 4× | 0.195 (0.175–0.217) | 0.212 (0.194–0.230) | 0.230 (0.214–0.245) |
| 8× | 0.197 (0.174–0.215) | 0.219 (0.198–0.236) | 0.229 (0.211–0.244) |

Observed on the same 50 tasks:

| Quantity | Value |
|---|---|
| Claimed (mean frozen `expected_q`) | 0.203 |
| Realized (instances 301–310) | 0.151 |
| Optimism | 0.052 |
| Raw development mean of the routed policies (all 50 tasks have rollouts) | 0.213 |
| Raw development mean minus realized | 0.062 |
| Percentile of the realized score among simulated reporting runs of the strict rule | 4th (`reported_percentile` = 0.04) |
| 5th–95th percentile of those simulated reporting runs | 0.153–0.214 |

Sensitivity: plain Beta outcome model ($\kappa = 1.48$), same setup, 300 worlds, seed 0 (computed with
`run_study(setup, dev, fit_beta_concentration(official), sims=300, seed=0)`; not part of
`summary.json`):

| Rule | True | Claimed | Optimism | Raw gap | Regret |
|---|---|---|---|---|---|
| Reference only | 0.063 | – | – | +0.001 | 0.166 |
| Best raw development mean | 0.191 | 0.312 | +0.121 | +0.121 | 0.039 |
| Best posterior, no rules | 0.192 | 0.195 | +0.003 | +0.090 | 0.037 |
| Strict rules (ours) | 0.186 | 0.188 | +0.003 | +0.051 | 0.044 |
| Oracle | 0.229 | 0.229 | +0.000 | +0.001 | 0.000 |

## How to interpret it

- **Claims, within the model.** The posterior rules claim almost exactly what they deliver (optimism
  +0.002 for both). This is close to guaranteed by construction: the true scores are drawn from the
  selector's own posterior, so the posterior is the correct belief whenever its Gaussian likelihood
  is adequate. It shows that the selection step adds little bias on top of the posterior. It does not
  show that the priors themselves are right.
- **Raw means overclaim.** Picking the highest raw development mean claims 0.299 for a route worth
  0.182 (+0.117; +0.121 under the plain Beta). Shrinkage is what keeps the claims honest.
- **What the rules buy.** Against the unconstrained posterior, the strict rules give up 0.010 of true
  score (0.186 against 0.196), and they cut the raw selection bias of the policies they pick by about
  43% (0.079 to 0.045; 0.090 to 0.051 under the plain Beta). Their intended value lies
  outside the model: broken ports, porting errors and outcome distributions the model misses.
- **Raw means versus the strict rules on true score depends on the outcome model.** At the real
  budget, raw-mean selection is slightly worse than the strict rules under the zero-inflated model
  (0.182 against 0.186) and slightly better under the plain Beta (0.191 against 0.186). The
  differences are small next to the 90% ranges. What does not depend on the model is the size of the
  claims: raw means overclaim by about 0.12, the posterior rules by about 0.002–0.003.
- **The candidate pool is the limit.** An oracle choosing among the same candidates reaches 0.229,
  0.043 above the strict rule on these 50 tasks, or about 0.02 in $Q$ over 100 tasks.
- **More evidence.** With eight times the development budget the strict rule reaches 0.197 and raw-mean
  selection 0.219; raw means overtake the strict rule from 2× on. The curve does not include the
  unconstrained posterior. Rerunning the 8× point with all five rules
  (`run_study(setup, dev, fit_zero_inflated(official), sims=120, seed=8, replicate=8)`, not part of
  `summary.json`) gives it 0.219, so at that budget the gap comes from the margin, the veto and the
  one-checkpoint-per-training-run constraint, not from shrinkage.
- **The observed score.** The frozen route claimed 0.203 on these tasks and realized 0.151, at the 4th
  percentile of the strict rule's simulated reporting runs (just below their 5th percentile, 0.153).
  Either the reported run was unlucky or the model is optimistic. Together with the calibration
  analysis in the paper (the gap sits in tasks decided by a prior or a single rollout), the likelier
  reading is that policy levels estimated from mostly single rollouts, concentrated on instance 313,
  were too high, which this study cannot detect because it takes those levels as the truth.

## How to run

A quick run with few worlds:

```bash
python -m policybank simulate --sims 40 --curve-sims 10
```

```text
posterior-predictive study, tasks 50-99, 40 worlds, kappa=6.42
rule                     true Q       90% range  claimed  optimism  regret
reference only            0.063   0.055-0.072        -         -   0.168
best dev mean             0.183   0.160-0.202    0.303    +0.120   0.048
best posterior            0.199   0.173-0.224    0.201    +0.002   0.032
strict rules (ours)       0.189   0.156-0.213    0.191    +0.003   0.042
oracle                    0.231   0.215-0.249    0.231    +0.000   0.000
observed: claimed 0.203, reported 0.151 (percentile 2 of simulated reporting runs)
```

With 40 worlds the numbers differ from the Results above by Monte Carlo error. The paper and
`results/summary.json` use the defaults (`--sims 300 --curve-sims 120 --seed 0`); plain
`python -m policybank simulate` prints the main Results table above, with percentile 4, in under a
minute on a laptop CPU. The command prints the main study only; the budget curve is computed but
appears only in `python -m policybank analyze` and `results/summary.json`. Results are deterministic
for a given `--sims`, `--curve-sims` and `--seed`.

From Python, with a custom rule or outcome model:

```python
from policybank import data as D
from policybank.analysis import _stage2_setup, simulation_study
from policybank.simulate import RULES, fit_beta_concentration, fit_zero_inflated, run_study

full = simulation_study(sims=300, curve_sims=120, seed=0)        # what summary.json holds

dev, setup = _stage2_setup()                                      # 411 rows, 360-row template
official = D.load_official()
zi = run_study(setup, dev, fit_zero_inflated(official), sims=300, seed=0)
beta = run_study(setup, dev, fit_beta_concentration(official), sims=300, seed=0)   # plain Beta
mine = run_study(setup, dev, fit_zero_inflated(official), sims=100,
                 rules={"strict": RULES["strict rules (ours)"], "oracle": RULES["oracle"]})
```

A rule is any callable `(setup, ledger, world) -> (pick, claim)` returning a policy per task and,
optionally, a claimed score per task.

## Limitations

- **The truth is the selector's own posterior.** Self-consistency of the posterior's claims is nearly
  automatic, and the study cannot detect priors or levels that are wrong in the same direction for
  every task, which is what the observed result suggests.
- **Tasks 50–99 only.** The transfer priors of tasks 0–49 depend on unreleased reference tables.
- **Fixed design.** Simulated ledgers reuse the real cells and counts. Instance effects are not
  modeled: every rollout is an independent draw given $\theta$, so the concentration of real rollouts
  on instance 313 and instance-to-instance difficulty play no role.
- **One outcome model at a time.** $c$ and $\kappa$ are pooled across tasks and policies and fitted on
  reported episodes. Results that depend on the outcome model (raw means versus strict rules on true
  score) are reported for both models above.
- **Independent cells.** True scores are drawn independently per (task, candidate) cell from the
  marginal posteriors, so the correlation that a shared policy level induces across a policy's tasks
  is ignored.
- **Clipping.** True scores drawn from the Gaussian posterior are clipped to $[0, 1]$, which piles
  mass at 0 for weak cells.
- **What is not modeled.** Porting errors, broken checkpoints, simulator-version shift between
  development and hidden evaluation, and the adaptive way development rollouts were actually
  allocated.
- **Monte Carlo error.** 300 worlds for the main study and 120 per budget multiplier. Differences of a
  few thousandths between rules should not be over-read.
