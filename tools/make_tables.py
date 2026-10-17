#!/usr/bin/env python3
"""Write ``paper/generated/numbers.tex`` (macros) and LaTeX tables from ``results/summary.json``.

Every number quoted in the paper that is recomputable from ``data/`` comes through here, so the
PDF cannot drift from the data.  Values that come from pipeline logs are typed in the paper and
marked with a dagger.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "paper" / "generated"
sys.path.insert(0, str(ROOT))


def tex(s: str) -> str:
    return s.replace("_", r"\_").replace("@", r"@\allowbreak{}").replace("&", r"\&")


def disp(name: str) -> str:
    return tex(name).replace("π0.5", r"$\pi_{0.5}$")


def signed(x: float, digits: int = 2) -> str:
    """A signed number with a typographic minus for LaTeX."""
    s = f"{x:+.{digits}f}"
    return "$-$" + s[1:] if s.startswith("-") else s


def num(x: int) -> str:
    return f"{x:,}".replace(",", "{,}")


def worked_example():
    """The ymetz prior/posterior on task 69 with the released code (tasks 50-99 construction)."""
    from policybank.analysis import _stage2_setup
    from policybank.selection import flat_level_prior, noise_variance, paired_level, per_task_scores, update
    dev, _ = _stage2_setup()
    sc = per_task_scores(dev)
    level = paired_level(sc["comet@ymetz9999"], sc["s150997"], leave_out=69)
    prior = flat_level_prior(level)
    nv = noise_variance(sc["comet@ymetz9999"])
    post = update(prior, sc["comet@ymetz9999"].get(69, []), nv)
    return level, prior, nv, post, sc["comet@ymetz9999"].get(69, [])


def main():
    s = json.loads((ROOT / "results" / "summary.json").read_text(encoding="utf-8"))
    site = json.loads((ROOT / "site" / "data" / "results.json").read_text(encoding="utf-8"))
    pol = json.loads((ROOT / "data" / "policies.json").read_text(encoding="utf-8"))
    OUT.mkdir(parents=True, exist_ok=True)
    c, st, br = s["calibration"], s["stages"], s["calibration_breakdown"]
    sim, obs = s["simulation"]["rules"], s["simulation"]["observed"]
    strict, naive, bpost, orc = (sim["strict rules (ours)"], sim["best dev mean"], sim["best posterior"],
                                 sim["oracle"])
    curve = s["simulation"]["curve"]
    level, prior, nv, post, own69 = worked_example()
    rb = s["reproduction_baselines"]
    n = {
        "Qval": f"{s['Q']:.3f}", "Qfull": f"{s['Q']:.5f}", "Qlo": f"{s['Q_ci95'][0]:.3f}",
        "Qhi": f"{s['Q_ci95'][1]:.3f}", "Nepisodes": num(s["episodes"]),
        "Nsuccess": str(s["successes"]), "SuccessRate": f"{100 * s['success_rate']:.1f}",
        "Nnonzero": str(s["nonzero_tasks"]), "Nzero": str(s["zero_tasks"]),
        "Ntaskssuccess": str(s["tasks_with_success"]), "Nepnonzero": str(s["episodes_nonzero"]),
        "WithinSD": f"{s['within_task_sd']:.2f}", "WithinSDnz": f"{br['within_sd_nonzero_tasks']:.3f}",
        "Ntimeouts": str(s["timeouts"]),
        "Spearman": f"{c['spearman']:.2f}", "Pearson": f"{c['pearson']:.2f}",
        "MeanExpected": f"{c['mean_expected']:.3f}", "MeanRealized": f"{c['mean_realized']:.3f}",
        "OptimismGap": f"{c['mean_expected'] - c['mean_realized']:.3f}",
        "PredGain": f"{br['predicted_gain_Q']:.3f}", "FallbackTasks": str(br["fallback_tasks"]),
        "StageOneTasks": str(st["1"]["tasks"]), "StageTwoTasks": str(st["2"]["tasks"]),
        "StageOneQ": f"{st['1']['q_mean']:.3f}", "StageTwoQ": f"{st['2']['q_mean']:.3f}",
        "StageOneE": f"{st['1']['expected_mean']:.3f}", "StageTwoE": f"{st['2']['expected_mean']:.3f}",
        "StageOneZeroOwn": str(br["routed_with_zero_own_stage1"]),
        "DevRollouts": num(s["dev"]["rollouts"]), "DevLabels": str(s["dev"]["policies_tested"]),
        "DevEligible": str(s["dev"]["selection_eligible"]), "DevEligibleLabels": str(br["eligible_labels"]),
        "ShareThirteen": f"{100 * s['dev']['share_instance_313']:.0f}",
        "ShareThirteenElig": f"{100 * br['share_313_eligible']:.0f}",
        "PowerTwo": num(s["power"]["0.02"]), "PowerFive": str(s["power"]["0.05"]),
        "PowerTen": str(s["power"]["0.10"]), "PowerTwenty": str(s["power"]["0.20"]),
        "SelFive": str(br["selection_n"]["0.05"]), "SelTen": str(br["selection_n"]["0.10"]),
        "SelTwenty": str(br["selection_n"]["0.20"]),
        "HistZero": str(s["q_histogram_deciles"][0]),
        "ReproAgree": str(s["stage2_reproduction"]["agree"]), "ReproTasks": str(s["stage2_reproduction"]["tasks"]),
        "ReproRollouts": str(s["stage2_reproduction"]["dev_rollouts_used"]),
        "ReproYmetz": str(rb["ymetz_everywhere_agree"]), "ReproNondefault": str(rb["nondefault_tasks"]),
        "ReproNondefaultAgree": str(rb["nondefault_agree"]),
        "ReplayThirtyTwo": str(s["replay_counts"]["32"]), "ReplayTwenty": str(s["replay_counts"]["20"]),
        "ReplayZero": str(s["replay_counts"]["0"]), "DemoSpearman": f"{s['demo_length_spearman']:.2f}",
        "DepthZeroTasks": str(br["by_depth"]["0"]["tasks"]), "DepthOneTasks": str(br["by_depth"]["1"]["tasks"]),
        "DepthTwoTasks": str(br["by_depth"]["2+"]["tasks"]),
        "DepthZeroAbs": f"{abs(br['by_depth']['0']['gap_points']):.1f}",
        "DepthOneAbs": f"{abs(br['by_depth']['1']['gap_points']):.1f}",
        "DepthTwoAbs": f"{abs(br['by_depth']['2+']['gap_points']):.1f}",
        "DevAtFreeze": str(br["eligible_at_freeze"]),
        "WithinSDthree": f"{s['within_task_sd']:.3f}",
        "SimTemplate": str(s["simulation"]["template_rollouts"]),
        "ZeroC": f"{s['simulation']['zero_c']:.1f}",
        "ZeroShareOff": f"{100 * s['simulation']['zero_share_official']:.0f}",
        "ZeroShareDev": f"{100 * s['simulation']['zero_share_dev']:.0f}",
        "DepthZeroGap": f"{br['by_depth']['0']['gap_points']:+.1f}",
        "DepthOneGap": f"{br['by_depth']['1']['gap_points']:+.1f}",
        "DepthTwoGap": f"{br['by_depth']['2+']['gap_points']:+.1f}",
        "Kappa": f"{s['simulation']['kappa']:.2f}", "Sims": str(s["simulation"]["sims"]),
        "SimStrictTrue": f"{strict['true']:.3f}", "SimStrictClaim": f"{strict['claimed']:.3f}",
        "SimStrictOpt": f"{strict['optimism']:+.3f}", "SimStrictRegret": f"{strict['regret']:.3f}",
        "SimStrictRaw": f"{strict['raw_dev_gap']:.3f}",
        "SimNaiveTrue": f"{naive['true']:.3f}", "SimNaiveClaim": f"{naive['claimed']:.3f}",
        "SimNaiveOpt": f"{naive['optimism']:+.3f}",
        "SimPostTrue": f"{bpost['true']:.3f}", "SimPostOpt": f"{bpost['optimism']:+.3f}",
        "SimPostRaw": f"{bpost['raw_dev_gap']:.3f}",
        "SimRefTrue": f"{sim['reference only']['true']:.3f}", "SimOracle": f"{orc['true']:.3f}",
        "SimCostOfRules": f"{bpost['true'] - strict['true']:.3f}",
        "SimStrictEight": f"{curve['8']['strict rules (ours)']['true']:.3f}",
        "SimNaiveEight": f"{curve['8']['best dev mean']['true']:.3f}",
        "ObsClaimed": f"{obs['claimed']:.3f}", "ObsRealized": f"{obs['realized']:.3f}",
        "ObsOpt": f"{obs['optimism']:.3f}", "ObsRawGap": f"{obs['raw_dev_gap']:.3f}",
        "ObsPct": f"{100 * obs['reported_percentile']:.0f}",
        "ObsLo": f"{obs['reported_p05']:.3f}", "ObsHi": f"{obs['reported_p95']:.3f}",
        "ExLevel": f"{level.mean:.3f}", "ExLevelSd": f"{level.sd:.3f}",
        "ExPrior": f"{prior.mean:.3f}", "ExPriorSd": f"{prior.sd:.3f}", "ExNoise": f"{nv:.3f}",
        "ExPost": f"{post.mean:.3f}", "ExPostSd": f"{post.sd:.3f}",
    }
    assert own69 == [0.0], own69
    lines = [f"\\newcommand{{\\{k}}}{{{v}}}" for k, v in n.items()]
    (OUT / "numbers.tex").write_text("% generated by tools/make_tables.py\n" + "\n".join(lines) + "\n",
                                     encoding="utf-8", newline="\n")

    fam = {"comet": "Comet", "winner": "Winner", "winner100": "Specialist"}
    rows = []
    for p in s["policies"]:
        meta = pol[p["policy"]]
        rows.append(f"{disp(meta['display'])} & {fam[p['family']]} & {meta['replay']} & {p['tasks']} & "
                    f"{p['expected_mean']:.3f} & {p['q_mean']:.3f} & {p['successes']} & {p['task_points']:.2f} \\\\")
    (OUT / "policies.tex").write_text("\n".join(rows) + "\n", encoding="utf-8", newline="\n")

    bank = []
    for meta in pol.values():
        public = "/" in meta["source"]
        src = (tex(meta["source"]) + (f"/{tex(meta['subfolder'])}" if meta["subfolder"] else "")) if public \
            else "this work (continued training of pt50)"
        rev = meta["revision"][:7] if public else meta["revision"]
        bank.append(f"{disp(meta['display'])} & \\texttt{{\\footnotesize {src}}} & \\texttt{{\\footnotesize {rev}}} \\\\")
    (OUT / "bank.tex").write_text("\n".join(bank) + "\n", encoding="utf-8", newline="\n")

    scenes = sorted(s["scenes"].items(), key=lambda kv: -kv[1]["q_mean"])
    (OUT / "scenes.tex").write_text("\n".join(
        f"\\texttt{{{tex(k)}}} & {v['tasks']} & {v['q_mean']:.3f} \\\\" for k, v in scenes) + "\n", encoding="utf-8", newline="\n")

    top = sorted(s["tasks"], key=lambda r: -r["q"])[:10]
    (OUT / "toptasks.tex").write_text("\n".join(
        f"{r['id']} & {r['name'].replace('_', ' ')} & {disp(pol[r['policy']]['display'])} & {r['expected_q']:.3f} & "
        f"{r['q']:.3f} & {r['successes']} \\\\" for r in top) + "\n", encoding="utf-8", newline="\n")

    label = {"0": "0", "1": "1", "2+": "2 or more"}
    (OUT / "depth.tex").write_text("\n".join(
        f"{label[k]} & {v['tasks']} & {v['expected']:.3f} & {v['realized']:.3f} & {signed(v['gap_points'])} \\\\"
        for k, v in br["by_depth"].items()) + "\n", encoding="utf-8", newline="\n")
    (OUT / "stagesplit.tex").write_text("\n".join(
        f"{k.replace('stage', 'Stage', 1).replace('0-49', '0--49').replace('50-99', '50--99')} & {v['tasks']} & {v['expected']:.3f} & {v['realized']:.3f} & "
        f"{signed(v['gap_points'])} \\\\" for k, v in br["by_stage"].items()) + "\n", encoding="utf-8", newline="\n")

    order = ["reference only", "best dev mean", "best posterior", "strict rules (ours)", "oracle"]
    names = {"reference only": "Reference policy only", "best dev mean": "Highest raw development mean",
             "best posterior": "Highest posterior, no rules", "strict rules (ours)": "Strict rules (ours)",
             "oracle": "Oracle (true best candidate)"}
    simrows = []
    for k in order:
        v = sim[k]
        claim = "--" if v["claimed"] is None else f"{v['claimed']:.3f}"
        opt = "--" if v["optimism"] is None else signed(v["optimism"], 3)
        raw = "--" if k in ("reference only", "oracle") else signed(v["raw_dev_gap"], 3)
        simrows.append(f"{names[k]} & {v['true']:.3f} & {v['true_p05']:.3f}--{v['true_p95']:.3f} & {claim} & "
                       f"{opt} & {raw} & {v['regret']:.3f} \\\\")
    (OUT / "simulation.tex").write_text("\n".join(simrows) + "\n", encoding="utf-8", newline="\n")

    short = {p: pol[p]["display"] for p in pol}
    app = []
    for t in site["tasks"]:
        lo, hi = t["q_ci95"]
        app.append(f"{t['id']} & {t['name'].replace('_', ' ')} & {disp(short[t['policy']])} & {t['stage']} & "
                   f"{t['own_dev_n']} & {t['expected']:.3f} & {t['q']:.3f} & {lo:.2f}--{hi:.2f} & {t['successes']} \\\\")
    (OUT / "alltasks.tex").write_text("\n".join(app) + "\n", encoding="utf-8", newline="\n")
    print("wrote", sorted(p.name for p in OUT.iterdir()))


if __name__ == "__main__":
    main()
