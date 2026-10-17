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
    fig.savefig(OUT / "tasks.pdf")
    plt.close(fig)


def fig_calibration(s):
    fig, ax = plt.subplots(figsize=(3.3, 3.0))
    colors = {1: ORANGE, 2: BLUE}
    for st in (1, 2):
        rs = [r for r in s["tasks"] if r["stage"] == st]
        ax.scatter([r["expected_q"] for r in rs], [r["q"] for r in rs], s=18, color=colors[st],
                   edgecolors=SURFACE, linewidths=0.8, label=f"stage {st} ({len(rs)} tasks)", zorder=3)
    ax.plot([0, 0.8], [0, 0.8], color=MUTED, linewidth=1.0, zorder=2)
    ax.text(0.62, 0.66, "y = x", color=MUTED, fontsize=7, rotation=0)
    ax.set_xlim(0, 0.8)
    ax.set_ylim(-0.02, 1.0)
    ax.set_xlabel("Expected task score at freeze (posterior mean)")
    ax.set_ylabel("Realized task score")
    c = s["calibration"]
    ax.set_title(f"Spearman {c['spearman']:.2f} · mean {c['mean_expected']:.3f} → {c['mean_realized']:.3f}",
                 loc="left", fontsize=8, color=INK2)
    ax.legend(loc="upper left", fontsize=7)
    fig.savefig(OUT / "calibration.pdf")
    plt.close(fig)


def fig_policies(s):
    ps = sorted(s["policies"], key=lambda p: p["task_points"])
    fig, ax = plt.subplots(figsize=(3.3, 2.8))
    y = range(len(ps))
    ax.barh(y, [p["task_points"] for p in ps], height=0.62, color=[FAMILY[p["family"]] for p in ps], linewidth=0)
    for i, p in enumerate(ps):
        ax.text(p["task_points"] + 0.06, i, f"{p['tasks']} task{'s' if p['tasks'] != 1 else ''}",
                va="center", fontsize=6.5, color=INK2)
    ax.set_yticks(list(y))
    ax.set_yticklabels([p["policy"].replace("comet@", "").replace("w100@", "") for p in ps], fontsize=7)
    ax.grid(axis="y", visible=False)
    ax.set_xlim(0, max(p["task_points"] for p in ps) * 1.25)
    ax.set_xlabel("Task points contributed (sum of task scores)")
    handles = [Patch(color=FAMILY[k], label=v) for k, v in FAMILY_LABEL.items()]
    ax.legend(handles=handles, loc="lower right", fontsize=6.5)
    fig.savefig(OUT / "policies.pdf")
    plt.close(fig)


def fig_noise(s):
    fig, axes = plt.subplots(1, 3, figsize=(7.0, 1.95))
    ax = axes[0]
    h = s["q_histogram_deciles"]
    ax.bar([i / 10 + 0.05 for i in range(10)], h, width=0.075, color=BLUE, linewidth=0)
    ax.set_xlabel("Episode score q")
    ax.set_ylabel("Episodes")
    ax.set_title("Reported episodes (n = 1,000)", loc="left")
    ax.text(0.14, h[0] * 0.97, f"{h[0]} below 0.1", ha="left", va="top", color=INK2, fontsize=6.5)
    ax.set_ylim(0, h[0] * 1.08)
    ax.grid(axis="x", visible=False)

    ax = axes[1]
    inst = s["dev"]["instance_counts"]
    ks = sorted(inst, key=int)
    ax.bar(range(len(ks)), [inst[k] for k in ks], width=0.6, color=BLUE, linewidth=0)
    ax.set_xticks(range(len(ks)))
    ax.set_xticklabels(ks, rotation=45, fontsize=6.5)
    ax.set_xlabel("Development instance")
    ax.set_ylabel("Rollouts")
    ax.set_title(f"Dev rollouts ({s['dev']['share_instance_313']:.0%} on 313)", loc="left")
    ax.grid(axis="x", visible=False)

    ax = axes[2]
    pw = s["power"]
    xs = [float(k) for k in pw]
    ys = [pw[k] for k in pw]
    ax.plot(xs, ys, color=BLUE, linewidth=2, marker="o", markersize=4.5, markeredgecolor=SURFACE)
    ax.set_yscale("log")
    for x_, y_ in zip(xs, ys, strict=True):
        ax.annotate(f"{y_:,}", (x_, y_), textcoords="offset points", xytext=(4, 3), fontsize=6.5, color=INK2)
    ax.set_xlabel("Difference in task score to detect")
    ax.set_ylabel("Rollouts per policy")
    ax.set_title(f"80% power, s.d. {s['within_task_sd']:.2f}", loc="left")
    ax.set_xlim(0, 0.23)
    fig.tight_layout(w_pad=1.6)
    fig.savefig(OUT / "noise.pdf")
    plt.close(fig)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    s = load()
    fig_tasks(s)
    fig_calibration(s)
    fig_policies(s)
    fig_noise(s)
    print("figures:", sorted(p.name for p in OUT.glob("*.pdf")))


if __name__ == "__main__":
    main()
