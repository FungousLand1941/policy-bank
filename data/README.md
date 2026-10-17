# Dataset

Built by `tools/build_dataset.py` from the evaluation pipeline's exports. Cluster paths, job
identifiers and run directories are removed. Everything else is kept.

| File | Rows | Contents |
|---|---|---|
| `tasks.json` | 100 | id, name, scene, mean demonstration length (s), natural-language instruction |
| `policies.json` | 10 | routed checkpoints: family, source repository, pinned revision, subfolder, replay length, lineage, licence status |
| `route.json` | 100 | frozen route: policy, stage (1/2), posterior expected q at freeze, fallback and its expected q; SHA-256 of the original route tables |
| `official_episodes.csv` | 1,000 | reported episodes (instances 301–310): q, success, steps, simulated seconds, normalized time, normalized arm/base distances, replay length, finish time (UTC), SHA-256 of the unchanged metrics file |
| `dev_rollouts.csv` | 1,146 | development ledger (instances 311–319): run label, policy label, q, success, steps, normalized time, flags for evaluation-time variants and non-default robot configuration, finish time (UTC) |
| `duplicates.json` | 2 | the two duplicate completed cells and the score-blind decision taken |

Notes

- `q` is the evaluator's `q_score.final`, the fraction of goal conditions satisfied. Q is the mean
  over tasks of the per-task mean over instances 301–310.
- An episode ends at success or at the step cap of 1.5 times the mean demonstration length.
  Normalized time ≈ 0.667 means the cap was reached.
- `policybank.data.load_dev(selection_only=True)` applies the filter used for selection:
  development instances, default configuration, no evaluation-time variant, and a routable label.
- The stage-2 route was frozen at 2026-10-13T12:54:00Z. `policybank.analysis.reproduce_stage2`
  uses only development rollouts finished before then.
- Instructions for tasks 50–99 come from the BEHAVIOR task prompts used by the Comet adapter.
