# Documentation

Documentation for `policybank`, the code and data release accompanying Team KANR's technical report
for the 2026 BEHAVIOR-1K Challenge. The [top-level README](../README.md) has the summary, quick start
and disclosures; the [paper](../paper/policy-bank.pdf) has the full argument; the project page is
<https://policy-bank.vercel.app>.

| Page | What it covers |
|---|---|
| [README.md](README.md) | This index and the conventions shared by all pages. |
| [method.md](method.md) | The selection method: what the release can and cannot reproduce, notation, the Gaussian model and conjugate update, noise pooling, transfer priors (tasks 0–49), paired policy levels (tasks 50–99), switching rules, one checkpoint per training run, the two-stage freeze, a worked example (`comet@ymetz9999` on task 69) and every hyperparameter. |
| [simulation.md](simulation.md) | The posterior-predictive study of the selection rules: what is simulated, the zero-inflated outcome model, the five rules, the outputs, the 300-world results, how to read and run it, and its limitations. |
| [serving.md](serving.md) | The hidden-evaluation contract: deployment model, wire format, sessions, observations, replies and resets, chunking, terminal failures and close codes, peer disconnects, timeouts, health endpoints, how to put a real checkpoint behind it, a client example, and what is tested. |
| [data.md](data.md) | Data dictionary for every file in `data/` (including the 1,000 original metric files in `data/metrics/`), the eligibility filter, freeze timestamps, hashes, and how the dataset was built. |
| [reproducing.md](reproducing.md) | Step by step: install, tests, every CLI command with its real output, regenerating the summary, tables, figures, paper and site, line endings, CI, and auditing raw metric files. |
| [api.md](api.md) | Module-by-module reference of the public Python API with signatures. |

Related files elsewhere:

- [`../README.md`](../README.md): project summary, headline results, quick start and disclosures.
- [`../paper/policy-bank.pdf`](../paper/policy-bank.pdf): the technical report.
- [`../docker/README.md`](../docker/README.md): the serving container image and its smoke test.
- [`../data/README.md`](../data/README.md): short description of the dataset.
- [`../notebooks/reproduce.ipynb`](../notebooks/reproduce.ipynb): the headline numbers in a notebook
  ([open in Colab](https://colab.research.google.com/github/FungousLand1941/policy-bank/blob/main/notebooks/reproduce.ipynb)).
- <https://policy-bank.vercel.app>: the project page, with the per-task results and downloadable data.

## Conventions

- Values marked † come from pipeline logs and reports that are not part of the release; they cannot be
  recomputed from `data/`. Every other number in these pages is produced by the released code from the
  released data.
- "Tasks 0–49" are the tasks with public 2025 per-task reference results; "tasks 50–99" are new in
  2026. Instances 301–310 are the reporting instances, 311–320 development, 321–340 hidden.
- $Q$ is the challenge score: the mean over 100 tasks of each task's mean `q` over the ten reporting
  instances, with missing cells counted as zero. It is a self-evaluated score on public instances
  (Isaac Sim 6.0.1), not a hidden-test result. The released value is 0.156054 (95% CI 0.1434–0.1685,
  task-stratified bootstrap with 10,000 resamples).
