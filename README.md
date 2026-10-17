# Policy Bank

**Development-selected routing of public robot policies for BEHAVIOR-1K.**
Team KANR's entry and technical report for the 2026 BEHAVIOR Challenge.

Keshav Balakrishna · Abhijay Gangerapu · Rithik Satarla (Independent)

[Paper (PDF)](paper/policy-bank.pdf) · [Project page](https://policy-bank.vercel.app) · [Data](data/)

---

The challenge asks one system to complete 100 long-horizon household tasks in simulation. Instead of
training one generalist, we route each task to one of ten public or lightly fine-tuned
vision-language-action checkpoints. Every routing decision uses only development instances
(311–320). A hierarchical empirical-Bayes model combines public reference results,
policy-level estimates paired against a reference policy, and development rollouts. Conservative
rules keep the incumbent unless a challenger also beats it on shared instances.

| | |
|---|---|
| Challenge score Q (public instances 301–310, Isaac Sim 6.0.1) | **0.156** (95% CI 0.144–0.168) |
| Episodes | 1,000 (100 tasks × 10 instances, one run per cell) |
| Tasks with partial credit / full successes | 71 / 37 episodes |
| Expected vs realized (Spearman, mean) | 0.68; 0.206 → 0.156 |
| Rollout noise within a task | s.d. 0.20, so separating a 0.05 difference takes about 250 rollouts per policy |
| Selector reimplementation vs frozen stage-2 route | 48 / 50 tasks |

Q is a self-evaluated score on public instances, not a hidden-test result. See
[Disclosures](#disclosures).

## Repository

```
policybank/            Python package
  metrics.py           challenge Q, bootstrap CI, rollout noise, power
  selection.py         priors, conjugate updates, switching rules, family consolidation
  routing.py           frozen route: validation, canonical SHA-256, image map
  provenance.py        metrics-file audit, coverage, score-blind duplicate resolution
  analysis.py          every number in the paper
  serving/             fail-stop websocket server: codec, contract, chunk executor, client
  cli.py               `python -m policybank ...`
data/                  released dataset (see data/README.md)
results/summary.json   output of `policybank analyze`
paper/                 LaTeX source, generated tables and figures, compiled PDF
site/                  static project page (deployed on Vercel)
tools/                 dataset build, figures, tables, site export
tests/                 53 tests (metrics, selection, routing, provenance, serving)
```

## Quick start

```bash
pip install -e ".[dev]"          # numpy, msgpack, websockets, pytest
python -m pytest -q              # 53 tests, about 3 s
python -m policybank score       # Q = 0.156054 (95% CI 0.1444-0.1676)
python -m policybank route --images
python -m policybank select      # re-run the stage-2 selection, compare with the frozen route
python -m policybank analyze --out results/summary.json
```

Regenerate the paper's figures, tables and the website data from `data/`:

```bash
pip install -e ".[figures]"
python tools/export_site_data.py   # results/summary.json + site/data/results.json
python tools/make_figures.py       # paper/figures/*.pdf
python tools/make_tables.py        # paper/generated/*.tex
cd paper && latexmk -pdf main.tex
```

## The selector in one paragraph

Each (task, policy) pair gets a Gaussian prior on its expected score. **Tasks 0–49** have public
2025 per-task results, which we scale by a transfer factor estimated from our own development
rollouts on the other tasks (`transfer_prior`, `estimate_transfer_factor`). **Tasks 50–99** have no
reference, so a policy's level is the reference policy's level plus its mean paired difference on
shared tasks, shrunk toward its family (`paired_level`, `flat_level_prior`). Development rollouts
update the prior conjugately (`update`). A challenger replaces the incumbent only with at least two
of its own rollouts, a win on shared instances (the development guard), a gain of at least 0.01, no
veto, and one checkpoint per family (`decide`, `one_per_family`, `select_by_level`).

## Serving

`policybank.serving` contains the hidden-evaluation contract. Each container serves one task and
one evaluator session, with batches of 1–10. The global chunk K=4 divides each policy's native
replay of 32 or 20 actions, so the chunked action stream equals the native one. Malformed input,
nonfinite actions, exceptions and timeouts are terminal (close code 1011): there is no retry, no
substitute action and no fallback checkpoint. Real checkpoints plug in through the `Policy` protocol
(`plan(obs, n) -> (n, horizon, 23)`, `reset()`). The package ships only a scripted stand-in:

```bash
python -m policybank serve --replay 32 --chunk 4 --port 8000
```

## Disclosures

- Public results were produced with **Isaac Sim 6.0.1**. Isaac Sim 5.1 crashed with the cluster's
  GPU driver, and the organizers allowed Isaac 6 for public results. Hidden evaluation uses 5.1.
- Two duplicate completed cells were resolved by **completion order, regardless of score**:
  `spraying_for_bugs`/307 (kept 0.5, excluded 0.0) and `cook_brussels_sprouts`/303 (0.0 / 0.0).
- 716 episodes replayed 32 actions per query, 277 replayed 20, and 7 replayed 0 in a recovery pass.
  All are reported unchanged.
- The scorer copy bundled with the simulator divides by a 20-instance pool and gives 0.078. The
  published contract uses 10 instances and gives 0.156. No scorer or metrics file was edited.
- **No model weights are redistributed here.** The winner checkpoints and the four-task specialist
  are Apache-2.0 at the pinned revisions. The ymetz card defers to its base checkpoint's terms. We
  found no explicit licence for the separately hosted Comet weights or the specialist used on tasks
  96–97.
- All ten native images passed GPU startup and synthetic-input batch-1 and batch-10 tests on an
  RTX 3090. A strict-isolation test failed for all ten (CUDA saw no GPU) and remains unresolved. Full
  hidden-protocol qualification (Isaac 5.1, 1 FPS, organizer GPU class) has not been completed.

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
  url         = {https://github.com/FungousLand1941/policy-bank}
}
```

Code: Apache-2.0 (see [LICENSE](LICENSE)). Model weights belong to their publishers.
