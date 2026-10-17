#!/usr/bin/env python3
"""Pre-render the project page from site/data/results.json.

Writes every bound number (elements carrying data-bind / data-fmt) and the generated
blocks (<!-- prerender:NAME --> ... <!-- /prerender:NAME -->) and the content of <meta>
tags that carry a data-tpl template ("{path|fmt}" placeholders) into site/index.html as
static text, so the page reads correctly without JavaScript and for crawlers. app.js
re-binds the same values at runtime with the same formatters; keep fmt(), resolve(),
the colour mapping and the card / sentence templates in sync with site/app.js.

    python tools/prerender_site.py            # update site/index.html
    python tools/prerender_site.py --check    # exit 1 if index.html is stale
    python tools/prerender_site.py --images   # also write og.png and apple-touch-icon.png
                                              # (needs matplotlib)
"""
from __future__ import annotations

import argparse
import html
import json
import math
import re
import sys
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

SITE = Path(__file__).resolve().parent.parent / "site"
MINUS = "\u2212"

# ---------------------------------------------------------------- formatting (= app.js fmt)


def to_fixed(v: float, d: int) -> str:
    """Number.prototype.toFixed: exact binary value, ties away from zero."""
    q = Decimal(float(v)).quantize(Decimal(1).scaleb(-d), rounding=ROUND_HALF_UP)
    s = f"{q:.{d}f}"
    return MINUS + s[1:] if s.startswith("-") else s


def js_round(v: float) -> int:
    return math.floor(v + 0.5)


def js_str(v) -> str:
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def fmt(v, f: str) -> str:
    if f == "int":
        return f"{js_round(v):,}"
    if f in ("f1", "f2", "f3", "f4"):
        return to_fixed(v, int(f[1]))
    if f == "pct0":
        return f"{js_round(v * 100)}%"
    if f == "pct1":
        return to_fixed(v * 100, 1) + "%"
    if f == "sp1":
        return ("+" if v >= 0 else MINUS) + to_fixed(abs(v), 1)
    if f == "sp2":
        return ("+" if v >= 0 else MINUS) + to_fixed(abs(v), 2)
    if f == "x100f1":
        return to_fixed(v * 100, 1)
    if f == "ord":
        n = js_round(v * 100)
        t = n % 100
        suf = "th" if 11 <= t <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
        return f"{n}{suf}"
    if f == "utc":
        m = re.match(r"^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2})", str(v))
        return f"{m.group(1)} at {m.group(2)} UTC" if m else str(v)
    if f == "utcday":
        m = re.match(r"^\d{4}-(\d{2})-(\d{2})T(\d{2}:\d{2})", str(v))
        return f"{m.group(3)} UTC on {int(m.group(2))} {MONTHS[int(m.group(1)) - 1]}" if m else str(v)
    return js_str(v)


MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September",
          "October", "November", "December"]


def resolve(o, path: str):
    """Dot paths where keys may themselves contain dots ("0.05"): longest key wins."""
    seg = path.split(".")
    i = 0
    while i < len(seg):
        hit = False
        for j in range(len(seg), i, -1):
            k = ".".join(seg[i:j])
            if isinstance(o, dict) and k in o:
                o, i, hit = o[k], j, True
                break
            if isinstance(o, list) and k.isdigit() and int(k) < len(o):
                o, i, hit = o[int(k)], j, True
                break
        if not hit:
            return None
    return o


def eval_bind(o, expr: str):
    vals = [resolve(o, p.strip()) for p in expr.split(" - ")]
    if any(v is None for v in vals):
        return None
    out = vals[0]
    for v in vals[1:]:
        out = out - v
    return out


def humanize(name: str) -> str:
    t = name.replace("_", " ")
    t = re.sub(r"^re ", "re-", t)
    return t[:1].upper() + t[1:]


# ---------------------------------------------------------------- colours (= app.js assignColors)

FAMVAR = {"comet": "comet", "winner": "winner", "winner100": "w100"}
FAMILY = {"comet": "comet", "winner": "winner", "winner100": "winner-format specialist"}
REFERENCE = "s150997"  # the weak reference policy, incumbent on tasks 50-99
STEPS = {2: [1, 0], 4: [2, 0, 3, 1]}
# Light-mode hexes of the CSS ramps, for the PNG images only.
LIGHT_HEX = {
    "comet": ["#003b7a", "#015bb5", "#3280de", "#62a6fe"],
    "winner": ["#6a2201", "#9e3703", "#d25117", "#fd7845"],
    "w100": ["#066947", "#14ac77"],
}


def assign_colors(policies):
    fams: dict[str, list] = {}
    for p in policies:
        fams.setdefault(p["family"], []).append(p)
    var, hexes = {}, {}
    for f, arr in fams.items():
        arr = sorted(arr, key=lambda p: (-p["tasks"], -p["task_points"], p["policy"]))
        order = STEPS[2] if len(arr) <= 2 else STEPS[4]
        fv = FAMVAR.get(f, "comet")
        for i, p in enumerate(arr):
            step = order[min(i, len(order) - 1)]
            var[p["policy"]] = f"var(--{fv}-{step})"
            hexes[p["policy"]] = LIGHT_HEX[fv][step]
    return var, hexes


# ---------------------------------------------------------------- generated blocks

E = html.escape


def bank_cards(D, color) -> str:
    out = []
    for p in sorted(D["policies"], key=lambda p: -p["task_points"]):
        hexrev = re.fullmatch(r"[0-9a-fA-F]{40}", p["revision"]) is not None
        rev = p["revision"][:7] if hexrev else p["revision"]
        src = (f'<a href="https://huggingface.co/{E(p["source"])}">{E(p["source"])}</a>'
               if "/" in p["source"] else f'<span>{E(p["source"])}</span>')
        sub = f' / <code>{E(p["subfolder"])}</code>' if p["subfolder"] else ""
        ours = '<span class="badge ours">ours</span>' if p["kind"] == "ours" else ""
        n = p["tasks"]

        def stat(v, label):
            return f"<div><b>{E(v)}</b><span>{E(label)}</span></div>"

        out.append(
            '<article class="pc">'
            f'<div class="pc-head"><span class="sw" style="background:{color[p["policy"]]}"></span>'
            f'<div><h3>{E(p["display"])}</h3><div class="pid">{E(p["policy"])}</div></div></div>'
            f'<div class="badges"><span class="badge">{E(FAMILY.get(p["family"], p["family"]))}</span>{ours}</div>'
            '<div class="pc-stats">'
            + stat(str(n), "tasks routed") + stat(fmt(p["q_mean"], "f3"), "realized q")
            + stat(fmt(p["expected_mean"], "f3"), "expected q") + stat(str(p["successes"]), "successes")
            + "</div>"
            f'<div class="pc-src">Source: {src} @ <code>{E(rev)}</code>{sub} · replay {p["replay"]}</div>'
            f'<p>{E(p["lineage"])}</p>'
            f'<p class="lic">Licence: {E(p["license_status"])}</p>'
            f'<button class="linkbtn" type="button" data-policy="{E(p["policy"])}">'
            f'Show its {n} task{"" if n == 1 else "s"} in the explorer</button>'
            "</article>"
        )
    return "".join(out)


def disagree_text(D) -> str:
    R = D.get("reproduction") or {}
    dis = R.get("disagreements") or []
    if not dis:
        return ""
    pol = {p["policy"]: p["display"] for p in D["policies"]}
    parts = []
    for d in dis:
        a, b = fmt(d["posterior_ours"], "f3"), fmt(d["posterior_frozen"], "f3")
        diff = abs(d["posterior_ours"] - d["posterior_frozen"])
        if diff < 0.01:
            parts.append(f'task {d["task_id"]} is a near tie ({a} vs {b})')
        else:
            who = "the reference" if d["ours"] == REFERENCE else pol.get(d["ours"], d["ours"])
            parts.append(f'on task {d["task_id"]} the reimplementation prefers {who} by {fmt(diff, "f2")} ({a} vs {b})')
    words = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five"}
    n = len(parts)
    text = f"In the one disagreement, {parts[0]}." if n == 1 else f"Of the {words.get(n, n)} disagreements, {'; '.join(parts)}."
    return E(text)


def teaser_svg(D, color) -> str:
    """Bank of checkpoints -> per-task router -> 10 x 10 grid of the 100 routed tasks."""
    pols = sorted(D["policies"], key=lambda p: (list(FAMVAR).index(p["family"]) if p["family"] in FAMVAR else 9,
                                                -p["tasks"], -p["task_points"]))
    W, H = 460, 300
    cw, gap, gx, gy = 13, 2, 302, 58
    rows = []
    rows.append(f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="Schematic: a bank of {len(pols)} '
                f'checkpoints feeds a per-task router; each of the 100 tasks runs one checkpoint; '
                f'Q = {fmt(D["headline"]["Q"], "f3")}." xmlns="http://www.w3.org/2000/svg">')
    rows.append(f'<text class="tz-head" x="0" y="12">Bank · {len(pols)} checkpoints</text>')
    rows.append(f'<text class="tz-head" x="{gx}" y="{gy - 10}">100 tasks</text>')
    rx, ry, rw, rh = 196, 118, 78, 52
    for i, p in enumerate(pols):
        y = 24 + i * 26
        rows.append(f'<path class="tz-edge" d="M164,{y + 9} C182,{y + 9} 180,{ry + rh / 2} {rx},{ry + rh / 2}"/>')
        rows.append(f'<rect x="0" y="{y}" width="160" height="19" rx="4" style="fill:var(--surface);stroke:var(--border)"/>')
        rows.append(f'<rect x="6" y="{y + 5}" width="9" height="9" rx="2" style="fill:{color[p["policy"]]}"/>')
        rows.append(f'<text class="tz-lab" x="21" y="{y + 13.5}">{E(p["display"])}</text>')
    rows.append(f'<rect class="tz-router" x="{rx}" y="{ry}" width="{rw}" height="{rh}" rx="8"/>')
    rows.append(f'<text class="tz-rt" x="{rx + rw / 2}" y="{ry + 22}" text-anchor="middle">router</text>')
    rows.append(f'<text class="tz-lab" x="{rx + rw / 2}" y="{ry + 38}" text-anchor="middle">one per task</text>')
    rows.append(f'<path class="tz-edge" d="M{rx + rw},{ry + rh / 2} H{gx - 8}" marker-end="url(#tz-ah)"/>')
    rows.append('<defs><marker id="tz-ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" '
                'orient="auto"><path d="M0,0L10,5L0,10z" style="fill:var(--axis)"/></marker></defs>')
    for t in sorted(D["tasks"], key=lambda t: t["id"]):
        r, c = divmod(t["id"], 10)
        x, y = gx + c * (cw + gap), gy + r * (cw + gap)
        title = f'Task {t["id"]}: {humanize(t["name"]).lower()}, q {fmt(t["q"], "f2")}'
        rows.append(f'<rect x="{x}" y="{y}" width="{cw}" height="{cw}" rx="2" style="fill:{color[t["policy"]]}">'
                    f'<title>{E(title)}</title></rect>')
    hd = D["headline"]
    qy = gy + 10 * (cw + gap) + 26
    rows.append(f'<text class="tz-q" x="{gx}" y="{qy}">Q = {fmt(hd["Q"], "f3")}</text>')
    rows.append(f'<text class="tz-lab" x="{gx}" y="{qy + 17}">95% CI {fmt(hd["Q_ci95"][0], "f3")}–'
                f'{fmt(hd["Q_ci95"][1], "f3")}</text>')
    rows.append("</svg>")
    return "".join(rows)


def human_size(n: int) -> str:
    kb = n / 1024
    if kb >= 1024:
        return f"{kb / 1024:.1f} MB"
    return f"{kb:.0f} KB" if kb >= 10 else f"{kb:.1f} KB"


# ---------------------------------------------------------------- page rewrite

BIND_RE = re.compile(r'<(\w+)(\s[^>]*?\bdata-bind="([^"]+)"[^>]*)>(.*?)</\1>', re.S)
FMT_RE = re.compile(r'\bdata-fmt="([^"]+)"')
SIZE_RE = re.compile(r'(<span\b[^>]*\bdata-size="([^"]+)"[^>]*>)(.*?)(</span>)', re.S)
# <meta content="..." data-tpl="... {path|fmt} ..."> : content is rewritten from the template.
TPL_RE = re.compile(r'<meta\b[^>]*\bdata-tpl="([^"]*)"[^>]*>')


def block(page: str, name: str, content: str) -> str:
    pat = re.compile(rf"(<!-- prerender:{name} -->)(.*?)(<!-- /prerender:{name} -->)", re.S)
    if not pat.search(page):
        raise SystemExit(f"marker prerender:{name} not found in index.html")
    return pat.sub(lambda m: m.group(1) + content + m.group(3), page)


def render(page: str, D) -> tuple[str, list[str]]:
    missing = []

    def bind(m):
        tag, attrs, expr = m.group(1), m.group(2), m.group(3)
        f = FMT_RE.search(attrs)
        v = eval_bind(D, html.unescape(expr))
        if v is None:
            missing.append(expr)
            return m.group(0)
        return f"<{tag}{attrs}>{E(fmt(v, f.group(1) if f else 'raw'))}</{tag}>"

    page = BIND_RE.sub(bind, page)

    def fill(tpl: str) -> str:
        def one(m):
            v = eval_bind(D, m.group(1))
            if v is None:
                missing.append(m.group(1))
                return m.group(0)
            return fmt(v, m.group(2))

        return re.sub(r"\{([^{}|]+)\|(\w+)\}", one, html.unescape(tpl))

    def meta(m):
        val = fill(m.group(1)).replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;")
        return re.sub(r'\bcontent="[^"]*"', lambda _: f'content="{val}"', m.group(0), count=1)

    page = TPL_RE.sub(meta, page)
    color, _ = assign_colors(D["policies"])
    page = block(page, "teaser", teaser_svg(D, color))
    page = block(page, "bank", bank_cards(D, color))
    page = block(page, "disagree", disagree_text(D))

    def size(m):
        f = SITE / m.group(2)
        return m.group(1) + (f"({human_size(f.stat().st_size)})" if f.exists() else "") + m.group(4)

    page = SIZE_RE.sub(size, page)
    return page, missing


# ---------------------------------------------------------------- images (matplotlib)


def write_images(D) -> None:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib import font_manager
    except ImportError:
        print("matplotlib not available; skipping og.png and apple-touch-icon.png", file=sys.stderr)
        return

    def font(name):
        p = Path("C:/Windows/Fonts") / name
        return font_manager.FontProperties(fname=str(p)) if p.exists() else font_manager.FontProperties()

    serif_b, sans, sans_b = font("georgiab.ttf"), font("segoeui.ttf"), font("segoeuib.ttf")
    bg, ink, ink2, muted = "#fbfbf9", "#141413", "#4f4e4a", "#6c6a65"
    _, hexes = assign_colors(D["policies"])
    hd = D["headline"]

    fig = plt.figure(figsize=(12, 6.3), dpi=100, facecolor=bg)
    fig.text(0.05, 0.89, "TEAM KANR · 2026 BEHAVIOR CHALLENGE · TECHNICAL REPORT", fontproperties=sans,
             fontsize=13, color=ink2)
    fig.text(0.05, 0.62, "Policy Bank: Development-Selected\nRouting of Public Robot Policies\nfor BEHAVIOR-1K",
             fontproperties=serif_b, fontsize=28, color=ink, linespacing=1.2, va="bottom")
    fig.text(0.05, 0.545, "Keshav Balakrishna, Abhijay Gangerapu, Rithik Satarla", fontproperties=sans,
             fontsize=15, color=ink2)
    fig.text(0.95, 0.80, f"Q = {fmt(hd['Q'], 'f3')}", fontproperties=sans_b, fontsize=36, color=ink, ha="right")
    fig.text(0.95, 0.735, f"95% CI {fmt(hd['Q_ci95'][0], 'f3')}–{fmt(hd['Q_ci95'][1], 'f3')}",
             fontproperties=sans, fontsize=15, color=ink2, ha="right")
    fig.text(0.95, 0.69, f"{fmt(hd['episodes'], 'int')} episodes · 100 tasks · {hd['policies_routed']} checkpoints",
             fontproperties=sans, fontsize=15, color=ink2, ha="right")
    ax = fig.add_axes([0.05, 0.1, 0.9, 0.36], facecolor=bg)
    T = sorted(D["tasks"], key=lambda t: (-t["q"], t["id"]))
    xs = range(len(T))
    ax.bar(xs, [max(t["q"], 0.006) for t in T], width=0.78, color=[hexes[t["policy"]] for t in T])
    ax.scatter(xs, [t["expected"] for t in T], marker="_", s=60, color=ink, linewidths=1.6, zorder=3)
    ax.set_xlim(-0.8, len(T) - 0.2)
    ax.set_ylim(0, 1)
    for spine in ("top", "right", "left"):
        ax.spines[spine].set_visible(False)
    ax.spines["bottom"].set_color("#c3c2b7")
    ax.set_xticks([])
    ax.set_yticks([0, 0.5, 1])
    ax.set_yticklabels(["0", "0.5", "1"], fontproperties=sans, fontsize=11, color=muted)
    ax.tick_params(axis="y", length=0)
    ax.grid(axis="y", color="#e6e5df", linewidth=1)
    ax.set_axisbelow(True)
    fig.text(0.05, 0.035, "Realized mean q per task, coloured by routed checkpoint; ticks mark the expected q at freeze.",
             fontproperties=sans, fontsize=12, color=muted)
    fig.text(0.95, 0.035, "policy-bank.vercel.app", fontproperties=sans_b, fontsize=12, color=ink2, ha="right")
    fig.savefig(SITE / "og.png", dpi=100, facecolor=bg)
    plt.close(fig)

    fig = plt.figure(figsize=(1.8, 1.8), dpi=100, facecolor=bg)
    ax = fig.add_axes([0, 0, 1, 1], facecolor=bg)
    ax.set_xlim(0, 32)
    ax.set_ylim(0, 32)
    ax.axis("off")
    from matplotlib.patches import FancyBboxPatch

    for x, hgt, col in ((5, 9, ink), (11, 19, "#2a78d6"), (17, 13, ink), (23, 6.5, ink)):
        ax.add_patch(FancyBboxPatch((x, 5), 4, hgt, boxstyle="round,pad=0,rounding_size=0.9", color=col))
    fig.savefig(SITE / "apple-touch-icon.png", dpi=100, facecolor=bg)
    plt.close(fig)
    print("wrote og.png and apple-touch-icon.png")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--check", action="store_true", help="exit 1 if index.html would change")
    ap.add_argument("--images", action="store_true", help="also write og.png and apple-touch-icon.png")
    a = ap.parse_args()
    D = json.loads((SITE / "data" / "results.json").read_text(encoding="utf-8"))
    path = SITE / "index.html"
    old = path.read_text(encoding="utf-8")
    new, missing = render(old, D)
    if missing:
        print("unresolved data-bind paths: " + ", ".join(sorted(set(missing))), file=sys.stderr)
        return 2
    if a.check:
        if new != old:
            print("index.html is stale; run tools/prerender_site.py", file=sys.stderr)
            return 1
        print("index.html is up to date")
    elif new != old:
        path.write_text(new, encoding="utf-8", newline="\n")
        print("updated site/index.html")
    else:
        print("site/index.html already up to date")
    if a.images:
        write_images(D)
    return 0


if __name__ == "__main__":
    sys.exit(main())
