#!/usr/bin/env python3
"""Render the paper's figures from ``results/summary.json`` into ``paper/figures/``.

Run ``python tools/export_site_data.py`` first (it writes the summary).  Needs matplotlib.
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "paper" / "figures"

# Reference palette (light mode): categorical slots 1-3 validate all-pairs for CVD.
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
INK, INK2, MUTED, GRID, AXIS, SURFACE = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7", "#ffffff"
FAMILY = {"comet": BLUE, "winner": ORANGE, "winner100": AQUA}
FAMILY_LABEL = {"comet": "Comet π0.5 family", "winner": "2025 winner", "winner100": "Winner-format specialist"}

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 8, "axes.titlesize": 9, "axes.labelsize": 8,
    "axes.edgecolor": AXIS, "axes.linewidth": 0.8, "axes.labelcolor": INK2, "axes.titlecolor": INK,
    "xtick.color": MUTED, "ytick.color": MUTED, "xtick.labelcolor": INK2, "ytick.labelcolor": INK2,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6, "axes.axisbelow": True,
    "axes.spines.top": False, "axes.spines.right": False, "legend.frameon": False,
    "pdf.fonttype": 42, "savefig.bbox": "tight", "savefig.pad_inches": 0.02,
})


def load():
    return json.loads((ROOT / "results" / "summary.json").read_text(encoding="utf-8"))


def fig_tasks(s):
    rows = sorted(s["tasks"], key=lambda r: (-r["q"], -r["expected_q"]))
    fig, ax = plt.subplots(figsize=(7.0, 2.3))
    x = range(len(rows))
    ax.bar(x, [r["q"] for r in rows], width=0.72, color=[FAMILY[r["family"]] for r in rows], linewidth=0)
    ax.scatter(x, [r["expected_q"] for r in rows], marker="_", s=22, color=INK, linewidths=1.2, zorder=3)
    ax.set_xlim(-0.8, len(rows) - 0.2)
    ax.set_ylim(0, 1.0)
    ax.set_xticks([])
    ax.grid(axis="x", visible=False)
    ax.set_ylabel("Task score (mean q over 301–310)")
    ax.set_xlabel("100 tasks, sorted by realized score")
    zero = sum(r["q"] == 0 for r in rows)
    ax.axvspan(len(rows) - zero - 0.5, len(rows) - 0.2, color="#f3f2ee", zorder=0, linewidth=0)
    ax.text(len(rows) - zero / 2 - 0.5, 0.9, f"{zero} tasks score 0", ha="center", va="top", color=INK2, fontsize=7)
    handles = [Patch(color=FAMILY[k], label=v) for k, v in FAMILY_LABEL.items()]
    handles.append(Line2D([], [], color=INK, marker="_", linestyle="none", markersize=7, label="expected at freeze"))
    ax.legend(handles=handles, loc="upper center", ncol=4, fontsize=7, bbox_to_anchor=(0.5, 1.16))
    fig.savefig(OUT / "tasks.pdf", metadata={"CreationDate": None})
    plt.close(fig)


DEPTH = {"0": (BLUE, "0 own rollouts"), "1": (ORANGE, "1 own rollout"), "2+": (AQUA, "2 or more")}


def _depth(n):
    return "0" if n == 0 else "1" if n == 1 else "2+"


def fig_calibration(s):
    own = {int(k): v for k, v in s["calibration_breakdown"]["own_dev_n"].items()}
    fig, ax = plt.subplots(figsize=(3.3, 3.9))
    for key, (color, _label) in DEPTH.items():
        for st, filled in ((2, True), (1, False)):
            rs = [r for r in s["tasks"] if _depth(own[r["id"]]) == key and r["stage"] == st]
            # Deterministic jitter so the 29 zero-score tasks do not hide each other.
            ys = [r["q"] if r["q"] > 0 else -0.012 * (1 + (r["id"] % 3)) for r in rs]
            ax.scatter([r["expected_q"] for r in rs], ys, s=20, zorder=3, linewidths=1.0,
                       facecolors=color if filled else SURFACE, edgecolors=color)
    ax.plot([0, 0.8], [0, 0.8], color=MUTED, linewidth=1.0, zorder=2)
    ax.text(0.66, 0.70, "y = x", color=MUTED, fontsize=7)
    ax.set_xlim(0, 0.8)
    ax.set_ylim(-0.05, 0.8)
    ax.set_aspect("equal")
    ax.set_xlabel("Expected task score at freeze (posterior mean)")
    ax.set_ylabel("Realized task score")
    c = s["calibration"]
    ax.set_title(f"Spearman {c['spearman']:.2f} · mean {c['mean_expected']:.3f} → {c['mean_realized']:.3f}",
                 loc="left", fontsize=8, color=INK2)
    handles = [Line2D([], [], marker="o", linestyle="none", markersize=5, markerfacecolor=col,
                      markeredgecolor=col, label=lab) for col, lab in DEPTH.values()]
    handles += [Line2D([], [], marker="o", linestyle="none", markersize=5, markerfacecolor=SURFACE,
                       markeredgecolor=INK2, label="stage 1 (hollow)")]
    ax.legend(handles=handles, loc="upper center", fontsize=6.3, ncol=2, title="routed policy's own dev rollouts",
              title_fontsize=6.3, bbox_to_anchor=(0.5, -0.2))
    fig.savefig(OUT / "calibration.pdf", metadata={"CreationDate": None})
    plt.close(fig)


def fig_simulation(s):
    sim = s["simulation"]
    order = ["reference only", "best dev mean", "best posterior", "strict rules (ours)", "oracle"]
    names = {"reference only": "Reference only", "best dev mean": "Best raw dev mean",
             "best posterior": "Best posterior", "strict rules (ours)": "Strict rules (ours)",
             "oracle": "Oracle"}
    fig, axes = plt.subplots(1, 2, figsize=(7.0, 2.6), gridspec_kw={"width_ratios": [1.25, 1]})
    ax = axes[0]
    for i, k in enumerate(order):
        v = sim["rules"][k]
        y = len(order) - 1 - i
        ax.plot([v["true_p05"], v["true_p95"]], [y, y], color=BLUE, linewidth=2, alpha=0.35,
                solid_capstyle="round")
        ax.scatter([v["true"]], [y], s=28, color=BLUE, edgecolors=SURFACE, linewidths=1.0, zorder=3)
        if v["claimed"] is not None and k != "oracle":
            ax.scatter([v["claimed"]], [y], s=34, marker="D", facecolors=SURFACE, edgecolors=ORANGE,
                       linewidths=1.3, zorder=4)
            ax.annotate(f"claims {v['claimed']:.3f}", (v["claimed"], y), textcoords="offset points",
                        xytext=(6, -2.5), fontsize=6.3, color=INK2)
    obs = sim["observed"]
    ax.axvline(obs["realized"], color=MUTED, linewidth=1, linestyle=(0, (2, 2)))
    ax.text(obs["realized"] + 0.003, len(order) - 0.75, f"our reported score {obs['realized']:.3f}",
            fontsize=6.3, color=INK2)
    ax.set_yticks(range(len(order)))
    ax.set_yticklabels([names[k] for k in reversed(order)], fontsize=7)
    ax.set_ylim(-0.6, len(order) - 0.4)
    ax.set_xlim(0.03, 0.36)
    ax.grid(axis="y", visible=False)
    ax.set_xlabel("Mean task score on tasks 50–99")
    ax.set_title(f"Rules in {sim['sims']} simulated worlds", loc="left")
    handles = [Line2D([], [], marker="o", color=BLUE, linestyle="-", linewidth=2, alpha=0.8, markersize=5,
                      label="true score (90% range)"),
               Line2D([], [], marker="D", linestyle="none", markerfacecolor=SURFACE, markeredgecolor=ORANGE,
                      markersize=5, label="score the rule claims")]
    ax.legend(handles=handles, loc="upper center", fontsize=6.3, ncol=2, bbox_to_anchor=(0.5, -0.27))

    ax = axes[1]
    ms = sorted(sim["curve"], key=int)
    xs = [int(m) for m in ms]
    for k, col, lab in (("oracle", MUTED, "oracle"), ("best dev mean", ORANGE, "best raw dev mean"),
                        ("strict rules (ours)", BLUE, "strict rules (ours)")):
        ys = [sim["curve"][m][k]["true"] for m in ms]
        lo = [sim["curve"][m][k]["true_p05"] for m in ms]
        hi = [sim["curve"][m][k]["true_p95"] for m in ms]
        ax.fill_between(xs, lo, hi, color=col, alpha=0.10, linewidth=0)
        ax.plot(xs, ys, color=col, linewidth=2, marker="o", markersize=4, markeredgecolor=SURFACE, label=lab)
    ax.set_xscale("log", base=2)
    ax.set_xticks(xs)
    ax.set_xticklabels([f"×{x}" for x in xs])
    ax.set_xlabel("Development budget (× our ledger)")
    ax.set_ylabel("True mean task score")
    ax.set_title("Value of more development rollouts", loc="left")
    ax.legend(loc="lower right", fontsize=6.3)
    fig.tight_layout(w_pad=2.0)
    fig.savefig(OUT / "simulation.pdf", metadata={"CreationDate": None})
    plt.close(fig)


def fig_noise(s):
    fig, axes = plt.subplots(1, 3, figsize=(7.0, 2.2))
    ax = axes[0]
    h = s["q_histogram_deciles"]
    ax.bar([i / 10 + 0.05 for i in range(10)], h, width=0.075, color=BLUE, linewidth=0)
    ax.set_xticks([0, 0.2, 0.4, 0.6, 0.8, 1.0])
    ax.set_xlabel("Episode score q (bins of 0.1)")
    ax.set_ylabel("Episodes")
    ax.set_title("Reported episodes (n = 1,000)", loc="left")
    ax.text(0.14, h[0] * 0.97, f"{h[0]} below 0.1", ha="left", va="top", color=INK2, fontsize=6.5)
    ax.set_ylim(0, h[0] * 1.08)
    ax.grid(axis="x", visible=False)

    ax = axes[1]
    inst = dict(s["dev"]["instance_counts"])
    inst.setdefault("320", 0)
    ks = sorted(inst, key=int)
    ax.bar(range(len(ks)), [inst[k] for k in ks], width=0.6, color=BLUE, linewidth=0)
    ax.set_xticks(range(len(ks)))
    ax.set_xticklabels(ks, rotation=45, fontsize=6.5)
    ax.set_xlabel("Development instance")
    ax.set_ylabel("Rollouts")
    ax.set_title(f"Dev ledger ({s['dev']['share_instance_313']:.0%} on 313)", loc="left")
    ax.grid(axis="x", visible=False)

    ax = axes[2]
    pw, sel = s["power"], s["calibration_breakdown"]["selection_n"]
    xs = [float(k) for k in pw]
    ax.plot(xs, [pw[k] for k in pw], color=BLUE, linewidth=2, marker="o", markersize=4.5,
            markeredgecolor=SURFACE, label="significance test")
    xs2 = [float(k) for k in sel]
    ax.plot(xs2, [sel[k] for k in sel], color=ORANGE, linewidth=2, marker="o", markersize=4.5,
            markeredgecolor=SURFACE, label="pick the better one")
    ax.set_yscale("log")
    for x_, y_ in zip(xs, [pw[k] for k in pw], strict=True):
        ax.annotate(f"{y_:,}", (x_, y_), textcoords="offset points", xytext=(4, 3), fontsize=6.3, color=INK2)
    for x_, y_ in zip(xs2, [sel[k] for k in sel], strict=True):
        ax.annotate(f"{y_:,}", (x_, y_), textcoords="offset points", xytext=(4, 3), fontsize=6.3, color=INK2)
    ax.set_xlabel("True difference in task score")
    ax.set_ylabel("Rollouts per policy (log)")
    ax.set_title(f"80% power / 80% correct, s.d. {s['within_task_sd']:.2f}", loc="left")
    ax.set_xlim(0, 0.23)
    ax.set_ylim(1, 5000)
    ax.legend(loc="upper center", fontsize=6.3, ncol=2, bbox_to_anchor=(0.5, -0.3))
    fig.tight_layout(w_pad=1.6)
    fig.savefig(OUT / "noise.pdf", metadata={"CreationDate": None})
    plt.close(fig)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    s = load()
    fig_tasks(s)
    fig_calibration(s)
    fig_simulation(s)
    fig_noise(s)
    print("figures:", sorted(p.name for p in OUT.glob("*.pdf")))


if __name__ == "__main__":
    main()
