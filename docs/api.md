# API reference

Module-by-module reference for the public API of `policybank` 1.0.0. Signatures were generated with
`inspect.signature` from the current code; annotations are shown as written in the source, and two
long defaults are abbreviated: `(301, ..., 310)` is `REPORT_INSTANCES` and `Rules(...)` is `STRICT`
(`Rules()`). Names starting with an underscore are private and may change.

- [`policybank`](#policybank) (constants)
- [`policybank.data`](#policybankdata)
- [`policybank.metrics`](#policybankmetrics)
- [`policybank.selection`](#policybankselection)
- [`policybank.simulate`](#policybanksimulate)
- [`policybank.routing`](#policybankrouting)
- [`policybank.provenance`](#policybankprovenance)
- [`policybank.analysis`](#policybankanalysis)
- [`policybank.serving`](#policybankserving): [`codec`](#policybankservingcodec),
  [`contract`](#policybankservingcontract), [`executor`](#policybankservingexecutor),
  [`server`](#policybankservingserver), [`client`](#policybankservingclient),
  [`remote`](#policybankservingremote)
- [`policybank.cli`](#policybankcli)

Everything needs only `numpy` and `msgpack`, except `PolicyServer.serve`, `PolicyClient` and
`OpenPIRemotePolicy`, which import `websockets>=13` when they run (`pip install -e ".[serve]"`).

## `policybank`

| Name | Value |
|---|---|
| `__version__` | `"1.0.0"` |
| `N_TASKS` | `100` |
| `REPORT_INSTANCES` | `(301, ..., 310)`: reporting instances |
| `DEV_INSTANCES` | `(311, ..., 320)`: development instances |
| `HIDDEN_INSTANCES` | `(321, ..., 340)`: hidden-evaluation instances (organizers only) |

## `policybank.data`

Loaders for the released dataset. See [data.md](data.md) for every field.

**`DATA_DIR`** — the active dataset directory: `$POLICYBANK_DATA` if it was set at import, else the
repository's `data/`.

**`set_data_dir(path: Path | str) -> None`**
Points every loader, and the analyses built on them, at another dataset directory. The CLI's
top-level `--data DIR` calls this.

**`class Episode(task_id: int, task: str, instance: int, policy: str, q: float, success: bool, steps: int = 0, normalized_time: float = 0.0, run: str = '')`**
Frozen dataclass for one evaluator rollout of a (task, instance) cell. `run` is set for development
rows. Property **`timed_out`** is `True` when the episode failed and `normalized_time <= 0.6670`, that
is, it ran to the step cap of 1.5 times the mean demonstration length.

**`load_json(name: str, data_dir: Path | None = None)`**
Parses `<data_dir>/<name>` (`data_dir` defaults to `DATA_DIR`). A missing file raises
`FileNotFoundError` with a message that explains `--data` and `POLICYBANK_DATA`.

**`load_tasks(data_dir: Path | None = None) -> list[dict]`** — `tasks.json`.

**`load_policies(data_dir: Path | None = None) -> dict[str, dict]`** — `policies.json`.

**`load_route(data_dir: Path | None = None) -> dict`** — `route.json`, as a plain dict.

**`load_official(data_dir: Path | None = None) -> list[Episode]`**
The 1,000 reported episodes from `official_episodes.csv`.

**`load_dev(data_dir: Path | None = None, *, selection_only: bool = False) -> list[Episode]`**
Rows of `dev_rollouts.csv` (1,146). With `selection_only=True`, only the rows the selection could use
(800): `dev_split` is 1, `variant` is not 1, `nondefault_config` is not 1, and the policy label is not
`unlabelled`, `pt50-sweep` or `ft-sweep`.

## `policybank.metrics`

Challenge scoring and power calculations. A missing (task, instance) cell counts as zero, so per-task
means always divide by the contract's instance count.

**`task_means(episodes: Iterable[Episode], n_instances: int = 10, *, instances: Sequence[int] | None = (301, ..., 310), n_tasks: int = 100) -> dict[int, float]`**
Per-task mean `q` with missing instances counted as zero (sum divided by `n_instances`). Raises
`ValueError` for a task id outside `0..n_tasks-1`, an instance outside `instances` (pass
`instances=None` to allow any), a duplicate (task, instance) cell, or `q` outside $[0, 1]$. Tasks
without episodes are absent from the result.

**`challenge_q(episodes: Iterable[Episode], n_tasks: int = 100, n_instances: int = 10) -> float`**
The challenge score $Q$: the sum of `task_means` divided by `n_tasks`, so absent tasks score zero.
`task_means` is called with its default `instances`, so only reporting instances are accepted.

**`success_rate(episodes: Sequence[Episode]) -> float`**
Share of episodes with `success`; `nan` for an empty sequence.

**`bootstrap_q(episodes: Sequence[Episode], n_boot: int = 10000, seed: int = 0, alpha: float = 0.05, n_instances: int = 10, n_tasks: int = 100, rescale: bool = True) -> tuple[float, float, float]`**
Returns `(Q, lo, hi)`: the point estimate (`challenge_q`) and a percentile interval from a
task-stratified bootstrap that resamples each task's scores, padded with zeros to `n_instances`, using
`random.Random(seed)`. The result does not depend on episode order or instance labels. With `rescale`,
each resampled task mean's deviation from the observed mean is multiplied by $\sqrt{k/(k-1)}$ for $k$
scores, undoing the plain bootstrap's variance shrinkage. The interval covers instance and rollout
variation only, not the route choice, a simulator change or the hidden-instance draw. Raises
`ValueError` if `n_boot < 1`.

**`within_task_sd(episodes: Iterable[Episode]) -> float`**
Pooled within-task standard deviation of `q` over tasks with at least two episodes; `nan` if there are
none. On the reporting set it mixes instance difficulty with rollout randomness (0.200).

**`rollouts_for_effect(delta: float, sd: float, alpha: float = 0.05, power: float = 0.8, paired_rho: float = 0.0) -> int`**
Rollouts per arm for a two-sided z-test to detect a mean difference `delta`:
$\lceil (z_{1-\alpha/2} + z_{\mathrm{power}})^2 \cdot 2 \mathrm{sd}^2 (1-\rho) / \delta^2 \rceil$. Pairing on shared
instances shrinks the variance of the difference by $(1-\rho)$.

**`rollouts_for_selection(delta: float, sd: float, p_correct: float = 0.8, paired_rho: float = 0.0) -> int`**
Rollouts per policy so that the policy with the higher sample mean is truly better with probability
`p_correct` (two policies, true difference `delta`, normal approximation):
$\lceil 2(1-\rho)(z_{p} \mathrm{sd}/\delta)^2 \rceil$. This is the question routing asks, and it needs far
fewer rollouts than a test.

## `policybank.selection`

The selector. [method.md](method.md) explains the model and rules.

**`class Gaussian(mean: float, sd: float)`**
Frozen dataclass. Raises `ValueError` unless `mean` is finite and `sd` is finite and positive.
Property **`precision`** is $1/\mathrm{sd}^2$. `str()` gives `mean±sd` to three decimals.

**`update(prior: Gaussian, scores: Sequence[float], noise_var: float) -> Gaussian`**
Conjugate Gaussian update of `prior` with `len(scores)` observations of variance `noise_var`. Returns
`prior` unchanged when `scores` is empty; raises `ValueError` if `noise_var <= 0`.

**`combine(*estimates: Gaussian) -> Gaussian`**
Precision-weighted combination of independent Gaussian estimates.

**`HYPERPRIOR`** — `Gaussian(mean=0.1, sd=0.1)`, the weak prior on a policy level.

**`transfer_prior(reference_q: float, factor: Gaussian, base_sd: float = 0.088) -> Gaussian`**
Prior from a public reference score scaled by an uncertain transfer factor: mean
`factor.mean * reference_q`, variance `(reference_q * factor.sd)**2 + base_sd**2`.

**`estimate_transfer_factor(own: Mapping[int, Sequence[float]], reference: Mapping[int, float], leave_out: int | None = None) -> Gaussian`**
Ratio estimator `sum(own task means) / sum(reference)` over tasks with a positive reference score and
at least one own rollout, excluding `leave_out`. The standard error is the delta-method one, floored at
0.001. Raises `ValueError` with fewer than two usable tasks.

**`per_task_scores(rows: Iterable[Episode]) -> dict[str, dict[int, list[float]]]`**
Groups `q` by policy, then task: `scores[policy][task_id] -> [q, ...]` (nested `defaultdict`s).

**`policy_level(scores: Mapping[int, Sequence[float]], leave_out: int | None = None) -> Gaussian | None`**
Mean of per-task means over tasks other than `leave_out`, with standard error
$\sqrt{\max(v, 10^{-4})/m}$ over $m$ tasks, where $v$ is the sample variance of the task means
($v = 0.1^2$ when $m = 1$). `None` if no task remains.

**`paired_level(candidate: Mapping[int, Sequence[float]], reference: Mapping[int, Sequence[float]], leave_out: int | None = None) -> Gaussian | None`**
The reference's `policy_level` plus the candidate's mean paired difference over the $k$ shared tasks
other than `leave_out`; the mean is clipped at 0. The standard error is
$\sqrt{\mathrm{se}_{\mathrm{ref}}^2 + \max(s_d, 0.05)^2/k}$, where $s_d$ is the s.d. of the differences
(0.25 when $k = 1$). `None` without a reference level or a shared task.

**`flat_level_prior(level: Gaussian | None, shrink_to: Gaussian = Gaussian(mean=0.1, sd=0.1), between_task_sd: float = 0.1) -> Gaussian`**
Task prior from a level: `combine(level, shrink_to)` (or `shrink_to` alone when `level` is `None`),
then the s.d. is widened by `between_task_sd` in quadrature.

**`noise_variance(scores: Mapping[int, Sequence[float]], default: float = 0.08, prior_dof: float = 4.0, floor: float = 0.01) -> float`**
Pooled within-task rollout variance of one policy, shrunk toward `default` with `prior_dof`
pseudo-degrees of freedom and floored at `floor`.

**`class Rules(min_own_rollouts: int = 2, dev_guard: bool = True, min_shared: int = 2, switch_margin: float = 0.01, veto_ref_above: float | None = 0.1)`**
Frozen dataclass of switching thresholds. `min_own_rollouts`: own rollouts a challenger needs on the
task. `dev_guard`: require the challenger's mean to beat the fallback's on the development instances
they share, with at least `min_shared` of them. `switch_margin`: minimum posterior gain.
`veto_ref_above`: veto a challenger that scored 0 on every shared instance where the fallback scored
above this value (`None` disables the veto). `min_own_rollouts` and `dev_guard` apply only when
`decide(guarded=True)`; the margin and the veto always apply.

**`STRICT`** — `Rules()`, the configuration of the frozen route.

**`class Candidate(policy: str, prior: Gaussian, n: int, dev_mean: float | None, posterior: Gaussian, flags: list[str] = <factory>)`**
One policy's evaluation on one task: prior, number and mean of its own rollouts, posterior, and the
rules it broke (`flags`, human-readable). Property **`eligible`** is `True` when `flags` is empty.

**`class Decision(task_id: int, fallback: str, choice: str, reason: str, candidates: list[Candidate])`**
The outcome for one task. `candidates` are sorted by posterior mean, highest first (ties broken by
policy label); `reason` explains the outcome. Property **`switched`** is `choice != fallback`. Method
**`expected(policy: str | None = None) -> float`** returns the posterior mean of `policy` (default: the
choice).

**`decide(task_id: int, fallback: str, priors: Mapping[str, Gaussian], dev: Sequence[Episode], noise: Mapping[str, float], rules: Rules = Rules(...), guarded: bool = True) -> Decision`**
Chooses a policy for one task. Every policy in `priors` is a candidate; its prior is updated with its
rows of `dev` on `task_id` using `noise[policy]` (0.08 if missing). Challengers are flagged by the
own-evidence and development-guard rules (only when `guarded`) and by the veto. The best unflagged
challenger replaces `fallback` if its posterior gain is at least `rules.switch_margin`. Raises
`ValueError` if `fallback` has no prior.

**`one_per_family(decisions: Sequence[Decision], family: Mapping[str, str]) -> dict[str, str]`**
Quick heuristic for inspection: maps each chosen policy to the member of its group (per `family`;
ungrouped policies are their own group) with the largest posterior gain over the fallback summed over
the tasks it won. `select_by_level` uses the exact search instead.

**`select_by_level(tasks: Sequence[int], dev: Sequence[Episode], reference: str, generalists: Sequence[str], specialists: Sequence[str] = (), family: Mapping[str, str] | None = None, rules: Rules = Rules(...), min_policy_rollouts: int = 2) -> list[Decision]`**
Routes tasks without public reference scores (tasks 50–99). The pool is every generalist and
specialist that is the reference or has rollouts in `dev`. Priors are `flat_level_prior` of
`paired_level` against `reference` (the reference uses its own `policy_level`), with the task left out;
noise variances are pooled per policy over `dev`. Generalists are candidates on every task; a
specialist only on tasks where it has rollouts, and only with at least `min_policy_rollouts` in total.
Each task is decided with `guarded=False` and `reference` as fallback. Then, while some group in
`family` (policy label to training-run id) has more than one member in the route, every allowed member
of the first such group is tried as the keeper (its siblings removed, all tasks re-decided) and the
trial with the highest total posterior mean is kept. The reference is never removed. Groups are
resolved one at a time, so with several crowded groups the result is not guaranteed to be jointly
optimal.

## `policybank.simulate`

Posterior-predictive simulation of the selection procedure on tasks 50–99. See
[simulation.md](simulation.md).

**`fit_beta_concentration(episodes: Sequence[Episode]) -> float`**
Method-of-moments Beta concentration $\kappa$ such that $\mathrm{var}(q \mid \mathrm{task}) = m(1-m)/(\kappa+1)$,
pooled over tasks with at least two episodes; floored at 0.05. Raises `ValueError` without
within-task variation.

**`class BetaOutcome(kappa: float)`**
Frozen dataclass outcome model: `draw(theta: float, rng: random.Random) -> float` returns a
$\mathrm{Beta}(\theta\kappa, (1-\theta)\kappa)$ draw, with $\theta$ clamped to $[0.005, 0.995]$. Never
exactly zero.

**`class ZeroInflatedOutcome(c: float, kappa: float)`**
Frozen dataclass outcome model: `draw(theta, rng)` returns exactly 0 with probability
$\pi_0 = (1-\theta)^c$, otherwise a Beta draw with concentration `kappa` and mean $\theta/(1-\pi_0)$, so
the overall mean is $\theta$ ($\theta$ is clamped to $[0, 0.995]$; if the nonzero mean would exceed 0.98
it is capped there and $\pi_0$ adjusted to keep the mean).

**`fit_zero_inflated(episodes: Sequence[Episode]) -> ZeroInflatedOutcome`**
Fits `c` by least squares of per-task zero fractions against $(1-m)^c$ over tasks with mean strictly
between 0 and 1 (grid 0.5, 0.55, ..., 20.45), and `kappa` by pooled moments on the nonzero scores of
tasks with at least two of them (floored at 0.05; 2.0 if there is no variation). Raises `ValueError` if
no task has a mean strictly between 0 and 1.

**`class Setup(tasks: list[int], reference: str, generalists: list[str], specialists: list[str], family: dict[str, str], template: list[Episode], candidates: dict[int, list[str]])`**
Dataclass describing one study. Classmethod
**`from_ledger(dev: Sequence[Episode], tasks: Sequence[int], reference: str, generalists: Sequence[str], specialists: Sequence[str], family: dict[str, str] | None = None) -> Setup`**
applies the scope rule: `specialists` keeps only those with at least two rollouts in total; the
candidates on a task are the generalists that are the reference or have any rollouts, plus the kept
specialists that ran that task. `template` keeps the rows of `dev` whose (task, policy) is a candidate
cell; it fixes the cells and counts that every simulated ledger reproduces.

**`posterior_truth(setup: Setup, dev: Sequence[Episode]) -> dict[tuple[int, str], tuple[float, float]]`**
The selector's posterior `(mean, sd)` for every (task, candidate) cell on the real ledger, built the way
`select_by_level` builds it (task left out of the level, pooled noise per policy).

**`draw_world(truth: dict, rng: random.Random) -> dict[tuple[int, str], float]`**
One world: a true score per cell drawn from $\mathcal N(\mathrm{mean}, \mathrm{sd}^2)$ and clipped to $[0, 1]$.

**`draw_ledger(setup: Setup, world: dict, kappa, rng: random.Random, replicate: int = 1) -> list[Episode]`**
Redraws every template row `replicate` times from the outcome model. `kappa` is either a number (a
`BetaOutcome` concentration) or an outcome model object. Copy `k` (from 0) shifts instances by
`100 * k`; `success` is `q >= 0.999`.

**`Rule`** — type alias: `Callable[[Setup, list[Episode], dict], tuple[dict[int, str], dict[int, float]]]`;
a rule returns `(pick, claim)` per task (`claim` may be `None`).

**`rule_reference(setup, dev, world)`** — always the reference; no claim.

**`rule_oracle(setup, dev, world)`** — the candidate with the highest true score; claims the truth.

**`rule_best_mean(setup, dev, world)`** — the candidate with the highest raw development mean on the
task (the reference with claim 0.0 if no candidate has rollouts); claims that mean.

**`RULES`** — the five rules of the study: `"reference only"`, `"best dev mean"`, `"best posterior"`
(`select_by_level` with `Rules(min_own_rollouts=0, dev_guard=False, switch_margin=0.0, veto_ref_above=None)`
and no training-run consolidation), `"strict rules (ours)"` (`Rules()` with consolidation), `"oracle"`.

**`run_study(setup: Setup, dev: Sequence[Episode], kappa, sims: int = 200, seed: int = 0, replicate: int = 1, rules: dict[str, Rule] | None = None, report_instances: int = 10) -> dict[str, dict]`**
Runs `sims` worlds with `random.Random(seed)` (`rules` defaults to `RULES`). Per rule it returns `true`
(mean true score of the picked route over the setup's tasks), `true_p05` / `true_p95` (5th and 95th
percentiles across worlds), `claimed` and `optimism` (`None` for a rule without claims), `regret`
(oracle true minus rule true), `raw_dev_gap` (raw development mean of the picked policies minus their
true score, on tasks where they have rollouts) and `reported` (sorted list of simulated reporting runs,
`report_instances` fresh episodes per task). `kappa` is a number or an outcome model, as in
`draw_ledger`.

## `policybank.routing`

**`class RouteError(ValueError)`** — raised for invalid routes.

**`class Route(assignments: Mapping[int, str])`**
Frozen dataclass mapping each task id to one policy label.

- **`Route.from_json(doc: Mapping) -> Route`** (classmethod) accepts `{"tasks": [{"task_id", "policy"}, ...]}`
  (the `route.json` layout) or `{task_id: policy}`; raises `RouteError` if a task is routed twice.
- **`canonical() -> bytes`** — compact JSON with string task ids and sorted keys.
- **`sha256`** (property) — SHA-256 hex digest of `canonical()`.
- **`policy(task_id: int) -> str`** — the routed policy; `RouteError` if the task is not routed.
- **`validate(bank: Iterable[str], n_tasks: int = 100) -> None`** — raises `RouteError` for unrouted
  task ids, unknown task ids, or policies outside `bank`.
- **`images() -> dict[str, list[int]]`** — tasks grouped by policy (one serving image per policy),
  largest group first.
- **`diff(other: Route) -> dict[int, tuple[str | None, str | None]]`** — tasks whose assignment differs,
  as `(self, other)`.

## `policybank.provenance`

Auditing evaluator output before scoring it.

**`NAME`** — regex for metrics file names: `<task>_<instance>_<rollout>.json`.

**`REQUIRED`** — `('task', 'instance_id', 'rollout_id', 'steps', 'success', 'q_score', 'time')`.

**`class AuditError(ValueError)`** — raised for every audit failure.

**`parse_metrics(filename: str, text: str) -> dict`**
Parses and validates one metrics file: the name matches `NAME`; the JSON is an object without
duplicate keys or `NaN`/`Infinity`; all `REQUIRED` keys exist; `instance_id`, `rollout_id` and `steps`
are non-negative integers (not booleans or floats); task, instance and rollout match the file name;
`q_score` and `time` are objects; `q_score.final` is a finite number in $[0, 1]$; `success` is a
boolean and implies `q_score.final == 1.0`; `time.normalized_time` is finite and non-negative.

**`check_coverage(cells: Iterable[tuple[str, int]], task_names: Sequence[str], instances: Sequence[int] = (301, ..., 310)) -> None`**
Requires exactly 100 distinct task names and exactly one cell per (task, instance) with nothing extra.

**`verify_directory(directory, task_names: Sequence[str], expected_sha256: dict[tuple[str, int], str] | None = None, instances: Sequence[int] = (301, ..., 310)) -> dict`**
Searches `directory` recursively for `*.json` files whose names match `NAME` (others are skipped),
parses each with `parse_metrics`, checks coverage, and, if `expected_sha256` is given, compares each
file's SHA-256 with it. Returns `{"files": int, "Q": float, "sha256_mismatches": [(task, instance), ...]}`,
where `Q` is the sum of `q_score.final` divided by `len(task_names) * len(instances)`. Raises
`AuditError` on the first hard failure.

**`class Attempt(cell: tuple[str, int], started: datetime, finished: datetime, q: float, ref: str = '')`**
Frozen dataclass for one completed attempt of a cell.

**`resolve_duplicates(attempts: Iterable[Attempt]) -> tuple[list[Attempt], list[dict]]`**
Keeps the attempt that finished first in each cell, independent of `q`. Raises `AuditError` if a later
attempt started before the kept one finished (chronology not established). Returns the kept attempts
and one record per resolved duplicate (`cell`, `kept`, `kept_q`, `excluded`, `excluded_q`, `rule`).

## `policybank.analysis`

Every number in the paper, recomputed from the active dataset directory.

**`FREEZE_UTC`** — `'2026-10-13T12:54:00Z'`, the stage-2 freeze.

**`STAGE1_START_UTC`** — `'2026-10-11T03:00:00Z'`, the evidence cutoff used for stage-1 tasks.

**`pearson(x, y)`** / **`spearman(x, y)`** — correlation coefficients (Spearman uses average ranks for
ties); `nan` if a series is constant.

**`task_table(official=None, route=None, tasks=None, dev=None)`**
One row per task (each argument is loaded from the dataset when not given; `dev` defaults to the
selection-eligible rows): `id`, `name`, `scene`, `demo_seconds`, `instruction`, `policy`, `family`,
`stage`, `expected_q`, `fallback`, `fallback_expected_q`, `q` (realized mean), `q_by_instance`,
`successes`, `timeouts`, `dev_rollouts`, `dev_policies`, `dev_chosen_n`, `dev_chosen_mean`.

**`policy_table(rows, policies=None)`**
Per routed policy, from `task_table` rows: `policy`, `display`, `family`, `kind`, `tasks`,
`task_ids`, `q_mean`, `task_points`, `successes`, `nonzero_tasks`, `expected_mean`; sorted by task
points, highest first.

**`reproduce_stage2(dev=None, route=None, freeze_utc: str = '2026-10-13T12:54:00Z')`**
Re-runs `select_by_level` for the stage-2 tasks among 50–99 (all 50 in the release) on the eligible
rows of tasks 50–99 that finished at or before `freeze_utc`, with reference `s150997`, generalists
`s150997`, `comet@ymetz6000` and `comet@ymetz9999`, every `w100@` label in those rows as a specialist,
the training-run map `{comet@ymetz6000, comet@ymetz9999} -> ymetz`, and `Rules()`. Returns `tasks`,
`agree`, `dev_rollouts_used`, `disagreements` (each with `task_id`, `ours`, `frozen`, `posterior_ours`,
`posterior_frozen`) and `choices` (a `Counter`).

**`summarize(simulate: bool = True)`**
The full results dictionary (the content of `results/summary.json`): `Q`, `Q_ci95`, `episodes`,
`successes`, `success_rate`, `nonzero_tasks`, `zero_tasks`, `tasks_with_success`, `episodes_nonzero`,
`within_task_sd`, `timeouts`, `timeout_share_of_failures`, `replay_counts`, `stages`, `calibration`,
`scenes`, `demo_length_spearman`, `q_histogram_deciles`, `dev`, `power`, `policies`,
`stage2_reproduction`, `simulation` (`None` when `simulate=False`), `calibration_breakdown`,
`reproduction_baselines` and the per-task rows `tasks`. With the simulation it takes about a minute.

**`simulation_study(sims: int = 300, curve_sims: int = 120, seed: int = 0)`**
The posterior-predictive study of [simulation.md](simulation.md): fits `fit_zero_inflated` to the
reported episodes, runs `run_study` on all of tasks 50–99 (eligible rows finished by the stage-2
freeze), adds a budget curve (replication 1 is the main run; 2, 4 and 8 use `curve_sims` worlds and
seeds `seed + m`) and the observed counterparts. Returns `kappa`, `zero_c`, `sims`, `rules`, `curve`,
`observed`, `template_rollouts`, `zero_share_official`, `zero_share_dev`.

**`calibration_breakdown()`**
Where the optimism gap sits. Returns `by_depth` (tasks grouped by the routed policy's own development
rollouts at its stage's cutoff: 0, 1, 2+), `by_stage`, `predicted_gain_Q`, `fallback_tasks`,
`within_sd`, `within_sd_nonzero_tasks`, `selection_n` (`rollouts_for_selection` at 0.05, 0.10 and 0.20),
`eligible_labels`, `share_313_eligible`, `dev_single_policy` (development-only single-policy means),
`routed_with_zero_own_stage1`, `own_dev_n` (per task) and `eligible_at_freeze`.

**`reproduction_baselines()`**
Agreement with the frozen route on tasks 50–99 of trivial rules: highest raw development mean
(`raw_dev_mean_agree`) and `comet@ymetz9999` everywhere (`ymetz_everywhere_agree`), plus how many of the
non-default picks the selector reproduces (`nondefault_tasks`, `nondefault_agree`).

## `policybank.serving`

The package re-exports `pack`, `unpack`, `CHUNK_KEY`, `ContractError`, `ContractSpec`,
`SessionContract`, `ChunkExecutor`, `Policy` and `ScriptedPolicy`. See [serving.md](serving.md) for
the protocol.

### `policybank.serving.codec`

**`MAX_BYTES`** — `134217728` (128 MiB), the largest frame or array accepted.

**`pack(obj) -> bytes`**
msgpack encoding with numpy arrays (including 0-d arrays) and numpy scalars as `b"__ndarray__"` /
`b"__npgeneric__"` marker maps (OpenPI-compatible); non-contiguous arrays are sent in C order.
`np.float64` scalars go out as plain msgpack floats. Raises `TypeError` for arrays or scalars whose
dtype is not bool, integer or float (object, string, complex, ...) and for other unsupported types.

**`unpack(data: bytes)`**
Bounded decoding of `bytes` or `bytearray`. Marker keys may be bytes or text; 0-d arrays stay 0-d;
arrays are read-only views of the frame; text is decoded to `str`. Raises `ValueError` for non-binary
or oversized frames, marker maps with a missing field, an `__ndarray__` value other than `True`,
unsupported dtypes or item sizes above 8, more than 8 dimensions or invalid shape entries, arrays over
`MAX_BYTES` or with an inconsistent byte length, scalar markers whose payload is not a scalar or does
not fit the dtype, msgpack extension types, oversized msgpack arrays or maps, and malformed msgpack. A
dtype string numpy cannot parse raises `TypeError`.

### `policybank.serving.contract`

**`CHUNK_KEY`** — `'action_chunk_size'`.

**`class ContractError(ValueError)`** — a contract violation; terminal in the server.

**`class ContractSpec(proprio_dim: int = 61, action_dim: int = 23, max_batch: int = 10, chunk: int = 4, tasks: frozenset[int] = <factory>, max_resets_between_queries: int = 1000)`**
Dataclass of contract limits. `tasks` defaults to `frozenset(range(100))`. `chunk` is the global
transport chunk K; 0 or 1 disables chunking.

**`class Query(obs: dict, n: int, batched: bool, task_id: int)`** — a validated observation.

**`class SessionContract(spec: ContractSpec, binding: dict | None = None)`**
Validates one evaluator connection. `binding` (`{"task_id": ...}`, default `{"task_id": None}`) can be
shared across connections so the task binding outlives a session; `PolicyServer` shares one.

- **`request(payload: bytes) -> Query | None`** — parses and validates one frame (see
  [serving.md](serving.md#observation-frame)); returns `None` for a reset, which clears the batch-shape
  binding and counts toward `max_resets_between_queries`. Raises `ContractError` on any violation,
  including any decoding error.
- **`reply(action: np.ndarray, chunk: np.ndarray | None, q: Query) -> dict`** — validates the outbound
  action (shape, float dtype, finite) and, when K > 1, the chunk (shape, same dtype, finite, row 0 equal
  to `action` byte for byte; a chunk with K ≤ 1 is an error); returns `{"action": ...}` plus
  `"action_chunk"` when K > 1, and resets the reset counter.

### `policybank.serving.executor`

**`class Policy(Protocol)`**
Attributes `name: str`, `horizon: int` (actions replayed per plan), `action_dim: int`; methods
**`plan(obs: dict, n: int) -> np.ndarray`** returning `(n, H, action_dim)` actions with `H >= horizon`
and **`reset() -> None`**.

**`class ChunkExecutor(policy: Policy, chunk: int)`**
Receding-horizon execution in fixed chunks of K = `max(chunk, 1)` actions. Raises `ValueError` if
`chunk > 1` does not divide `policy.horizon`. Attribute `plans` counts plans requested.

- **`step(obs: dict, n: int) -> np.ndarray`** — the next `(n, K, action_dim)` actions; asks the policy
  for a new plan, truncated to `horizon`, only when the queue holds fewer than K actions. Raises
  `ValueError` for a plan with the wrong number of environments, the wrong number of dimensions or
  width, fewer than `horizon` actions, or nonfinite values.
- **`reset() -> None`** — empties the queue and calls `policy.reset()`.

**`class ScriptedPolicy(name: str = 'scripted', horizon: int = 32, action_dim: int = 23)`**
Deterministic stand-in for tests: in plan `j` (counted since the last reset), step `s` has value
`j + s / horizon` in every dimension, for every environment (float32).

### `policybank.serving.server`

**`LOG`** — the `logging` logger `policybank.serving`. Terminal failures are logged at ERROR as
`terminal failure: <kind> [<session id>]: <message>`; abnormal peer closes at WARNING as
`session <id> closed by peer (...)`; readiness at INFO as
`SERVER_READY policy=... chunk=... replay=... port=...`.

**`class QueryTimeout(TimeoutError)`** — a bounded step exceeded `query_timeout_s`; the message is
`session reset exceeded <N> s`, `metadata send exceeded <N> s` or `query exceeded <N> s`.

**`class PolicyFault(RuntimeError)`** — wraps any exception other than `ContractError` raised on the
inference thread (model, executor, adapter, upstream connection), as `<type>: <message>`.

**`class PolicyServer(policy: Policy, spec: ContractSpec | None = None, *, query_timeout_s: float = 550.0, task_id: int | None = None, keepalive_s: float | None = 30.0)`**
The fail-stop websocket server for one policy and one task. `spec` defaults to
`ContractSpec(action_dim=policy.action_dim)`; the `ChunkExecutor` is built here, so a chunk that does
not divide `policy.horizon` raises `ValueError`. `task_id` pre-binds the task. `keepalive_s` is the
websocket ping interval (pong timeout twice that; `None` disables pings), which ends sessions whose
peer vanished without closing. Attributes: `failed` (`threading.Event`), `failure` (reason string or
`None`), `queries` (answered observation frames), `sessions` (accepted sessions), `port` (set once
listening).

- **`async serve(host: str = '0.0.0.0', port: int = 8000, ready: asyncio.Event | None = None) -> int`**
  — runs until a terminal failure (returns 1) or `shutdown()` / SIGTERM / SIGINT (returns 0). Port 0
  binds a free port (read it from `port`). Sets `ready` once listening. Each call creates its own
  single-thread inference pool and never joins it, so a hung inference call cannot block the return;
  the caller should exit the process afterwards (the CLI uses `os._exit`).
- **`async handler(ws)`** — the per-connection coroutine: 1013 refusal, bounded session reset and
  metadata, the query loop, 1011 on a terminal failure.
- **`metadata() -> dict`** — the map sent on connect.
- **`fail(reason: str) -> None`** — records a terminal failure, logs it and wakes `serve()`
  (thread-safe; the first call wins).
- **`shutdown() -> None`** — stops serving cleanly (thread-safe; a no-op before `serve()` starts).
- **`health(connection, request)`** — `process_request` hook answering `GET /healthz` and `/readyz`
  with `200 OK` or `503 FAILED`; other paths continue as a websocket handshake.

### `policybank.serving.client`

**`class PolicyClient(uri: str, chunk: int = 4, timeout: float = 30.0)`**
Minimal synchronous client (context manager). Connects (waiting up to `timeout`), reads the server's
metadata into `metadata`, and exposes the socket as `ws`.

- **`infer(proprio: np.ndarray, task_id: int, **extra) -> dict`** — sends `robot_r1::proprio`
  (float32), `task_id` (int64 array, one entry per environment), `action_chunk_size` (0-d int64 array
  holding `chunk`) and any `extra` keys; returns the decoded reply (waiting up to `timeout`).
- **`reset() -> None`** — sends `{"reset": True}`; no reply is read.
- **`close() -> None`** — closes the connection.

### `policybank.serving.remote`

**`class UpstreamError(RuntimeError)`** — the upstream server replied with an error or a malformed plan,
closed the connection, failed at the socket level, or did not answer in time.

**`class OpenPIRemotePolicy(uri: str, *, name: str = 'remote', horizon: int = 32, action_dim: int = 23, timeout_s: float = 540.0, drop_keys: tuple[str, ...] = ('action_chunk_size',), forward_reset: bool = False)`**
A `Policy` backed by an OpenPI-compatible websocket server. Connects at construction (waiting up to
`timeout_s`; a connection error is raised as is) and stores the upstream metadata in `metadata`.

- **`plan(obs: dict, n: int) -> np.ndarray`** — sends one request per environment and returns
  `(n, horizon, action_dim)` float32 actions, truncating longer plans. A query is batched when the first
  `*proprio` array is 2-D (so batched N = 1 is split too); then every array with leading dimension `n`
  is indexed per environment. `task_id` with leading dimension `n` is indexed in unbatched queries too;
  any other `task_id` is sent unchanged. `drop_keys` are removed. Waits up to `timeout_s` per reply.
  Raises `UpstreamError` for a text reply, a reply without `"actions"`, a plan that is not 2-D, shorter
  than `horizon` or of the wrong width, a closed upstream connection, an `OSError`, or a reply timeout.
- **`reset() -> None`** — with `forward_reset`, sends `{"reset": True}` upstream and reads no reply;
  otherwise does nothing (the executor clears the wrapper's own queues).
- **`close() -> None`** — closes the upstream connection.

## `policybank.cli`

**`main(argv=None)`** — the `python -m policybank` / `policybank` entry point:
`policybank [--data DATA] {score,route,select,analyze,verify,simulate,serve} ...`. `--data` (dataset
directory; default: the repository's `data/`, or `$POLICYBANK_DATA` if set) goes before the
subcommand. Subcommands, with their `--help` text:

| Subcommand | Help | Options (default) |
|---|---|---|
| `score` | challenge Q of the reported episodes with a bootstrap CI | `--boot` (10000) |
| `route` | show and validate the frozen route | `--images`: group tasks by serving image |
| `select` | re-run the stage-2 selection and compare with the frozen route | `--freeze` (`2026-10-13T12:54:00Z`) |
| `analyze` | every number in the paper, as JSON | `--out` (none: print without the per-task rows) |
| `verify` | audit a folder of evaluator metrics files (coverage, format, hashes) | `directory`; `--check-hashes`: compare every file with the released SHA-256 |
| `simulate` | posterior-predictive study of the selection rules (tasks 50-99) | `--sims` (300), `--curve-sims` (120), `--seed` (0) |
| `serve` | run the fail-stop server in front of a scripted or upstream policy | `--upstream`, `--forward-reset`, `--policy` (`scripted`), `--replay` (32), `--chunk` (4), `--host` (`127.0.0.1`), `--port` (8000), `--query-timeout` (550.0); see [serving.md](serving.md#command-line) |

Example output for every command is in [reproducing.md](reproducing.md#3-command-reference).
