# Policy Bank

[![ci](https://github.com/FungousLand1941/policy-bank/actions/workflows/ci.yml/badge.svg)](https://github.com/FungousLand1941/policy-bank/actions/workflows/ci.yml)
[![paper](https://img.shields.io/badge/paper-PDF-blue)](paper/policy-bank.pdf)
[![project page](https://img.shields.io/badge/project%20page-policy--bank.vercel.app-black)](https://policy-bank.vercel.app)
[![license](https://img.shields.io/badge/code-Apache--2.0-green)](LICENSE)
[![Open in Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/FungousLand1941/policy-bank/blob/main/notebooks/reproduce.ipynb)

**Development-selected routing of public robot policies for BEHAVIOR-1K.**
This is Team KANR's technical report and code for the 2026 BEHAVIOR Challenge.

Keshav Balakrishna · Abhijay Gangerapu · Rithik Satarla (Independent)

[Paper (PDF)](paper/policy-bank.pdf) · [Project page](https://policy-bank.vercel.app) · [Data](data/)

---

The challenge asks one system to complete 100 long-horizon household tasks in simulation. Instead of
training one generalist, we route each task to one of ten vision-language-action checkpoints. Nine
are public and one is our own continued training. Every routing decision uses development instances
(311–320) only. An empirical-Bayes model combines public reference scores, policy levels estimated
against a reference policy, and our eligible development rollouts (800 in total, 724 available when
the main route froze). Conservative switching rules then guard each change of policy.

| | |
|---|---|
| Challenge score Q (public instances 301–310, Isaac Sim 6.0.1) | **0.156** (95% CI 0.143–0.168) |
| Episodes | 1,000 (100 tasks × 10 instances, scored from each cell's first completed run) |
| Tasks with any credit / full successes | 71 tasks / 37 episodes in 15 tasks |
| Expected vs realized | Spearman 0.68 across tasks; mean 0.206 → 0.156 |
| Where the optimism sits | +1.5 and +4.1 task points where the routed policy had 0 or 1 own dev rollouts; −0.6 with ≥ 2 |
| Simulation (tasks 50–99, within the model, zero-inflated Beta outcomes) | raw-mean selection delivers less than our rules (0.182 vs 0.186) and overclaims by 0.12; posterior claims stay honest (+0.002); an oracle adds only 0.043 |
| Selector reimplementation vs frozen stage-2 route | 48 / 50 tasks, including all 8 non-default picks (routing ymetz everywhere: 42) |

Q is a self-evaluated score on public instances, not a hidden-test result. See
[Disclosures](#disclosures).

## Quick start

```bash
git clone https://github.com/FungousLand1941/policy-bank && cd policy-bank
pip install -e ".[dev]"             # numpy, msgpack, websockets, pytest, ruff
python -m pytest -q                 # 127 tests, ~40 s (one is skipped on Windows)
python -m policybank score          # Q = 0.156054 (95% CI 0.1434-0.1685)
python -m policybank route --images # one serving image per policy and its tasks
python -m policybank select         # re-run the stage-2 selection against the frozen route
python -m policybank simulate       # posterior-predictive study of the selection rules
python -m policybank analyze --out results/summary.json
```

The dataset lives in `data/`. Run from a clone, or point the code elsewhere with `--data DIR` (before
the subcommand) or the `POLICYBANK_DATA` environment variable.

All 1,000 reported evaluator metric files are in `data/metrics/`, byte for byte. To audit them, or
any folder of raw evaluator files (format, coverage, and SHA-256 against the release):

```bash
python -m policybank verify data/metrics --check-hashes
```

## Repository

```
policybank/            Python package
  metrics.py           challenge Q, rescaled bootstrap CI, rollout noise, power for testing and for selection
  selection.py         priors, conjugate updates, switching rules, one-checkpoint-per-training-run search
  simulate.py          posterior-predictive simulation of selection rules (zero-inflated Beta outcomes)
  routing.py           frozen route: validation, canonical SHA-256, image map
  provenance.py        metrics-file audit, coverage, score-blind duplicate resolution, directory verification
  analysis.py          every number in the paper
  serving/             fail-stop websocket server: codec, contract, chunk executor, client, OpenPI adapter
  cli.py               python -m policybank {score,route,select,simulate,analyze,verify,serve}
data/                  released dataset (see data/README.md)
results/summary.json   output of `policybank analyze`
paper/                 LaTeX source, generated numbers/tables/figures, compiled PDF
site/                  static project page (deployed on Vercel)
tools/                 dataset build, figures, tables, site export and prerender
tests/                 127 tests (unit, property, serving, CLI subprocess)
```

To regenerate the paper's numbers, figures and website data from `data/`:

```bash
pip install -e ".[figures]"
python tools/export_site_data.py   # results/summary.json + site/data (runs the simulation, ~1 min)
python tools/make_tables.py        # paper/generated/*.tex: every number quoted in the paper
python tools/make_figures.py       # paper/figures/*.pdf
python tools/prerender_site.py     # bake numbers into site/index.html
cd paper && latexmk -pdf main.tex
```

CI runs the tests and ruff on Python 3.10–3.13. It also regenerates `paper/generated/` and fails if
any number in the paper drifts from the data.

## The selector

Each (task, policy) pair gets a Gaussian prior on its expected score.
- **Tasks 0–49** have public 2025 per-task results. We scale them by a transfer factor. For Comet pt50
  it is estimated from our own development rollouts on the other tasks (`transfer_prior`,
  `estimate_transfer_factor`); for the winner checkpoints it was fixed before stage 2†.
- **Tasks 50–99** have no reference. A policy's level is the reference policy's level plus its mean
  paired difference on shared tasks, with the decided task left out. That level is shrunk toward a
  weak hyperprior and widened by the between-task spread (`paired_level`, `flat_level_prior`).

Development rollouts update the prior conjugately (`update`). The switching rules differ by task range:
- **Tasks 0–49 (the 13 routed in stage 2):** a challenger replaces the incumbent only if it has ≥ 2 of
  its own rollouts, beats the incumbent on ≥ 2 shared development instances, gains ≥ 0.01, and is
  not vetoed.
- **Tasks 50–99:** the highest eligible posterior wins if it gains ≥ 0.01 over the reference policy,
  subject to the veto. A specialist is a candidate only on the tasks it has rollouts for, and only
  with ≥ 2 rollouts in total. **One checkpoint per training run:** when two steps of one training
  run (the ymetz steps 6000 and 9999) win different tasks, every step is tried as the keeper and the
  best whole route is kept.

The paper's Algorithm 1 and Table 2 list every hyperparameter.

## Serving

`policybank.serving` implements the hidden-evaluation contract:
- **One task, one session.** Each container serves one task and one evaluator session, with batches
  of 1–10. A second concurrent connection is refused with close code 1013. Every new session starts
  from a reset policy.
- **Chunking.** The global chunk K=4 divides each policy's native replay of 32 or 20 actions, so the
  chunked stream equals the native one.
- **Fail-stop.** Malformed input, nonfinite actions, model exceptions and per-query timeouts (550 s,
  below the 600 s rule) are terminal (close code 1011) and stop the server. There is no retry, no
  substitute action, no fallback checkpoint and no automatic restart.
- **Disconnects.** An evaluator disconnect is not a policy failure: its session simply ends. Keepalive
  pings (every 30 s) drop a peer that vanished without closing, so the evaluator's reconnect is not
  refused as a second session. A failing or disconnecting *upstream* policy server is a policy
  failure.
- **Hung models.** Inference runs on a dedicated thread, and the CLI hard-exits after a failure, so a
  hung model cannot keep the container alive.

Put the contract in front of a real checkpoint served by any OpenPI-compatible policy server:

```bash
python -m policybank serve --upstream ws://localhost:8001 --policy pt50 --replay 32 --chunk 4 --port 8000
```

Add `--forward-reset` when the upstream is a native BEHAVIOR server that keeps per-episode state
and accepts `{"reset": True}`; otherwise restart the upstream per session. Without `--upstream`, the
server runs a deterministic scripted stand-in, for protocol tests.

A non-root container image for the server lives in [`docker/`](docker/); CI builds it and runs a
10-check smoke test of the full contract against it (`.github/workflows/serve-smoke.yml`).

## Disclosures

- Public results were produced with **Isaac Sim 6.0.1**. Isaac Sim 5.1 crashed with the cluster's
  GPU driver, and the organizers allowed Isaac 6 for public results. Hidden evaluation uses 5.1.
- Two duplicate completed cells were resolved by **completion order, regardless of score**:
  `spraying_for_bugs`/307 (kept 0.5, excluded 0.0) and `cook_brussels_sprouts`/303 (0.0 / 0.0).
- 716 episodes replayed 32 actions per query, 277 replayed 20, and 7 came from a recovery pass that
  replays 0. All are reported unchanged.
- The scorer copy bundled with the simulator divides by a 20-instance pool and gives 0.078. The
  published contract uses 10 instances and gives 0.156. No scorer or metrics file was edited.
- Some values in the paper come from pipeline logs that are not part of this release. The paper marks
  them with †, for example the 860† rollouts behind the stage-2 freeze and the transfer factors.
- **No model weights are redistributed here.** The publishers of the winner checkpoints and the
  four-task specialist declare Apache-2.0 at the pinned revisions. The ymetz card defers to its base checkpoint's terms. We found
  no explicit licence for the separately hosted Comet weights or the specialist used on tasks 96–97.
- **Hidden-evaluation readiness is unverified.**
  - All ten native images passed GPU startup and synthetic batch-1/batch-10 tests on an RTX 3090.
  - A strict-isolation test failed for all ten (CUDA saw no GPU); the cause is unresolved.
  - Full Isaac 5.1 episodes at 1 FPS on the organizers' GPU class have not been run.

## Credits

Team Comet ([openpi-comet](https://github.com/mli0603/openpi-comet)); Physical Intelligence
([OpenPI](https://github.com/Physical-Intelligence/openpi), π0/π0.5); Google (PaliGemma/Gemma);
Ilia Larchenko, Gleb Zarin and Akash Karnatak ([2025 winning solution](https://github.com/IliaLarchenko/behavior-1k-solution));
ymetz; JackLiu0406; amyjia1212; the Stanford BEHAVIOR-1K team; TACC (Stampede3).

## Citation

```bibtex
@techreport{kanr2026policybank,
  title       = {Policy Bank: Development-Selected Routing of Public Robot Policies for {BEHAVIOR-1K}},
  author      = {Balakrishna, Keshav and Gangerapu, Abhijay and Satarla, Rithik},
  institution = {Team KANR (Independent)},
  year        = {2026},
  note        = {2026 BEHAVIOR Challenge technical report},
  url         = {https://policy-bank.vercel.app}
}
```

Code: Apache-2.0 (see [LICENSE](LICENSE)). Model weights belong to their publishers.
