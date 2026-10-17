# Reproducing the results

Every number in the paper that does not carry a † is recomputed from `data/` by the code in this
repository. Nothing here needs a GPU, a simulator or model weights. Every command below is run from the
repository root. The outputs were produced with the current code on a laptop CPU (Windows 11,
Python 3.11.9, numpy 2.4.6) and are trimmed where marked.

The quickest check needs no local install: the notebook
[`notebooks/reproduce.ipynb`](../notebooks/reproduce.ipynb)
([open in Colab](https://colab.research.google.com/github/FungousLand1941/policy-bank/blob/main/notebooks/reproduce.ipynb))
clones the repository, installs it, and recomputes the score with its bootstrap interval, the route
hash, the stage-2 reproduction, the calibration breakdown and a smaller run of the simulation study.

## 1. Install

Requirements: Python 3.10 or newer (CI tests 3.10–3.13).

```bash
git clone https://github.com/FungousLand1941/policy-bank && cd policy-bank
pip install -e ".[dev]"          # numpy, msgpack, websockets, pytest, ruff
```

| Extra | Adds | Needed for |
|---|---|---|
| (none) | `numpy>=1.24`, `msgpack>=1.0` | scoring, selection, simulation, analysis, audit |
| `serve` | `websockets>=13` | `policybank.serving`, `python -m policybank serve` |
| `figures` | `matplotlib>=3.7` | `tools/make_figures.py`, `tools/prerender_site.py --images` |
| `dev` | `pytest>=7`, `websockets>=13`, `ruff>=0.6` | tests and lint |

The CLI finds the dataset in the repository's `data/`. To use a copy elsewhere, pass `--data DIR`
before the subcommand (`python -m policybank --data DIR score`) or set `POLICYBANK_DATA=DIR`.

## 2. Run the tests

```bash
python -m pytest -q -p no:cacheprovider     # -p no:cacheprovider: do not write .pytest_cache/
ruff check .
```

```text
...s.................................................................... [ 56%]
.......................................................                  [100%]
126 passed, 1 skipped in 39.50s
```

The suite collects 127 tests. The skipped one (`tests/test_cli_process.py`) checks that `serve` exits
with code 0 on SIGTERM. That only applies on POSIX: on Windows `Popen.terminate()` is
`TerminateProcess`, which forces the exit code. On Linux all 127 run.

The suite covers scoring and the bootstrap, the released headline numbers, provenance and route
hashing, every selection rule and the stage-2 reproduction, the simulation, the codec, the session
contract, chunked execution, the server (in-process and as a CLI subprocess, including keepalive
handling of silent peers), the OpenPI adapter, and seeded randomized property tests.

## 3. Command reference

`python -m policybank [--data DIR] <command> [options]` (also installed as `policybank`).

| Command | Options (default) | What it does |
|---|---|---|
| `score` | `--boot` (10000) | challenge $Q$ of the 1,000 reported episodes with a task-stratified bootstrap 95% CI (seed 0) |
| `route` | `--images` | validate the frozen route against `policies.json`, print its canonical SHA-256 and every task; with `--images`, tasks grouped by serving image |
| `select` | `--freeze` (`2026-10-13T12:54:00Z`) | re-run the stage-2 selection for tasks 50–99 on eligible rollouts finished by `--freeze` and compare with the frozen route |
| `simulate` | `--sims` (300), `--curve-sims` (120), `--seed` (0) | posterior-predictive study of the selection rules on tasks 50–99 |
| `analyze` | `--out FILE` | every number in the paper as JSON; prints it without the per-task rows, or writes everything to `FILE` |
| `verify` | `directory`, `--check-hashes` | audit a folder of evaluator metrics files (format, coverage, Q); with `--check-hashes`, compare every file with the released SHA-256 |
| `serve` | `--upstream`, `--forward-reset`, `--policy` (`scripted`), `--replay` (32), `--chunk` (4), `--host` (`127.0.0.1`), `--port` (8000), `--query-timeout` (550.0) | run the fail-stop server in front of the scripted policy or an OpenPI-compatible upstream; see [serving.md](serving.md) |

### `score`

```bash
python -m policybank score
```

```text
Q = 0.156054  (95% CI 0.1434-0.1685, task-stratified bootstrap, 10000 resamples)
episodes = 1000  successes = 37  success rate = 0.037
```

The bootstrap resamples the ten reporting episodes within each task (seed 0). Its result does not
depend on the order of the rows in `official_episodes.csv`. CI runs the faster `score --boot 2000`:

```bash
python -m policybank score --boot 2000
```

```text
Q = 0.156054  (95% CI 0.1433-0.1685, task-stratified bootstrap, 2000 resamples)
episodes = 1000  successes = 37  success rate = 0.037
```

### `route`

```bash
python -m policybank route
```

```text
route sha256 adb6f400a503a3bbdca961260514f64a4c854b341f3021ae397f4fad8467d7e1  (stage 2 frozen 2026-10-13T12:54:00Z)
  0 turning_on_radio                       -> pt12                 stage 2  E[q]=0.304  fallback winner2 0.289
  1 picking_up_trash                       -> winner2              stage 2  E[q]=0.549  fallback winner2 0.549
  2 putting_away_Halloween_decorations     -> pt50                 stage 1  E[q]=0.500
  ...
 54 putting_away_toys                      -> w100@j_jl_4task100   stage 2  E[q]=0.333  fallback s150997 0.138
  ...
 99 sorting_books_on_shelf                 -> comet@ymetz9999      stage 2  E[q]=0.166  fallback s150997 0.030
```

One line per task (trimmed here to 5 of 100); task names are cut to 38 characters. `E[q]` is the
routed policy's posterior expected score at freeze. Stage-2 lines add the incumbent the routed policy
had to beat and the incumbent's expected score.

```bash
python -m policybank route --images
```

```text
route sha256 adb6f400a503a3bbdca961260514f64a4c854b341f3021ae397f4fad8467d7e1  (stage 2 frozen 2026-10-13T12:54:00Z)
comet@ymetz9999         42 tasks  [50, 51, 52, 53, 55, 58, 59, 60, 61, 62, 63, 64, 65, 66, 68, 69, 70, 71, 72, 73, 74, 75, 76, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87, 88, 89, 90, 91, 92, 93, 94, 95, 99]
pt50                    25 tasks  [2, 3, 6, 7, 8, 10, 11, 15, 16, 17, 21, 22, 23, 24, 26, 27, 28, 35, 36, 37, 39, 41, 43, 45, 49]
winner1                 11 tasks  [5, 13, 14, 19, 25, 29, 34, 42, 44, 47, 48]
winner2                  5 tasks  [1, 12, 18, 20, 30]
winner3                  5 tasks  [4, 31, 32, 38, 46]
w100@j_jl_4task100       4 tasks  [54, 56, 77, 98]
s150997                  3 tasks  [33, 57, 67]
pt12                     2 tasks  [0, 9]
w100@b_amy_t90           2 tasks  [96, 97]
winner4                  1 tasks  [40]
```

### `select`

```bash
python -m policybank select
```

```text
stage-2 tasks 50-99: reimplementation agrees with the frozen route on 48/50 tasks using 411 dev rollouts
  task 70: ours s150997 (0.176) vs frozen comet@ymetz9999 (0.173)
  task 87: ours s150997 (0.288) vs frozen comet@ymetz9999 (0.229)
```

The numbers in parentheses are the reimplementation's posterior means for the two policies. The
411 rollouts are the eligible rows on tasks 50–99 that finished by the freeze (see
[data.md](data.md#eligibility-filter)). The original pipeline used a slightly different development
table and pooled the two ymetz steps; see [method.md](method.md). The 13 stage-2 tasks from 0–49 and
all of stage 1 need unreleased reference tables and are not re-derived.

### `simulate`

A quick run with fewer simulated worlds (a few seconds):

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

The paper uses the defaults: 300 worlds, 120 worlds per point of the evidence-depth curve, and the
zero-inflated outcome model (a point mass at zero plus a Beta part whose concentration is `kappa`).
`python -m policybank simulate` takes about a minute and prints the numbers in the paper:

```text
posterior-predictive study, tasks 50-99, 300 worlds, kappa=6.42
rule                     true Q       90% range  claimed  optimism  regret
reference only            0.062   0.052-0.073        -         -   0.167
best dev mean             0.182   0.158-0.204    0.299    +0.117   0.047
best posterior            0.196   0.173-0.218    0.198    +0.002   0.033
strict rules (ours)       0.186   0.153-0.211    0.189    +0.002   0.043
oracle                    0.229   0.212-0.248    0.229    +0.000   0.000
observed: claimed 0.203, reported 0.151 (percentile 4 of simulated reporting runs)
```

With 40 worlds the estimates move by a few thousandths and the percentile is coarse; the ordering of
the rules is the same. See [simulation.md](simulation.md) for what each column means.

### `analyze`

```bash
python -m policybank analyze                  # JSON to stdout, without the per-task rows
python -m policybank analyze --out FILE       # everything, including the per-task rows
```

It runs the 300-world simulation, so it takes about a minute. The output is one JSON object
(trimmed):

```text
{
 "Q": 0.15605353674103675,
 "Q_ci95": [
  0.14336520476613596,
  0.16849295942595485
 ],
 "episodes": 1000,
 "successes": 37,
 "success_rate": 0.037,
 "nonzero_tasks": 71,
 "zero_tasks": 29,
 "tasks_with_success": 15,
 "episodes_nonzero": 364,
 "within_task_sd": 0.19987571557418154,
 "timeouts": 963,
 ...
```

`Q_ci95` is the default 10,000-resample bootstrap, the interval `score` prints. The remaining keys
are:

| Key | Contents (values from the current data) |
|---|---|
| `timeout_share_of_failures` | 1.0: every unsuccessful episode ran to the step cap |
| `replay_counts` | episodes by replay length: 32: 716, 20: 277, 0: 7 |
| `stages` | per stage: tasks (37 / 63), realized and expected mean $q$, task points |
| `calibration` | expected vs realized per-task scores: Pearson 0.600, Spearman 0.684, mean expected 0.206, mean realized 0.156 |
| `scenes`, `demo_length_spearman`, `q_histogram_deciles` | per-scene means, rank correlation with demonstration length, histogram of the 1,000 $q$ values |
| `dev` | 1,146 rollouts, 800 selection-eligible, 36 labels tested, rows per instance |
| `power`, `policies` | rollouts needed to detect a given difference; per-policy summary of the route |
| `stage2_reproduction` | the result printed by `select` |
| `simulation` | the 300-world study printed by `simulate`, plus the evidence-depth curve |
| `calibration_breakdown`, `reproduction_baselines` | optimism by evidence depth and stage (724 eligible rows at the freeze); agreement of trivial rules with the frozen route |
| `tasks` | 100 per-task rows (only with `--out`) |

On an unmodified checkout `analyze --out FILE` holds the same values as the committed
`results/summary.json`. The bytes differ: `analyze --out` escapes non-ASCII characters and has no
trailing newline, while `tools/export_site_data.py`, which writes the committed file, keeps them and
ends with a newline. Use `tools/export_site_data.py` to refresh the committed summary.

### `verify`

```bash
python -m policybank verify data/metrics --check-hashes
```

```text
1000 metrics files, coverage complete, Q = 0.156054
all SHA-256 match the released ledger
```

All 1,000 original evaluator metrics files are in `data/metrics/`, byte for byte. See
[Auditing raw metric files](#auditing-raw-metric-files).

### `serve`

```bash
python -m policybank serve --port 8765
```

```text
2026-10-17 16:22:27,519 INFO server listening on 127.0.0.1:8765
2026-10-17 16:22:27,519 INFO SERVER_READY policy=scripted chunk=4 replay=32 port=8765
```

The default port is 8000. The server runs until a terminal failure (exit code 1) or SIGTERM/SIGINT
(exit code 0). See [serving.md](serving.md) for the protocol and a client example, and
[`docker/README.md`](../docker/README.md) for the container image.

## 4. Regenerate the summary, tables, figures, paper and site

These scripts overwrite committed files. On an unmodified checkout they reproduce them byte for byte.

```bash
pip install -e ".[figures]"
python tools/export_site_data.py      # results/summary.json and site/data/ (runs the simulation, ~1 min)
python tools/make_tables.py           # paper/generated/*.tex: every number quoted in the paper
python tools/make_figures.py          # paper/figures/*.pdf (needs matplotlib)
python tools/prerender_site.py        # bake the numbers into site/index.html
cd paper && latexmk -pdf main.tex     # paper/main.pdf
```

| Step | Reads | Writes | Prints |
|---|---|---|---|
| `tools/export_site_data.py` | `data/` | `results/summary.json` (the `analyze` dictionary), `site/data/results.json`, and copies of `official_episodes.csv`, `dev_rollouts.csv`, `route.json`, `tasks.json`, `policies.json` in `site/data/` | `site/data/results.json  100 tasks, 10 policies` |
| `tools/make_tables.py` | `results/summary.json`, `site/data/results.json`, `data/policies.json`, and the task-69 worked example recomputed from `data/` | `paper/generated/numbers.tex` (LaTeX macros) and the table bodies `alltasks`, `bank`, `depth`, `policies`, `scenes`, `simulation`, `stagesplit`, `toptasks` | `wrote ['alltasks.tex', 'bank.tex', 'depth.tex', 'numbers.tex', 'policies.tex', 'scenes.tex', 'simulation.tex', 'stagesplit.tex', 'toptasks.tex']` |
| `tools/make_figures.py` | `results/summary.json` | `paper/figures/{calibration,noise,simulation,tasks}.pdf` | `figures: [...]` |
| `tools/prerender_site.py` | `site/data/results.json`, `site/index.html` | `site/index.html` (`--images` also writes `site/og.png` and `site/apple-touch-icon.png`, needs matplotlib) | `updated site/index.html` or `site/index.html already up to date` |
| `latexmk -pdf main.tex` | `paper/main.tex`, `paper/generated/`, `paper/figures/`, `paper/refs.bib` | `paper/main.pdf` | |

Run them in this order: `make_tables.py` and `make_figures.py` read the summary that
`export_site_data.py` writes, and `prerender_site.py` reads `site/data/results.json`.

`python tools/prerender_site.py --check` writes nothing. It exits 1 with
`index.html is stale; run tools/prerender_site.py` if `site/index.html` would change, and prints
`index.html is up to date` otherwise (the current checkout passes). The released PDF is
`paper/policy-bank.pdf`; `latexmk` writes `paper/main.pdf` (ignored by Git), so copy it over if you
rebuild the release.

Values marked † in the paper are typed into `paper/main.tex` by hand, because they come from pipeline
logs that are not released. Everything else enters the paper through `paper/generated/numbers.tex` and
the generated tables, so the PDF cannot drift from the data.

### Line endings

The generators write every file with LF line endings (`newline="\n"`), whatever the platform, and
`.gitattributes` normalizes text files to LF (`* text=auto eol=lf`). Regenerating on Windows therefore
leaves `git diff` empty. `.gitattributes` also marks `data/metrics/*.json` as `-text`, so Git never
converts those files and they stay byte-identical to what the evaluator wrote; their SHA-256 values
in `official_episodes.csv` depend on it.

## 5. Continuous integration

`.github/workflows/ci.yml` runs on pushes to `main` and on pull requests:

| Job | Python | Steps |
|---|---|---|
| `test` | 3.10, 3.11, 3.12, 3.13 | `pip install -e ".[dev]"`; `ruff check .`; `python -m pytest -q`; then reproduce the headline numbers from `data/` with `score --boot 2000`, `route --images` and `select`, and audit the metric files with `verify data/metrics --check-hashes` |
| `paper-numbers` | 3.11 | `pip install -e ".[dev]"`; `tools/export_site_data.py`; `tools/make_tables.py`; `git diff --exit-code -- paper/generated` fails the job if any number in the paper drifts from the data |

`.github/workflows/serve-smoke.yml` runs on the same triggers:

| Job | Steps |
|---|---|
| `source` (server from source) | Python 3.12, `pip install ".[serve]"`; start `python -m policybank serve --host 127.0.0.1 --port 8000 --replay 32 --chunk 4`; run `docker/smoke_test.py`; then require the server to stop by itself with a nonzero exit code within 30 s and `terminal failure: contract` in its log |
| `docker` (container image) | build `docker/Dockerfile.serve`; start the container with `--restart no`; wait until Docker reports it healthy; check that PID 1 is `tini` running the server as uid 65532; run the smoke test against it; require the container to exit nonzero within 30 s with zero restarts and the contract failure in its log |

The image, its health check and the smoke test are described in
[`docker/README.md`](../docker/README.md).

## Auditing raw metric files

`python -m policybank verify DIR [--check-hashes]` audits a folder of evaluator metrics files before
anyone scores them. It is what `data/metrics/` was checked with, and it works on any copy of the
evaluator output.

What it checks (`policybank.provenance.verify_directory`):

1. **Discovery.** `DIR` is searched recursively for `*.json` files named `<task>_<instance>_<rollout>.json`;
   other files are ignored.
2. **Format** (`parse_metrics`), for every file: valid JSON object; no duplicate keys; no `NaN` or
   `Infinity`; the keys `task`, `instance_id`, `rollout_id`, `steps`, `success`, `q_score`, `time`;
   integer, non-negative `instance_id`, `rollout_id` and `steps`; task, instance and rollout equal to
   the file name; `q_score` and `time` are objects; `q_score.final` finite and in $[0, 1]$; boolean
   `success`, and `q_score.final == 1.0` whenever it is true; `time.normalized_time` finite and
   non-negative.
3. **Coverage** (`check_coverage`): exactly one file for each of the 100 tasks in `tasks.json` and each
   instance 301–310, and nothing else.
4. **Hashes** (with `--check-hashes`): the SHA-256 of each file's bytes against the `sha256` column of
   `official_episodes.csv` in the active dataset directory.

It then prints the file count and $Q$ (the sum of `q_score.final` over the 1,000 cells divided by
1,000). Results:

| Situation | Output | Exit code |
|---|---|---|
| everything matches | `1000 metrics files, coverage complete, Q = 0.156054` and `all SHA-256 match the released ledger` | 0 |
| valid files whose bytes differ from the release (for example re-serialized JSON) | the first line, then `<n> files differ: [('assembling_gift_baskets', 301), ...]` (first five cells) | 1 |
| a format or coverage error | a traceback ending in `policybank.provenance.AuditError: ...`, for example `missing=[('turning_on_radio', 301)] extra=[]` | 1 |

The same checks are available from Python:

```python
from policybank import data as D
from policybank.provenance import verify_directory

names = [t["name"] for t in D.load_tasks()]
report = verify_directory("data/metrics", names)   # {'files': 1000, 'Q': 0.156..., 'sha256_mismatches': []}
```

`policybank.provenance.resolve_duplicates` implements the score-blind rule used for the two duplicate
cells (keep the attempt that finished first; refuse if the attempts overlap in time); see
[data.md](data.md#duplicatesjson).
