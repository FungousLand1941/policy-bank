# Data dictionary

The JSON and CSV files in `data/` were produced by `tools/build_dataset.py` from the team's
evaluation-pipeline exports. Cluster paths, job identifiers and run directories were removed; every
other field needed to reproduce the paper was kept. `metrics/` holds the original evaluator files
themselves, unchanged; the script reads them to compute the hashes but does not copy them. The raw
inputs are not released (see [Rebuilding](#rebuilding)). `policybank.data` loads these files (see
[api.md](api.md#policybankdata)).

| File | Rows | Contents |
|---|---|---|
| [`tasks.json`](#tasksjson) | 100 | task id, name, scene, mean demonstration length, instruction |
| [`policies.json`](#policiesjson) | 10 | the routed checkpoints and their pinned sources |
| [`route.json`](#routejson) | 100 | the frozen route, expected scores at freeze, hashes |
| [`official_episodes.csv`](#official_episodescsv) | 1,000 | reported episodes, instances 301–310 |
| [`metrics/`](#metrics) | 1,000 files | the unchanged evaluator metric files behind `official_episodes.csv` |
| [`dev_rollouts.csv`](#dev_rolloutscsv) | 1,146 | development ledger, instances 311–319 |
| [`duplicates.json`](#duplicatesjson) | 2 | the two duplicate completed cells and the score-blind decision |
| `README.md` | | short description of the dataset |

The data directory can be moved: pass `--data DIR` before the CLI subcommand, set the
`POLICYBANK_DATA` environment variable, or call `policybank.data.set_data_dir(path)`.

## Conventions

- `q` is the evaluator's `q_score.final`: the fraction of the task's BDDL goal conditions satisfied at
  the end of the episode, in $[0, 1]$. `q = 1` exactly when the episode succeeds.
- An episode ends at success or at the step cap of 1.5 times the task's mean demonstration length.
  The simulator steps at 30 Hz (`sim_seconds = steps / 30` on every reported row).
- Timestamps are ISO 8601 UTC strings of the form `2026-10-13T12:54:00Z`. The code compares them as
  strings, which is valid because every value has this exact format.
- Booleans in the CSV files are written as `0` / `1`.

## `tasks.json`

A list of 100 objects, ordered by `id`.

| Field | Type | Meaning |
|---|---|---|
| `id` | int | task id, 0–99 |
| `name` | str | BEHAVIOR activity name, for example `turning_on_radio` |
| `demo_seconds` | int | mean human demonstration length in seconds (72–869) |
| `scene` | str | one of 7 scenes: `house_single_floor` (34 tasks), `house_double_floor_lower` (32), `house_double_floor_upper` (10), `restaurant_diner` (8), `Rs_int` (6), `hotel_suite_large` (5), `office_cubicles_right` (5) |
| `instruction` | str | natural-language instruction; for tasks 50–99 it comes from the BEHAVIOR task prompts used by the Comet adapter |

## `policies.json`

An object keyed by policy label, one entry per routed checkpoint (10). Labels are the ones used in
`route.json`, `official_episodes.csv` and `dev_rollouts.csv`.

| Field | Type | Meaning |
|---|---|---|
| `family` | str | `comet` (π0.5 Comet line, replay 32), `winner` (2025 winning solution, replay 20) or `winner100` (winner-format community specialist, replay 20) |
| `display` | str | human-readable name used in the paper and on the site |
| `kind` | str | `public` or `ours` (only `s150997`) |
| `source` | str | Hugging Face repository id, or `KANR continued training` for `s150997` |
| `revision` | str | pinned commit hash (40 hex digits), or `step 150997` |
| `subfolder` | str | checkpoint subfolder inside the repository; empty for `s150997` |
| `replay` | int | actions replayed per model query (the policy's native receding horizon) |
| `lineage` | str | where the checkpoint comes from |
| `license_status` | str | licence situation as found at the pinned revision |

| Label | Family | Display | Replay |
|---|---|---|---|
| `pt50` | comet | Comet π0.5 pt50 | 32 |
| `pt12` | comet | Comet π0.5 pt12 | 32 |
| `s150997` | comet | pt50 + 2026 demos (ours) | 32 |
| `comet@ymetz9999` | comet | ymetz pt50 step 9999 | 32 |
| `winner1` – `winner4` | winner | 2025 winner ckpt 1–4 | 20 |
| `w100@j_jl_4task100` | winner100 | JackLiu 4-task specialist | 20 |
| `w100@b_amy_t90` | winner100 | amyjia 5-task specialist | 20 |

No model weights are part of the release.

## `route.json`

The frozen task-to-policy route.

| Field | Type | Meaning |
|---|---|---|
| `schema` | str | `policy-bank-route/1` |
| `stage2_frozen_utc` | str | `2026-10-13T12:54:00Z`, when the stage-2 route was frozen |
| `manifest_built_utc` | str | `2026-10-16T01:01:15Z`, when the pipeline's frozen-route manifest was built |
| `route_sha256` | str | canonical SHA-256 of the final route (see [Hashes](#hashes)) |
| `stage1_table_sha256` | str | SHA-256 of the original stage-1 route table |
| `stage2_table_sha256` | str | SHA-256 of the original stage-2 route table |
| `tasks` | list | 100 entries, ordered by `task_id` |

Each entry of `tasks`:

| Field | Type | Meaning |
|---|---|---|
| `task_id` | int | 0–99 |
| `task` | str | task name |
| `policy` | str | routed policy label (a key of `policies.json`) |
| `family` | str | that policy's family |
| `stage` | int | 1 (37 tasks, all in 0–49) or 2 (63 tasks: 13 in 0–49, all of 50–99) |
| `selection` | str | `prior + development posterior (stage 1)` or `development posterior (stage 2)` |
| `part` | str | batch label from the original route tables: `A1`, `A2`, `A3`, `B` (stage 1) or `A`, `B` (stage 2) |
| `expected_q` | float | posterior expected score of the routed policy at freeze, 3 decimals |
| `fallback` | str or null | stage 2: the incumbent the routed policy had to beat (`s150997` on 50–99; `pt50`, `winner2` or `pt12` on 0–49). Stage 1: `null` |
| `fallback_expected_q` | float or null | the incumbent's posterior expected score at freeze; `null` for stage 1 |

When the incumbent was kept, `policy == fallback` (for example task 1).

## `official_episodes.csv`

The 1,000 reported episodes: one per (task, instance) for tasks 0–99 and instances 301–310, sorted by
`task_id` then `instance`. `policybank.data.load_official()` reads it.

| Column | Type | Meaning |
|---|---|---|
| `task_id` | int | 0–99 |
| `task` | str | task name |
| `instance` | int | reporting instance, 301–310 |
| `policy` | str | the routed policy that produced the episode (always equal to `route.json`'s policy for the task) |
| `q` | float | `q_score.final` |
| `success` | 0/1 | the evaluator's `success` flag |
| `steps` | int | simulator steps |
| `sim_seconds` | float | `time.simulator_time`, rounded to 3 decimals |
| `normalized_time` | float | `time.normalized_time`, rounded to 6 decimals. About 1/1.5 = 0.667 when the episode ran to the step cap (every failure has 0.6665–0.6667); larger when a success finished sooner |
| `nd_base`, `nd_left`, `nd_right` | float | `normalized_agent_distance.base` / `.left` / `.right`, rounded to 6 decimals |
| `replay` | int | actions replayed per model query: 32 (716 episodes), 20 (277), or 0 (7 episodes from a recovery pass that queried the model at every control step) |
| `finished_utc` | str | finish time from the run's episode index |
| `sha256` | str | SHA-256 of the unchanged evaluator metrics file (`metrics/<task>_<instance>_0.json`) |

`Episode.timed_out` (in `policybank.data`) is true when `success` is 0 and `normalized_time <= 0.6670`.
All 963 unsuccessful reported episodes ran to the step cap.

## `metrics/`

All 1,000 original evaluator metric files of the reporting set, byte for byte as the evaluator wrote
them (two-space indented JSON, LF line endings), in one flat folder and named
`<task>_<instance>_0.json`. Their SHA-256 values are the `sha256` column of
`official_episodes.csv`. `.gitattributes` marks them `-text` so Git never rewrites their line endings.
Audit them with:

```bash
python -m policybank verify data/metrics --check-hashes
```

```text
1000 metrics files, coverage complete, Q = 0.156054
all SHA-256 match the released ledger
```

Every file has these fields:

| Field | Type | Meaning |
|---|---|---|
| `task` | str | task name (must match the file name) |
| `instance_id` | int | instance (must match the file name) |
| `rollout_id` | int | rollout index (must match the file name; 0 in the release) |
| `steps` | int | simulator steps |
| `success` | bool | success flag; `q_score.final` must be 1.0 when true |
| `agent_distance` | object | `base`, `left`, `right`: distances travelled, as reported by the evaluator |
| `normalized_agent_distance` | object | `base`, `left`, `right`: the evaluator's normalized distances |
| `q_score` | object | `final`: the partial-credit score `q` |
| `time` | object | `simulator_steps`, `simulator_time`, `normalized_time` |

`policybank.provenance.parse_metrics` enforces the subset of this format that scoring depends on;
see [reproducing.md](reproducing.md#auditing-raw-metric-files).

## `dev_rollouts.csv`

Every development rollout in the team's ledger (1,146 rows over 57 runs and 36 policy labels), sorted
by `task_id`, `run`, `instance`. The row key `(run, task_id, instance, policy)` is unique; the analysis
code uses it to look up `finished_utc`. `policybank.data.load_dev()` reads all rows;
`load_dev(selection_only=True)` applies the [eligibility filter](#eligibility-filter).

| Column | Type | Meaning |
|---|---|---|
| `run` | str | development run label |
| `task_id` | int | 0–99 |
| `task` | str | task name |
| `instance` | int | development instance; 311–319 occur (instance 313 has 656 rows, 57%; none on 320) |
| `policy` | str | policy label: the ledger label before any `\|` description. Empty labels become `unlabelled`; the older labels `base` and `ft` become `pt50-sweep` and `ft-sweep` |
| `q` | float | `q_score.final` |
| `success` | 0/1 | success flag |
| `steps` | int | simulator steps |
| `normalized_time` | float | `time.normalized_time` as recorded in the ledger (at most 3 decimals) |
| `variant` | 0/1 | 1 if the label's description names an evaluation-time variant: time compression, gripper correction, `action_search`, sticky, or zscore (107 rows) |
| `nondefault_config` | 0/1 | 1 if the description mentions a modified robot configuration (22 rows, all of which also have `variant == 1`) |
| `dev_split` | 0/1 | 1 if `instance` is in 311–320 (1 on every released row) |
| `finished_utc` | str | finish time, from the raw ledger's file-modification timestamp |

The ledger spans 2026-10-04T08:38:55Z to 2026-10-13T20:18:01Z; 76 rows finished after the stage-2
freeze.

### Eligibility filter

A rollout is eligible for selection when all of the following hold (`load_dev(selection_only=True)`):

- `dev_split == 1` (a development instance),
- `variant == 0` (no evaluation-time variant),
- `nondefault_config == 0` (default robot configuration),
- `policy` is not `unlabelled`, `pt50-sweep` or `ft-sweep` (a routable label).

The variant flag removes 107 rows (including the 22 non-default-configuration rows) and the label rule
removes 239 (`ft-sweep` 105, `pt50-sweep` 103, `unlabelled` 31); the two sets do not overlap. Eight
labels disappear entirely: the three above and the variant-only labels `comet@ymetz6000_as_native32`,
`comet@ymetz6000_as_search16`, `comet@ymetz6000_as_seed16`, `comet@ymetz6000_as_seed32` and `h100fz`.
That leaves 800 of the 1,146 rows, over 28 of the 36 labels and 404 (task, policy) cells; 198 cells
have a single rollout. Some
remaining labels are one-off experiments (for example `h100f` or `skillpilot01-base-index15`). They
count as eligible rows but are not candidates in the stage-2 reproduction, which considers only the
generalists `s150997`, `comet@ymetz6000`, `comet@ymetz9999` and the `w100@` specialists.

`policybank.analysis` additionally restricts by time: stage-2 decisions use eligible rows with
`finished_utc <= 2026-10-13T12:54:00Z`. That is 724 of the 800 eligible rows; 411 of them are on
tasks 50–99, the rows `python -m policybank select` uses. The calibration breakdown counts a stage-1
task's own development evidence only up to `analysis.STAGE1_START_UTC` (see
[Freeze timestamps](#freeze-timestamps)).

## `duplicates.json`

Infrastructure retries produced two completed rollouts for two reporting cells. Each was resolved by
keeping the attempt that finished first, regardless of its score.

| Field | Type | Meaning |
|---|---|---|
| `task`, `instance` | str, int | the cell (`spraying_for_bugs`/307 and `cook_brussels_sprouts`/303) |
| `rule` | str | the decision rule as recorded by the pipeline |
| `kept_q`, `kept_sha256` | float, str | score and file hash of the kept attempt; `kept_sha256` equals the cell's `sha256` in `official_episodes.csv` |
| `excluded_q`, `excluded_sha256` | float, str | score and file hash of the later attempt, which is not released |

Kept/excluded scores: 0.5/0.0 for `spraying_for_bugs`/307 and 0.0/0.0 for `cook_brussels_sprouts`/303.
`policybank.provenance.resolve_duplicates` implements the rule.

## Freeze timestamps

| Timestamp | Where | Meaning |
|---|---|---|
| 2026-10-11T03:00:00Z | `analysis.STAGE1_START_UTC` | evidence cutoff for stage-1 tasks; the first reported episode finished at 03:04:21Z |
| 2026-10-13T12:54:00Z | `route.json` `stage2_frozen_utc`, `analysis.FREEZE_UTC`, default of `select --freeze` | stage-2 freeze (07:54 CDT) |
| 2026-10-13T13:10:30Z | `official_episodes.csv` | first stage-2 reported episode finished |
| 2026-10-14T06:38:00Z | `official_episodes.csv` | last reported episode finished |
| 2026-10-16T01:01:15Z | `route.json` `manifest_built_utc` | frozen-route manifest built |

## Hashes

- **`route_sha256`** (`adb6f400a503a3bbdca961260514f64a4c854b341f3021ae397f4fad8467d7e1`) is the
  SHA-256 of a canonical JSON encoding of the route: an object mapping each task id, as a string, to
  its policy label, with sorted keys and no whitespace. `policybank.routing.Route` computes it:

  ```python
  from policybank import data as D
  from policybank.routing import Route
  r = Route.from_json(D.load_route())
  r.canonical()[:40]   # b'{"0":"pt12","1":"winner2","10":"pt50","1'
  r.sha256             # 'adb6f400...'
  ```

  `python -m policybank route` prints it, and the tests check it against the recorded value.
- **`stage1_table_sha256`** and **`stage2_table_sha256`** identify the original stage-1 and stage-2
  route tables as written at freeze time. Those tables are not released, so these hashes are
  recorded for provenance and cannot be recomputed from `data/`.
- **`sha256`** in `official_episodes.csv` is the SHA-256 of each metrics file's raw bytes. It can be
  checked against `data/metrics/` or any other copy of the evaluator output with
  `python -m policybank verify DIR --check-hashes`.
- **`kept_sha256` / `excluded_sha256`** in `duplicates.json` identify both attempts of each
  duplicate cell.

## Rebuilding

```bash
python tools/build_dataset.py --raw /path/to/raw --out data
```

The raw inputs are internal pipeline exports and are **not released**, so this step cannot be run from
a clone. The script documents the layout it expects:

| Raw file | Contents |
|---|---|
| `tasks_all.tsv` | id, name, demonstration seconds, scene, instruction |
| `task_mapping_100.json` (optional) | BEHAVIOR task prompts, used where the table has no instruction |
| `ROUTE.tsv`, `ROUTE2.tsv` | stage-1 and stage-2 route tables with expected scores and fallbacks |
| `routes.frozen.json` | frozen task-to-policy mapping, the manifest build time and the route-table hashes |
| `official7_episodes.tsv` | episode index with the producing policy and finish times |
| `canonical/*.json` | the 1,000 unchanged evaluator metrics files |
| `dev_all_live.tsv` | every development rollout |
| `duplicate-resolution.json` | chronology decisions for the two duplicate cells |

What the script does:

- checks that every routed policy matches between the route tables and the frozen manifest, and that
  every reported episode was produced by its task's routed policy;
- sets `replay` from the policy family (`comet` 32, `winner`/`winner100` 20) except for seven cells
  listed in the script, which came from the recovery pass and replayed 0;
- derives `variant`, `nondefault_config` and `dev_split` from each development label's description
  and instance, and maps old labels (`base`, `ft`, empty) as described above;
- keeps only development rows whose task is one of the 100 tasks;
- writes `policies.json` from a table inside the script, and `route_sha256` with
  `policybank.routing.Route`;
- writes every output file as UTF-8 with LF line endings;
- prints `tasks=100 official=1000 dev=<rows> Q=<mean q>` at the end.

It reads `canonical/*.json` but does not copy those files; `data/metrics/` is a byte-for-byte copy of
that folder.
