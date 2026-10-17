# Changelog

## v1.0.0 — 2026-10-17

First public release of Team KANR's 2026 BEHAVIOR Challenge technical report, code and data.

### Results
- Frozen per-task route over ten vision-language-action checkpoints, chosen from development
  rollouts only. Self-evaluated challenge score on the public reporting instances (Isaac Sim 6.0.1):
  **Q = 0.156 (95% CI 0.143–0.168)** over 1,000 episodes. 71 tasks score above zero; 37 episodes
  in 15 tasks succeed. This is not a hidden-test score.
- Calibration analysis: development expectations ranked tasks moderately well (Spearman 0.68) but
  were optimistic by 0.050 on average. The gap sits where the routed policy had zero or one own
  development rollout.
- Posterior-predictive simulation of the selection procedure (tasks 50–99, zero-inflated Beta
  outcomes fitted to the reported episodes). Within the model:
  - choosing by raw development means delivers a worse route and overclaims by about 0.12;
  - the posterior's claims stay calibrated;
  - an oracle over the same candidates adds only about 0.04.

### Paper
- `paper/policy-bank.pdf` (15 pages). The LaTeX source in `paper/` takes every quoted number from
  `paper/generated/`, which is produced from the data by `tools/make_tables.py`. Pipeline-only
  values are marked with a dagger.

### Code (`policybank`)
- `metrics`: challenge Q, a bootstrap CI that is rescaled for ten instances and independent of input
  order, rollout noise, and power for testing and for selection.
- `selection`: transfer and paired-level priors, conjugate updates, switching rules (development
  guard, margin, veto, scope) and the one-checkpoint-per-training-run search (exhaustive within a run, greedy across runs).
- `simulate`: posterior-predictive study of selection rules.
- `routing` and `provenance`: canonical route hash, metrics-file audit, score-blind duplicate
  resolution, and `policybank verify`.
- `serving`: fail-stop websocket server.
  - Session behaviour: one task and one session per container, a reset at the start of every
    session, and keepalive pings that drop half-open peers.
  - Failures: upstream failures are terminal (close code 1011); a second session is refused (1013).
  - `OpenPIRemotePolicy` fronts real OpenPI-compatible checkpoints, with optional reset forwarding.
- CLI: `python -m policybank {score,route,select,simulate,analyze,verify,serve}`.
- 127 tests (one skipped on Windows) (unit, property, serving integration, CLI subprocess). CI covers:
  - the tests and ruff on Python 3.10–3.13;
  - a check that every number in the paper still regenerates from the data;
  - a container smoke test.

### Data
- Route, tasks, policies (pinned sources and revisions), per-episode results, the development
  ledger, the duplicate-cell ledger, and **all 1,000 unchanged evaluator metric files** in
  `data/metrics/`, each verified by SHA-256.

### Website
- https://policy-bank.vercel.app — results explorer, selector demo, calibration and simulation
  analyses, reproduction panel and downloads. Pages are pre-rendered, so they also read without
  JavaScript.

### Known limitations
- Public results used Isaac Sim 6.0.1. Hidden evaluation uses Isaac Sim 5.1.
- Hidden-protocol qualification of the native images (Isaac 5.1, 1 FPS, organizer GPU class) has
  not been completed, and a strict-isolation GPU test failed for all ten images for a cause not yet
  determined.
- Model weights are not redistributed. Licence status per checkpoint is listed in
  `data/policies.json`.
