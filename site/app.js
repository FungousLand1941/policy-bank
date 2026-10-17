/* Policy Bank project page. Vanilla ES2020, no dependencies.
   Numbers come from data/results.json. tools/prerender_site.py writes the same values
   into index.html, so this script only re-binds them and draws the interactive parts.
   Keep fmt(), resolve() and the colour mapping in sync with that script. */
'use strict';
(() => {
  const NS = 'http://www.w3.org/2000/svg';
  const $ = (q, r = document) => r.querySelector(q);
  const $$ = (q, r = document) => Array.from(r.querySelectorAll(q));

  /* ---------- DOM helpers (text always via textContent) ---------- */
  function h(tag, attrs, ...kids) {
    const e = document.createElement(tag);
    if (attrs) for (const k in attrs) {
      const v = attrs[k];
      if (v == null || v === false) continue;
      if (k === 'class') e.className = v;
      else if (k === 'text') e.textContent = v;
      else if (k === 'style') e.style.cssText = v;
      else if (k.startsWith('on')) e.addEventListener(k.slice(2), v);
      else e.setAttribute(k, v === true ? '' : v);
    }
    for (const c of kids.flat()) if (c != null && c !== false) e.append(c.nodeType ? c : document.createTextNode(String(c)));
    return e;
  }
  function s(tag, attrs, parent) {
    const e = document.createElementNS(NS, tag);
    if (attrs) for (const k in attrs) {
      const v = attrs[k];
      if (v == null) continue;
      if (k === 'text') e.textContent = v; else if (k === 'style') e.style.cssText = v; else e.setAttribute(k, v);
    }
    if (parent) parent.appendChild(e);
    return e;
  }

  /* ---------- shared formatting (mirrors tools/prerender_site.py) ---------- */
  const MINUS = '−';
  const fixed = (v, d) => { const t = (+v).toFixed(d); return t[0] === '-' ? MINUS + t.slice(1) : t; };
  function fmt(v, f) {
    switch (f) {
      case 'int': return Math.round(v).toLocaleString('en-US');
      case 'f1': case 'f2': case 'f3': case 'f4': return fixed(v, +f[1]);
      case 'pct0': return Math.round(v * 100) + '%';
      case 'pct1': return fixed(v * 100, 1) + '%';
      case 'sp1': return (v >= 0 ? '+' : MINUS) + Math.abs(v).toFixed(1);
      case 'x100f1': return fixed(v * 100, 1);
      case 'ord': { const n = Math.round(v * 100), t = n % 100; return n + (t >= 11 && t <= 13 ? 'th' : ({ 1: 'st', 2: 'nd', 3: 'rd' }[n % 10] || 'th')); }
      case 'utc': { const m = /^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2})/.exec(v); return m ? `${m[1]} at ${m[2]} UTC` : String(v); }
      default: return String(v);
    }
  }
  /* Paths are dot-separated, but keys may contain dots ("0.05"): match the longest key. */
  function resolve(o, path) {
    const seg = path.split('.');
    let i = 0;
    while (i < seg.length) {
      if (o == null || typeof o !== 'object') return undefined;
      let hit = false;
      for (let j = seg.length; j > i; j--) {
        const k = seg.slice(i, j).join('.');
        if (Object.prototype.hasOwnProperty.call(o, k)) { o = o[k]; i = j; hit = true; break; }
      }
      if (!hit) return undefined;
    }
    return o;
  }
  function evalBind(o, expr) {
    const vals = expr.split(' - ').map(p => resolve(o, p.trim()));
    if (vals.some(v => v == null)) return undefined;
    return vals.length === 1 ? vals[0] : vals.slice(1).reduce((a, b) => a - b, vals[0]);
  }
  const f2 = x => fixed(x, 2), f3 = x => (x == null || isNaN(x) ? '–' : fixed(x, 3));
  const fint = x => fmt(x, 'int');
  const sgn = (x, d = 3) => (x >= 0 ? '+' : MINUS) + Math.abs(x).toFixed(d);
  const qt = t => (t === 0 ? '0' : t === 1 ? '1' : String(+t.toFixed(3)));
  const humanize = n => { const t = n.replace(/_/g, ' ').replace(/^re /, 're-'); return t.charAt(0).toUpperCase() + t.slice(1); };
  const sceneName = n => (/^[A-Z]/.test(n) ? n : humanize(n));
  const lin = (d0, d1, r0, r1) => v => r0 + ((v - d0) / (d1 - d0)) * (r1 - r0);
  const logS = (d0, d1, r0, r1) => { const a = Math.log10(d0), b = Math.log10(d1); return v => r0 + ((Math.log10(v) - a) / (b - a)) * (r1 - r0); };
  function niceTicks(lo, hi, n = 4) {
    const raw = (hi - lo) / n, p = Math.pow(10, Math.floor(Math.log10(raw))), m = raw / p;
    const st = (m <= 1 ? 1 : m <= 2 ? 2 : m <= 2.5 ? 2.5 : m <= 5 ? 5 : 10) * p;
    const out = [];
    for (let v = Math.ceil(lo / st - 1e-9) * st; v <= hi + 1e-9; v += st) out.push(+v.toFixed(6));
    return out;
  }
  function wrap(str, max) {
    const out = []; let line = '';
    for (const w of str.split(' ')) {
      if (line && (line + ' ' + w).length > max) { out.push(line); line = w; } else line = line ? line + ' ' + w : w;
    }
    if (line) out.push(line);
    return out;
  }
  const clip = (str, px, cw = 6.1) => { const n = Math.floor(px / cw); return str.length > n ? str.slice(0, Math.max(1, n - 1)) + '…' : str; };

  let D = null;
  const TASK = {}, POL = {}, COLOR = {};
  const pcol = id => COLOR[id] || 'var(--muted)';
  const pname = id => (POL[id] ? POL[id].display : id);
  const depth = t => Math.min(t.own_dev_n || 0, 2);
  const dcol = t => `var(--d${depth(t)})`;
  const FAMILY = { comet: 'comet', winner: 'winner', winner100: 'winner-format specialist' };
  const FAMVAR = { comet: 'comet', winner: 'winner', winner100: 'w100' };
  /* Rank within family (tasks, then task points) -> lightness step of the family ramp. */
  const STEPS = { 2: [1, 0], 4: [2, 0, 3, 1] };
  function assignColors() {
    const fams = {};
    D.policies.forEach(p => (fams[p.family] = fams[p.family] || []).push(p));
    Object.keys(fams).forEach(f => {
      const arr = fams[f].sort((a, b) => b.tasks - a.tasks || b.task_points - a.task_points || (a.policy < b.policy ? -1 : 1));
      const order = arr.length <= 2 ? STEPS[2] : STEPS[4];
      arr.forEach((p, i) => { COLOR[p.policy] = `var(--${FAMVAR[f] || 'comet'}-${order[Math.min(i, order.length - 1)]})`; });
    });
  }

  /* ---------- tooltip + live region ---------- */
  const tip = $('#tip'), live = $('#chartLive');
  function tipShow(nodes, cx, cy) {
    tip.replaceChildren(...nodes);
    tip.hidden = false;
    const r = tip.getBoundingClientRect();
    let x = cx + 14, y = cy + 14;
    if (x + r.width > innerWidth - 8) x = cx - r.width - 14;
    if (x < 8) x = 8;
    if (y + r.height > innerHeight - 8) y = cy - r.height - 14;
    if (y < 8) y = 8;
    tip.style.left = x + 'px';
    tip.style.top = y + 'px';
  }
  const tipHide = () => { tip.hidden = true; };
  function tipContent(head, rows) {
    return [h('div', { class: 'th', text: head }),
      ...rows.map(r => h('div', { class: 'tr' },
        r.c ? h('i', { class: r.box ? 'kb' : 'k', style: 'background:' + r.c }) : null,
        h('b', { text: r.v }), r.l ? ' ' : null, r.l ? h('span', { text: r.l }) : null))];
  }
  const nodesText = nodes => nodes.map(n => n.textContent.replace(/\s+/g, ' ').trim()).filter(Boolean).join('; ');
  document.addEventListener('pointerdown', e => { if (!e.target.closest('svg[tabindex]')) tipHide(); }, true);
  addEventListener('scroll', tipHide, { passive: true });

  /* Shared hover / tap / keyboard layer. mode: 'x' | 'y' nearest along an axis, 'xy' nearest point. */
  function interact(svg, items, mode, onHover, onActivate) {
    let idx = -1, lastType = 'mouse', lastTap = -1;
    svg.setAttribute('tabindex', '0');
    const local = e => { const r = svg.getBoundingClientRect(); return { x: e.clientX - r.left, y: e.clientY - r.top }; };
    function nearest(p) {
      let best = -1, bd = Infinity;
      items.forEach((it, i) => {
        const d = mode === 'x' ? Math.abs(it.x - p.x) : mode === 'y' ? Math.abs(it.y - p.y) : Math.hypot(it.x - p.x, it.y - p.y);
        if (d < bd) { bd = d; best = i; }
      });
      return mode === 'xy' && bd > 26 ? -1 : best;
    }
    function set(i, cx, cy, announce) {
      idx = i;
      if (onHover) onHover(i);
      if (i < 0) { tipHide(); return; }
      const it = items[i], nodes = it.tip();
      if (cx == null) { const r = svg.getBoundingClientRect(); cx = r.left + it.x; cy = r.top + it.y; }
      tipShow(nodes, cx, cy);
      if (announce) live.textContent = `${i + 1} of ${items.length}. ${nodesText(nodes)}`;
    }
    svg.addEventListener('pointermove', e => { lastType = e.pointerType; if (e.pointerType !== 'touch') set(nearest(local(e)), e.clientX, e.clientY); });
    svg.addEventListener('pointerleave', e => { if (e.pointerType !== 'touch') set(-1); });
    svg.addEventListener('pointerdown', e => { lastType = e.pointerType; if (e.pointerType !== 'mouse') set(nearest(local(e)), e.clientX, e.clientY); });
    svg.addEventListener('click', e => {
      if (!onActivate) return;
      const i = nearest(local(e));
      if (i < 0) return;
      if (lastType === 'mouse') onActivate(items[i]);
      else { if (lastTap === i) onActivate(items[i]); lastTap = i; }
    });
    svg.addEventListener('keydown', e => {
      const n = items.length; if (!n) return;
      const k = e.key;
      if (k === 'ArrowRight' || k === 'ArrowDown') { e.preventDefault(); set(Math.min(n - 1, idx + 1), null, null, true); }
      else if (k === 'ArrowLeft' || k === 'ArrowUp') { e.preventDefault(); set(Math.max(0, idx - 1), null, null, true); }
      else if (k === 'Home') { e.preventDefault(); set(0, null, null, true); }
      else if (k === 'End') { e.preventDefault(); set(n - 1, null, null, true); }
      else if (k === 'Escape') set(-1);
      else if (k === 'Enter' && idx >= 0 && onActivate) onActivate(items[idx]);
    });
    svg.addEventListener('focus', () => { if (idx < 0 && svg.matches(':focus-visible')) set(0, null, null, true); });
    svg.addEventListener('blur', () => set(-1));
  }

  /* ---------- chart scaffolding ---------- */
  const charts = new Map(), widths = new Map();
  let roTimer = 0;
  const ro = 'ResizeObserver' in window ? new ResizeObserver(() => {
    clearTimeout(roTimer);
    roTimer = setTimeout(() => charts.forEach((fn, id) => {
      const box = document.getElementById(id), w = box.clientWidth;
      if (w && w !== widths.get(id)) { widths.set(id, w); fn(); }
    }), 120);
  }) : null;
  function reg(id, fn) {
    charts.set(id, fn);
    const box = document.getElementById(id);
    widths.set(id, box.clientWidth);
    if (ro) ro.observe(box);
    fn();
  }
  const redraw = id => { const fn = charts.get(id); if (fn) fn(); };
  function frame(box, title, desc) {
    const W = Math.max(box.clientWidth, 200), H = box.clientHeight || 240;
    const svg = s('svg', { width: W, height: H, viewBox: `0 0 ${W} ${H}`, role: 'group', 'aria-roledescription': 'interactive chart',
      'aria-label': `${title}. ${desc} Use the arrow keys to step through values.` });
    box.replaceChildren(svg);
    return { svg, W, H };
  }
  function yAxis(g, y, ticks, f, x0, x1, base = true) {
    ticks.forEach((t, i) => {
      const yy = Math.round(y(t)) + 0.5;
      s('line', { class: i === 0 && base ? 'bl' : 'gl', x1: x0, x2: x1, y1: yy, y2: yy }, g);
      s('text', { class: 'tk', x: x0 - 6, y: yy + 3.5, 'text-anchor': 'end', text: f(t) }, g);
    });
  }
  function vbar(x, yTop, yBase, w, r = 4) {
    const hh = yBase - yTop; if (hh <= 0) return '';
    r = Math.min(r, w / 2, hh);
    return `M${x},${yBase}V${yTop + r}Q${x},${yTop} ${x + r},${yTop}H${x + w - r}Q${x + w},${yTop} ${x + w},${yTop + r}V${yBase}Z`;
  }
  function hbar(x0, y, x1, hh, r = 4) {
    const w = x1 - x0; if (w <= 0) return '';
    r = Math.min(r, hh / 2, w);
    return `M${x0},${y}H${x1 - r}Q${x1},${y} ${x1},${y + r}V${y + hh - r}Q${x1},${y + hh} ${x1 - r},${y + hh}H${x0}Z`;
  }
  const yLabel = (g, text, x, y) => s('text', { class: 'al', transform: `translate(${x},${y}) rotate(-90)`, 'text-anchor': 'middle', text }, g);
  function miniTable(cols, rows, cap) {
    return h('table', { class: 'mini' }, cap ? h('caption', { class: 'sr', text: cap }) : null,
      h('thead', null, h('tr', null, cols.map((c, i) => h('th', { scope: 'col', class: i ? 'n' : null, text: c })))),
      h('tbody', null, rows.map(r => h('tr', null, r.map((v, i) => h('td', { class: i ? 'n' : null, text: v }))))));
  }
  function hoverBand(g, horizontal) { return s('rect', { class: 'hb', visibility: 'hidden', x: 0, y: 0, width: 0, height: 0 }, g); }
  function showBand(r, x, y, w, hh) { r.setAttribute('x', x); r.setAttribute('y', y); r.setAttribute('width', w); r.setAttribute('height', hh); r.setAttribute('visibility', 'visible'); }

  /* ---------- flow diagrams ---------- */
  function flow(id, nodes, edges, minW) {
    const box = document.getElementById(id);
    const W = Math.max(box.clientWidth, 240), n = nodes.length;
    let cols = W < 520 ? 1 : Math.max(1, Math.min(n, Math.floor((W + 34) / (minW + 34))));
    cols = Math.ceil(n / Math.ceil(n / cols));
    const gx = cols > 1 ? 34 : 0, gy = 34, bw = (W - (cols - 1) * gx) / cols;
    const tc = Math.max(12, Math.floor((bw - 26) / 7.6)), lc = Math.max(14, Math.floor((bw - 26) / 6.4));
    const L = nodes.map(nd => ({ t: wrap(nd.t, tc), l: nd.l.flatMap(x => wrap(x, lc)) }));
    const rows = Math.ceil(n / cols), rowH = [], rowY = [];
    let yy = 1;
    for (let r = 0; r < rows; r++) {
      let mh = 0;
      for (let c = 0; c < cols; c++) { const k = r * cols + c; if (k < n) mh = Math.max(mh, 30 + L[k].t.length * 18 + L[k].l.length * 16 + 10); }
      rowH.push(mh); rowY.push(yy); yy += mh + gy;
    }
    const H = Math.ceil(yy - gy + 2);
    box.style.minHeight = H + 'px';
    const svg = s('svg', { width: W, height: H, viewBox: `0 0 ${W} ${H}`, 'aria-hidden': 'true', focusable: 'false' });
    const mk = s('marker', { id: id + '-ah', viewBox: '0 0 10 10', refX: 9, refY: 5, markerWidth: 7, markerHeight: 7, orient: 'auto-start-reverse' }, s('defs', null, svg));
    s('path', { d: 'M0,0L10,5L0,10z', class: 'ah' }, mk);
    const pos = nodes.map((_, k) => { const r = Math.floor(k / cols), c = k % cols; return { x: 0.5 + c * (bw + gx), y: rowY[r], h: rowH[r] }; });
    edges.forEach((kind, k) => {
      const a = pos[k], b = pos[k + 1];
      if (!b) return;
      let d;
      if (a.y === b.y) { const cy = a.y + Math.min(a.h, 64) / 2 + 8; d = `M${a.x + bw + 2},${cy}H${b.x - 3}`; }
      else if (cols === 1) d = `M${a.x + bw / 2},${a.y + a.h + 2}V${b.y - 3}`;
      else { const my = a.y + a.h + gy / 2; d = `M${a.x + bw / 2},${a.y + a.h + 2}V${my}H${b.x + bw / 2}V${b.y - 3}`; }
      const ed = s('path', { d, class: 'edge', 'marker-end': `url(#${id}-ah)` }, svg);
      if (kind === 'bi') ed.setAttribute('marker-start', `url(#${id}-ah)`);
    });
    nodes.forEach((nd, k) => {
      const p = pos[k], g = s('g', { class: 'nd ' + (nd.k || '') }, svg);
      s('rect', { x: p.x, y: p.y, width: bw - 1, height: p.h, rx: 8 }, g);
      s('text', { class: 'nn', x: p.x + 13, y: p.y + 19, text: nd.n }, g);
      let ty = p.y + 38;
      L[k].t.forEach(t => { s('text', { class: 'nt', x: p.x + 13, y: ty, text: t }, g); ty += 18; });
      ty += 2;
      L[k].l.forEach(t => { s('text', { class: 'nl', x: p.x + 13, y: ty, text: t }, g); ty += 16; });
    });
    box.replaceChildren(svg);
  }
  function pipelineNodes() {
    const hd = D ? D.headline : null;
    return [
      { n: 'STEP 1', t: 'Public checkpoints', l: [hd ? `${hd.policies_routed} routed; ${hd.policies_tested} labels tested` : 'ten routed checkpoints', 'Comet π0.5, 2025 winner, specialists, ours'] },
      { n: 'STEP 2', t: 'Development rollouts', l: ['instances 311–320', hd ? `${fint(hd.dev_rollouts)} in the ledger, ${fint(hd.dev_eligible)} eligible` : 'development ledger'] },
      { n: 'STEP 3', t: 'Empirical-Bayes posterior', l: ['per (task, policy)', 'reference prior + own rollouts'] },
      { n: 'STEP 4', t: 'Switching rules', l: ['≥ 2 own rollouts, guard (0–49)', 'gain ≥ 0.01 · veto', 'scope, one per family (50–99)'], k: 'core' },
      { n: 'STEP 5', t: 'Frozen route', l: ['one policy per task', 'hashed with SHA-256'] },
      { n: 'STEP 6', t: 'One evaluation', l: ['public instances 301–310', hd ? `${fint(hd.episodes)} episodes, Q = ${f3(hd.Q)}` : 'run once'], k: 'eval' },
      { n: 'STEP 7', t: 'Hidden test', l: ['instances 321–340', 'run by the organizers'], k: 'ext' },
    ];
  }
  const servingNodes = [
    { n: 'ORGANIZERS', t: 'Evaluator', l: ['hidden-test harness', 'instances 321–340'], k: 'ext' },
    { n: 'TRANSPORT', t: 'WebSocket', l: ['msgpack frames'] },
    { n: 'OURS', t: 'Fail-stop server', l: ['contract validation', 'one task per container', 'one session', 'batch ≤ 10', 'global chunk K = 4 (divides native replay 32 / 20)', '≤ 550 s per query'], k: 'core' },
    { n: 'MODEL', t: 'Policy', l: ['the routed checkpoint for this task'] },
  ];

  /* ---------- selector widget ---------- */
  const pdf = (v, mu, sd) => Math.exp(-0.5 * ((v - mu) / sd) ** 2) / (sd * Math.sqrt(2 * Math.PI));
  let SEL = null, selTimer = 0;
  function selRead() {
    const v = k => +$('#s_' + k).value;
    const mu = v('mu'), sd = v('sd'), n = v('n'), xb = v('x'), sig = v('sig'), inc = v('inc');
    const prec = 1 / (sd * sd) + n / (sig * sig);
    const pm = (mu / (sd * sd) + (n * xb) / (sig * sig)) / prec;
    const gain = Math.round((pm - inc) * 1e9) / 1e9;   // strip float noise; compare unrounded
    SEL = { mu, sd, n, xb, sig, inc, pm, psd: Math.sqrt(1 / prec), w: n / (sig * sig) / prec, gain };
  }
  /* Print the gain with enough decimals that the printed value agrees with the verdict. */
  function gainText(g) {
    let d = 4;
    while (d < 9 && (+g.toFixed(d) >= 0.01) !== (g >= 0.01)) d++;
    return sgn(g, d);
  }
  function selUpdate() {
    selRead();
    const P = SEL;
    $('#o_mu').textContent = P.mu.toFixed(2); $('#o_sd').textContent = P.sd.toFixed(2);
    $('#o_n').textContent = P.n; $('#o_x').textContent = P.xb.toFixed(2);
    $('#o_sig').textContent = P.sig.toFixed(2); $('#o_inc').textContent = P.inc.toFixed(2);
    $('#s_x').disabled = P.n === 0;
    const stat = (v, l) => h('div', null, h('b', { text: v }), h('span', { text: l }));
    const gt = gainText(P.gain);
    $('#selStats').replaceChildren(stat(f3(P.pm), 'posterior mean'), stat(f3(P.psd), 'posterior s.d.'), stat(gt, 'gain vs incumbent'));
    let lead, rest;
    if (P.n < 2) { lead = 'Keep the incumbent.'; rest = ` The challenger has ${P.n} own rollout${P.n === 1 ? '' : 's'}; the tasks 0–49 rule needs at least 2.`; }
    else if (P.gain < 0.01) { lead = 'Keep the incumbent.'; rest = ` Posterior gain ${gt} is below the 0.01 threshold.`; }
    else { lead = 'Switch allowed by the tasks 0–49 rule,'; rest = ` gain ${gt} ≥ 0.01 with ${P.n} own rollouts, provided the challenger also passes the development guard and the veto.`; }
    $('#selVerdict').replaceChildren(h('b', { text: lead }), rest + ` Own rollouts carry ${Math.round(P.w * 100)}% of the posterior weight.`);
    clearTimeout(selTimer);
    selTimer = setTimeout(() => { $('#selLive').textContent = `Posterior mean ${f3(P.pm)}, gain ${gt}. ${lead.replace(/,$/, '.')}`; }, 600);
    redraw('selChart');
  }
  function selChart() {
    const box = $('#selChart'), P = SEL;
    const { svg, W, H } = frame(box, 'Prior and posterior for the challenger',
      `Prior mean ${f3(P.mu)}, s.d. ${f3(P.sd)}. Posterior mean ${f3(P.pm)}, s.d. ${f3(P.psd)}. Incumbent ${f3(P.inc)}.`);
    const m = { l: 8, r: 10, t: 16, b: 22 };
    const x = lin(-0.1, 1, m.l, W - m.r);
    const ymax = Math.max(pdf(P.mu, P.mu, P.sd), pdf(P.pm, P.pm, P.psd));
    const y = lin(0, ymax * 1.06, H - m.b, m.t);
    const g = s('g', null, svg);
    [0, 0.2, 0.4, 0.6, 0.8, 1].forEach(t => {
      s('line', { class: 'gl', x1: x(t), x2: x(t), y1: m.t, y2: H - m.b }, g);
      s('text', { class: 'tk', x: x(t), y: H - 6, 'text-anchor': 'middle', text: qt(t) }, g);
    });
    s('line', { class: 'bl', x1: m.l, x2: W - m.r, y1: H - m.b + 0.5, y2: H - m.b + 0.5 }, g);
    const xs = []; for (let i = 0; i <= 220; i++) xs.push(-0.1 + (1.1 * i) / 220);
    const curve = (mu, sd) => xs.map(v => [x(v), y(pdf(v, mu, sd))]);
    const pathOf = pts => 'M' + pts.map(p => p[0].toFixed(1) + ',' + p[1].toFixed(1)).join('L');
    const area = pts => pathOf(pts) + `L${x(1)},${y(0)}L${x(-0.1)},${y(0)}Z`;
    const pr = curve(P.mu, P.sd), po = curve(P.pm, P.psd);
    s('path', { d: area(pr), class: 'wash2' }, g); s('path', { d: pathOf(pr), class: 'ln2' }, g);
    s('path', { d: area(po), class: 'wash' }, g); s('path', { d: pathOf(po), class: 'ln' }, g);
    const xi = x(P.inc), right = xi > W - 90;
    s('line', { class: 'inc', x1: xi, x2: xi, y1: m.t - 4, y2: H - m.b }, g);
    s('text', { class: 'dl2', x: xi + (right ? -5 : 5), y: m.t + 2, 'text-anchor': right ? 'end' : 'start', text: 'incumbent' }, g);
    if (P.n > 0) { const xm = x(P.xb), yb = H - m.b; s('path', { class: 'ink-fill', d: `M${xm},${yb - 8}L${xm + 5},${yb}L${xm - 5},${yb}Z` }, g); }
    const cross = s('line', { class: 'gl', x1: 0, x2: 0, y1: m.t, y2: H - m.b, visibility: 'hidden', style: 'stroke:var(--ink-2)' }, g);
    const items = [];
    for (let i = 0; i <= 50; i++) {
      const v = i / 50;
      items.push({ x: x(v), y: m.t + 10, tip: () => tipContent(`q = ${f2(v)}`, [
        { v: pdf(v, P.pm, P.psd).toFixed(2), l: 'posterior density', c: 'var(--ink)' },
        { v: pdf(v, P.mu, P.sd).toFixed(2), l: 'prior density', c: 'var(--muted)' }]) });
    }
    interact(svg, items, 'x', i => {
      if (i < 0) cross.setAttribute('visibility', 'hidden');
      else { cross.setAttribute('x1', items[i].x); cross.setAttribute('x2', items[i].x); cross.setAttribute('visibility', 'visible'); }
    });
  }

  /* ---------- bank ---------- */
  function pointsChart() {
    const box = $('#pointsChart');
    const ps = D.policies.slice().sort((a, b) => b.task_points - a.task_points);
    const narrow = box.clientWidth < 560, rowH = narrow ? 44 : 30;
    box.style.height = ps.length * rowH + 8 + 'px';
    const { svg, W } = frame(box, 'Task points contributed per checkpoint',
      `Horizontal bars, one per routed checkpoint, sorted by task points: ${ps.map(p => `${p.display} ${p.task_points.toFixed(2)}`).join(', ')}.`);
    const lw = narrow ? 0 : Math.min(230, W * 0.34), x0 = lw + (narrow ? 0 : 10), x1 = W - 46;
    const x = lin(0, Math.max(...ps.map(p => p.task_points)), x0, x1);
    const g = s('g', null, svg), hb = hoverBand(g), items = [];
    ps.forEach((p, i) => {
      const top = 4 + i * rowH, bh = narrow ? 12 : 14;
      const by = narrow ? top + 22 : top + (rowH - bh) / 2, xe = Math.max(x(p.task_points), x0 + 2);
      s('text', { class: 'dl2', x: narrow ? 0 : lw, y: narrow ? top + 14 : by + bh / 2 + 4, 'text-anchor': narrow ? 'start' : 'end', text: p.display }, g);
      s('path', { class: 'bar', d: hbar(x0, by, xe, bh), style: 'fill:' + pcol(p.policy) }, g);
      s('text', { class: 'dl', x: xe + 6, y: by + bh / 2 + 4, text: p.task_points.toFixed(2) }, g);
      items.push({ x: xe, y: top + rowH / 2, p, tip: () => tipContent(p.display, [
        { v: p.task_points.toFixed(2), l: 'task points', c: pcol(p.policy), box: true },
        { v: String(p.tasks), l: 'tasks routed' }, { v: f3(p.q_mean), l: 'realized mean q' }, { v: f3(p.expected_mean), l: 'expected mean q' }]) });
    });
    s('line', { class: 'bl', x1: x0 + 0.5, x2: x0 + 0.5, y1: 2, y2: ps.length * rowH + 6 }, g);
    interact(svg, items, 'y', i => { if (i < 0) hb.setAttribute('visibility', 'hidden'); else showBand(hb, 0, 4 + i * rowH, W, rowH); }, it => focusPolicy(it.p.policy));
  }
  function bankCard(p) {
    const hex = /^[0-9a-f]{40}$/i.test(p.revision);
    const src = p.source.includes('/') ? h('a', { href: 'https://huggingface.co/' + p.source, text: p.source }) : h('span', { text: p.source });
    const stat = (v, l) => h('div', null, h('b', { text: v }), h('span', { text: l }));
    return h('article', { class: 'pc' },
      h('div', { class: 'pc-head' }, h('span', { class: 'sw', style: 'background:' + pcol(p.policy) }),
        h('div', null, h('h3', { text: p.display }), h('div', { class: 'pid', text: p.policy }))),
      h('div', { class: 'badges' }, h('span', { class: 'badge', text: FAMILY[p.family] || p.family }), p.kind === 'ours' ? h('span', { class: 'badge ours', text: 'ours' }) : null),
      h('div', { class: 'pc-stats' }, stat(String(p.tasks), 'tasks routed'), stat(f3(p.q_mean), 'realized q'), stat(f3(p.expected_mean), 'expected q'), stat(String(p.successes), 'successes')),
      h('div', { class: 'pc-src' }, 'Source: ', src, ' @ ', h('code', { text: hex ? p.revision.slice(0, 7) : p.revision }),
        p.subfolder ? [' / ', h('code', { text: p.subfolder })] : null, ` · replay ${p.replay}`),
      h('p', { text: p.lineage }),
      h('p', { class: 'lic', text: 'Licence: ' + p.license_status }),
      h('button', { class: 'linkbtn', type: 'button', 'data-policy': p.policy, text: `Show its ${p.tasks} task${p.tasks === 1 ? '' : 's'} in the explorer` }));
  }
  function bankCards() {
    const ps = D.policies.slice().sort((a, b) => b.task_points - a.task_points);
    $('#bankCards').replaceChildren(...ps.map(bankCard));
  }

  /* ---------- explorer ---------- */
  const st = { pol: new Set(), stage: 'all', scene: 'all', q: '', sort: 'q', ci: false };
  const SORTS = { q: ['realized q', t => -t.q], e: ['expected q', t => -t.expected], gap: ['gap (realized − expected)', t => t.q - t.expected], id: ['task id', t => t.id] };
  const OPEN = new Set();
  let CUR = [], stripAll = false, tableLimit = 20, searchTimer = 0;
  const mobile = () => matchMedia('(max-width: 760px)').matches;
  function filtered() {
    const q = st.q.trim().toLowerCase(), key = SORTS[st.sort][1];
    return D.tasks.filter(t => (!st.pol.size || st.pol.has(t.policy))
      && (st.stage === 'all' || String(t.stage) === st.stage)
      && (st.scene === 'all' || t.scene === st.scene)
      && (!q || t._name.toLowerCase().includes(q) || String(t.id) === q))
      .sort((a, b) => key(a) - key(b) || a.id - b.id);
  }
  function buildFilters() {
    const ps = D.policies.slice().sort((a, b) => a.family.localeCompare(b.family) || b.tasks - a.tasks || b.task_points - a.task_points);
    $('#fPolicies').replaceChildren(...ps.map(p => h('button', {
      class: 'chip', type: 'button', 'aria-pressed': 'false', 'data-p': p.policy,
      onclick: () => { st.pol.has(p.policy) ? st.pol.delete(p.policy) : st.pol.add(p.policy); changed(); },
      onpointerenter: () => emph(p.policy), onpointerleave: () => emph(null), onfocus: () => emph(p.policy), onblur: () => emph(null),
    }, h('span', { class: 'sw', style: 'background:' + pcol(p.policy) }), h('span', { text: p.display }), h('span', { class: 'ct', text: p.tasks }))));
    const sc = $('#fScene');
    Object.keys(D.scenes).sort((a, b) => sceneName(a).localeCompare(sceneName(b))).forEach(k => sc.append(h('option', { value: k, text: `${sceneName(k)} (${D.scenes[k].tasks})` })));
    sc.addEventListener('change', () => { st.scene = sc.value; changed(); });
    $('#fSort').addEventListener('change', e => { st.sort = e.target.value; changed(); });
    $('#fSearch').addEventListener('input', e => { clearTimeout(searchTimer); searchTimer = setTimeout(() => { st.q = e.target.value; changed(); }, 150); });
    $$('.seg button').forEach(b => b.addEventListener('click', () => { st.stage = b.dataset.stage; changed(); }));
    $('#fReset').addEventListener('click', () => { resetFilters(); changed(); });
    $('#stripCI').addEventListener('change', e => { st.ci = e.target.checked; redraw('stripChart'); });
    $('#stripMore').addEventListener('click', () => { stripAll = !stripAll; redraw('stripChart'); });
    $('#tableMore').addEventListener('click', () => { tableLimit += 20; renderTable(); });
    $('#bankCards').addEventListener('click', e => { const b = e.target.closest('[data-policy]'); if (b) focusPolicy(b.dataset.policy); });
  }
  function resetFilters() {
    clearTimeout(searchTimer);
    Object.assign(st, { stage: 'all', scene: 'all', q: '', sort: 'q' }); st.pol.clear();
  }
  function syncControls() {
    $('#fPolicies').classList.toggle('sel', st.pol.size > 0);
    $$('#fPolicies .chip').forEach(c => c.setAttribute('aria-pressed', String(st.pol.has(c.dataset.p))));
    $$('.seg button').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.stage === st.stage)));
    $('#fScene').value = st.scene; $('#fSort').value = st.sort;
    if ($('#fSearch').value !== st.q) $('#fSearch').value = st.q;
  }
  function changed() {
    syncControls();
    stripAll = false; tableLimit = 20;
    renderExplorer();
    writeURL();
  }
  function writeURL() {
    const p = new URLSearchParams();
    if (st.pol.size) p.set('policy', [...st.pol].join(','));
    if (st.stage !== 'all') p.set('stage', st.stage);
    if (st.scene !== 'all') p.set('scene', st.scene);
    if (st.q.trim()) p.set('q', st.q.trim());
    if (st.sort !== 'q') p.set('sort', st.sort);
    const qs = p.toString();
    try { history.replaceState(null, '', location.pathname + (qs ? '?' + qs : '') + location.hash); } catch (e) { /* file:// or sandbox */ }
  }
  function readURL() {
    const p = new URLSearchParams(location.search);
    (p.get('policy') || '').split(',').filter(x => POL[x]).forEach(x => st.pol.add(x));
    if (['1', '2'].includes(p.get('stage'))) st.stage = p.get('stage');
    if (D.scenes[p.get('scene')]) st.scene = p.get('scene');
    if (p.get('q')) st.q = p.get('q');
    if (SORTS[p.get('sort')]) st.sort = p.get('sort');
  }
  function emph(pid) { $$('#stripChart .bar').forEach(b => b.classList.toggle('dim', !!pid && b.dataset.p !== pid)); }
  function focusPolicy(pid) {
    resetFilters(); st.pol.add(pid); changed();
    $('#results').scrollIntoView({ block: 'start' });
  }
  function renderExplorer() {
    CUR = filtered();
    const n = CUR.length, sum = k => CUR.reduce((a, t) => a + t[k], 0), succ = sum('successes');
    $('#exSummary').textContent = n
      ? `Showing ${n} of ${D.tasks.length} tasks · mean realized q ${f3(sum('q') / n)} · mean expected q ${f3(sum('expected') / n)} · ${succ} full success${succ === 1 ? '' : 'es'}`
      : 'No tasks match these filters.';
    redraw('stripChart');
    renderTable();
  }
  function taskTip(t, extra) {
    return tipContent(`#${t.id} ${t._name}`, [
      { v: f3(t.q), l: 'realized mean q', c: pcol(t.policy), box: true },
      { v: `${f3(t.q_ci95[0])}–${f3(t.q_ci95[1])}`, l: '95% interval' },
      { v: f3(t.expected), l: 'expected at freeze', c: 'var(--ink)' },
      { v: sgn(t.q - t.expected), l: 'gap' },
      { v: `${t.successes}/10`, l: 'full successes' },
      { v: pname(t.policy), l: `stage ${t.stage}` },
      ...(extra || [])]);
  }
  function stripChart() {
    const box = $('#stripChart'), all = CUR, more = $('#stripMore');
    const narrow = box.clientWidth < 560;
    if (narrow) {
      const rows = stripAll ? all : all.slice(0, 20), rowH = 22, top = 24, bot = 24;
      box.style.height = Math.max(110, rows.length * rowH + top + bot) + 'px';
      const { svg, W, H } = frame(box, 'Realized and expected q per task',
        `Ranked dot plot of ${rows.length} of ${all.length} tasks sorted by ${SORTS[st.sort][0]}. Dots show realized mean q, coloured by checkpoint; ticks show expected q.`);
      const lw = Math.min(150, W * 0.42), x = lin(0, 1, lw + 10, W - 10), g = s('g', null, svg);
      [0, 0.25, 0.5, 0.75, 1].forEach(t => {
        s('line', { class: 'gl', x1: x(t), x2: x(t), y1: top - 4, y2: H - bot + 2 }, g);
        s('text', { class: 'tk', x: x(t), y: 13, 'text-anchor': 'middle', text: qt(t) }, g);
      });
      const hb = hoverBand(g), items = [];
      rows.forEach((t, i) => {
        const cy = top + i * rowH + rowH / 2;
        s('text', { class: 'dl2', x: 0, y: cy + 4, text: clip(t._name, lw) }, g);
        if (st.ci) s('line', { class: 'wh', x1: x(t.q_ci95[0]), x2: x(t.q_ci95[1]), y1: cy, y2: cy }, g);
        s('line', { class: 'xt', x1: x(t.expected), x2: x(t.expected), y1: cy - 6, y2: cy + 6 }, g);
        s('circle', { class: 'bar', 'data-p': t.policy, cx: x(t.q), cy, r: 4.5, style: `fill:${pcol(t.policy)};stroke:var(--ring);stroke-width:2` }, g);
        items.push({ x: x(t.q), y: cy, t, tip: () => taskTip(t) });
      });
      s('text', { class: 'al', x: 0, y: H - 7, text: all.length ? `${rows.length} of ${all.length} tasks, sorted by ${SORTS[st.sort][0]}` : 'No tasks match these filters' }, g);
      interact(svg, items, 'y', i => { if (i < 0) hb.setAttribute('visibility', 'hidden'); else showBand(hb, 0, top + i * rowH, W, rowH); }, it => openTask(it.t.id));
      more.hidden = all.length <= 20;
      more.textContent = stripAll ? 'Show the first 20 only' : `Show all ${all.length} tasks`;
      return;
    }
    more.hidden = true;
    box.style.height = '300px';
    const { svg, W, H } = frame(box, 'Realized and expected q per task',
      `${all.length} tasks sorted by ${SORTS[st.sort][0]}. Bars show realized mean q over instances 301–310, coloured by checkpoint; ticks show expected q at freeze.`);
    const m = { l: 34, r: 6, t: 10, b: 26 }, pw = W - m.l - m.r, ph = H - m.t - m.b;
    const y = lin(0, 1, m.t + ph, m.t), g = s('g', null, svg);
    yAxis(g, y, [0, 0.25, 0.5, 0.75, 1], qt, m.l, W - m.r);
    s('text', { class: 'al', x: m.l, y: H - 6, text: all.length ? `${all.length} task${all.length === 1 ? '' : 's'}, sorted by ${SORTS[st.sort][0]}` : 'No tasks match these filters' }, g);
    if (!all.length) return;
    const band = Math.min(pw / all.length, 30), bw = band >= 6 ? Math.min(24, band - 2) : Math.max(1, band * 0.72);
    const hb = hoverBand(g), items = [], yb = y(0);
    all.forEach((t, i) => {
      const x = m.l + i * band + (band - bw) / 2, cx = x + bw / 2;
      const a = { class: 'bar', 'data-p': t.policy, style: 'fill:' + pcol(t.policy) };
      if (t.q > 0) s('path', Object.assign(a, { d: bw >= 6 ? vbar(x, y(t.q), yb, bw) : `M${x},${yb}V${y(t.q)}H${x + bw}V${yb}Z` }), g);
      else s('rect', Object.assign(a, { x, y: yb - 2, width: bw, height: 2 }), g);
      if (st.ci) s('line', { class: 'wh', x1: cx, x2: cx, y1: y(t.q_ci95[0]), y2: y(t.q_ci95[1]) }, g);
      const tw = Math.max(bw + 4, band), ye = Math.round(y(t.expected));
      s('line', { class: 'xt', x1: cx - tw / 2, x2: cx + tw / 2, y1: ye, y2: ye }, g);
      items.push({ x: cx, y: y(Math.max(t.q, t.expected)), t, tip: () => taskTip(t) });
    });
    interact(svg, items, 'x', i => { if (i < 0) hb.setAttribute('visibility', 'hidden'); else showBand(hb, m.l + i * band, m.t, band, ph); }, it => openTask(it.t.id));
  }
  function heat(t) {
    return h('div', { class: 'heat', 'data-id': t.id, role: 'img', 'aria-label': 'Per-instance q, instances 301 to 310: ' + t.qs.map(f2).join(', ') },
      t.qs.map((v, i) => h('i', { 'data-i': i, style: `background:color-mix(in oklab, var(--heat1) ${Math.round(v * 100)}%, var(--heat0))` })));
  }
  function taskRow(t) {
    const open = OPEN.has(t.id);
    return h('tr', { class: 'row' + (open ? ' open' : ''), id: 'task-' + t.id, 'data-id': t.id },
      h('td', { class: 'c-id', text: t.id }),
      h('td', { class: 'c-task' }, h('button', { class: 'tbtn', type: 'button', 'aria-expanded': String(open), 'aria-controls': open ? 'det-' + t.id : null, text: t._name })),
      h('td', { class: 'c-pol' }, h('span', { class: 'pol' }, h('span', { class: 'sw', style: 'background:' + pcol(t.policy) }), h('span', { text: pname(t.policy) }))),
      h('td', { class: 'c-num c-st', 'data-label': 'Stage', text: t.stage }),
      h('td', { class: 'c-num c-ex', 'data-label': 'Expected', text: f3(t.expected) }),
      h('td', { class: 'c-num c-re', 'data-label': 'Realized', text: f3(t.q) }),
      h('td', { class: 'c-num c-su', 'data-label': 'Success', text: `${t.successes}/10` }),
      h('td', { class: 'c-heat' }, heat(t)));
  }
  function renderTable() {
    const limit = mobile() ? tableLimit : Infinity, rows = CUR.slice(0, limit);
    const frag = document.createDocumentFragment();
    if (!CUR.length) frag.append(h('tr', null, h('td', { colspan: 8, class: 'empty', text: 'No tasks match these filters.' })));
    rows.forEach(t => { frag.append(taskRow(t)); if (OPEN.has(t.id)) frag.append(detailRow(t)); });
    $('#taskBody').replaceChildren(frag);
    const more = $('#tableMore'), left = CUR.length - rows.length;
    more.hidden = left <= 0;
    more.textContent = `Show ${Math.min(20, left)} more (${left} remaining)`;
  }
  function detailRow(t) {
    const fb = t.fallback ? `${pname(t.fallback)} (expected ${f3(t.fallback_expected)})${t.fallback === t.policy ? ', same as routed' : ''}` : 'none recorded';
    const devs = Object.entries(t.dev).sort((a, b) => b[1].n - a[1].n || b[1].mean - a[1].mean);
    const totalN = devs.reduce((a, d) => a + d[1].n, 0);
    const dt = (a, b) => [h('dt', { text: a }), h('dd', { text: b })];
    return h('tr', { class: 'det', id: 'det-' + t.id }, h('td', { colspan: 8 }, h('div', { class: 'det-in' },
      h('div', null,
        t.instruction ? h('p', { class: 'instr', text: '“' + t.instruction + '”' })
          : h('p', { class: 'instr none', text: 'No natural-language instruction is included in the released data for this task.' }),
        h('dl', { class: 'facts' }, dt('Scene', sceneName(t.scene)), dt('Mean demo length', `${t.demo_s} s`),
          dt('Routed checkpoint', `${pname(t.policy)} · stage ${t.stage}`), dt('Own rollouts at freeze', String(t.own_dev_n)),
          dt('95% interval', `${f3(t.q_ci95[0])}–${f3(t.q_ci95[1])}`), dt('Fallback recorded at freeze', fb)),
        h('div', { class: 'iv' }, t.qs.map((v, i) => h('span', null, `${301 + i} `, h('b', { text: f2(v) }))))),
      h('div', null,
        h('div', { class: 'lbl', text: `Development evidence · ${totalN} rollout${totalN === 1 ? '' : 's'}` }),
        devs.length ? h('table', { class: 'mini' },
          h('thead', null, h('tr', null, h('th', { scope: 'col', text: 'Checkpoint' }), h('th', { scope: 'col', class: 'n', text: 'n' }), h('th', { scope: 'col', class: 'n', text: 'mean q' }))),
          h('tbody', null, devs.map(([p, v]) => h('tr', { class: p === t.policy ? 'rt' : null },
            h('td', null, h('span', { class: 'pcell' }, POL[p] ? h('span', { class: 'sw', style: 'background:' + pcol(p) }) : null,
              POL[p] ? h('span', { text: pname(p) }) : h('span', { class: 'pidm', text: p }),
              p === t.policy ? h('span', { class: 'tag', text: 'routed' }) : null,
              p === t.fallback && p !== t.policy ? h('span', { class: 'tag', text: 'fallback' }) : null)),
            h('td', { class: 'n', text: v.n }), h('td', { class: 'n', text: f3(v.mean) }))))) : null,
        t.dev[t.policy] ? null : h('p', { class: 'mini-note', text: 'The routed checkpoint has no development rollouts on this task.' }),
        h('p', { class: 'mini-note', text: 'Labels without a display name were tested in development but not routed.' })))));
  }
  function setHash(hash) { try { history.replaceState(null, '', location.pathname + location.search + hash); } catch (e) { /* ignore */ } }
  function toggleTask(id, force) {
    const tr = $(`#taskBody tr.row[data-id="${id}"]`);
    if (!tr) return null;
    const btn = $('.tbtn', tr), open = OPEN.has(id), want = force == null ? !open : force;
    if (want === open) return tr;
    btn.setAttribute('aria-expanded', String(want));
    tr.classList.toggle('open', want);
    if (want) { OPEN.add(id); tr.after(detailRow(TASK[id])); btn.setAttribute('aria-controls', 'det-' + id); setHash('#task-' + id); }
    else { OPEN.delete(id); const d = $('#det-' + id); if (d) d.remove(); btn.removeAttribute('aria-controls'); if (location.hash === '#task-' + id) setHash(''); }
    return tr;
  }
  function openTask(id) {
    if (!TASK[id]) return;
    if (!CUR.includes(TASK[id])) { resetFilters(); syncControls(); CUR = filtered(); renderExplorer(); writeURL(); }
    const idx = CUR.indexOf(TASK[id]);
    if (mobile() && idx >= tableLimit) { tableLimit = Math.ceil((idx + 1) / 20) * 20; renderTable(); }
    const tr = toggleTask(id, true);
    if (tr) { tr.scrollIntoView({ block: 'center' }); $('.tbtn', tr).focus({ preventScroll: true }); }
  }
  function tableEvents() {
    const body = $('#taskBody');
    body.addEventListener('click', e => { if (e.target.closest('a, .det')) return; const tr = e.target.closest('tr.row'); if (tr) toggleTask(+tr.dataset.id); });
    body.addEventListener('pointerover', e => {
      const c = e.target.closest('.heat i'); if (!c || e.pointerType === 'touch') return;
      const t = TASK[+c.parentNode.dataset.id], i = +c.dataset.i;
      tipShow(tipContent(`#${t.id} ${t._name}`, [{ v: f3(t.qs[i]), l: `q on instance ${301 + i}` }]), e.clientX, e.clientY);
    });
    body.addEventListener('pointerout', e => { if (e.target.closest('.heat i')) tipHide(); });
    addEventListener('hashchange', () => { const m = /^#task-(\d+)$/.exec(location.hash); if (m) openTask(+m[1]); });
  }

  /* ---------- analysis ---------- */
  function calChart() {
    const box = $('#calChart'), T = D.tasks, C = D.calibration;
    const m = { l: 46, r: 12, t: 12, b: 40 };
    const side = Math.max(170, Math.min(box.clientWidth - m.l - m.r, 440));
    box.style.height = side + m.t + m.b + 'px';
    const { svg, W } = frame(box, 'Expected versus realized q per task',
      `Square scatter of ${T.length} tasks on a common 0 to 1 scale, coloured by own development rollouts (0, 1, 2 or more); stage 1 hollow, stage 2 filled. Spearman ${f2(C.spearman)}, Pearson ${f2(C.pearson)}.`);
    const ox = Math.max(0, (W - (m.l + side + m.r)) / 2) + m.l;
    const x = lin(0, 1, ox, ox + side), y = lin(0, 1, m.t + side, m.t), g = s('g', null, svg);
    const ticks = [0, 0.2, 0.4, 0.6, 0.8, 1];
    ticks.forEach((t, i) => {
      const yy = Math.round(y(t)) + 0.5, xx = Math.round(x(t)) + 0.5;
      s('line', { class: i ? 'gl' : 'bl', x1: ox, x2: ox + side, y1: yy, y2: yy }, g);
      s('line', { class: i ? 'gl' : 'bl', x1: xx, x2: xx, y1: m.t, y2: m.t + side }, g);
      s('text', { class: 'tk', x: ox - 6, y: yy + 3.5, 'text-anchor': 'end', text: qt(t) }, g);
      if (i) s('text', { class: 'tk', x: xx, y: m.t + side + 15, 'text-anchor': 'middle', text: qt(t) }, g);
    });
    s('line', { class: 'ref', x1: x(0), y1: y(0), x2: x(1), y2: y(1) }, g);
    s('text', { class: 'dl2', x: x(1) - 4, y: y(1) + 14, 'text-anchor': 'end', text: 'y = x' }, g);
    s('text', { class: 'al', x: ox + side / 2, y: m.t + side + 32, 'text-anchor': 'middle', text: 'Expected q at freeze' }, g);
    yLabel(g, 'Realized mean q, 301–310', ox - 34, m.t + side / 2);
    const jit = t => (t.q === 0 ? ((t.id * 7) % 9) - 4 : 0);
    if (st.calCI) T.forEach(t => s('line', { class: 'wh', x1: x(t.expected), x2: x(t.expected), y1: y(t.q_ci95[0]), y2: y(t.q_ci95[1]), style: `stroke:${dcol(t)}` }, g));
    const order = T.slice().sort((a, b) => b.stage - a.stage || a.id - b.id);
    order.forEach(t => s('circle', { cx: x(t.expected), cy: y(t.q) + jit(t), r: 4.5,
      style: t.stage === 1 ? `fill:var(--ring);stroke:${dcol(t)};stroke-width:2` : `fill:${dcol(t)};stroke:var(--ring);stroke-width:1.5` }, g));
    const ring = s('circle', { r: 8.5, class: 'hl', visibility: 'hidden' }, g);
    const items = order.map(t => ({ x: x(t.expected), y: y(t.q) + jit(t), t, tip: () => {
      const same = T.filter(o => o !== t && o.expected === t.expected && o.q === t.q).length;
      return taskTip(t, [{ v: String(t.own_dev_n), l: 'own rollouts at freeze', c: dcol(t), box: true },
        ...(same ? [{ v: String(same), l: `other task${same === 1 ? '' : 's'} at this point` }] : [])]);
    } }));
    interact(svg, items, 'xy', i => {
      if (i < 0) ring.setAttribute('visibility', 'hidden');
      else { ring.setAttribute('cx', items[i].x); ring.setAttribute('cy', items[i].y); ring.setAttribute('visibility', 'visible'); }
    }, it => openTask(it.t.id));
  }
  /* Neutral column chart; labelsAt 'edge' puts tick labels on bin boundaries. */
  function columns(id, opts) {
    const { values, emphIdx, title, desc, yName, xName, tipFn } = opts;
    const box = document.getElementById(id), { svg, W, H } = frame(box, title, desc);
    const m = { l: 50, r: 10, t: 22, b: 40 };
    const ticks = niceTicks(0, Math.max(...values), 4), mx = Math.max(...values);
    if (ticks[ticks.length - 1] < mx) ticks.push(+(ticks[ticks.length - 1] + ticks[1] - ticks[0]).toFixed(6));
    const y = lin(0, ticks[ticks.length - 1], H - m.b, m.t), g = s('g', null, svg);
    yAxis(g, y, ticks, fint, m.l, W - m.r);
    yLabel(g, yName, 13, (m.t + H - m.b) / 2);
    s('text', { class: 'al', x: (m.l + W - m.r) / 2, y: H - 4, 'text-anchor': 'middle', text: xName }, g);
    const band = (W - m.l - m.r) / values.length, bw = Math.min(24, band - 2);
    const hb = hoverBand(g), items = [], narrow = W < 380;
    values.forEach((v, i) => {
      const x = m.l + i * band + (band - bw) / 2;
      if (v > 0) s('path', { d: vbar(x, y(v), y(0), bw), class: 'bar ' + (i === emphIdx ? 'ink-fill' : 'ink2-fill') }, g);
      if (opts.labelsAt !== 'edge' && (!narrow || i % 2 === 0 || i === emphIdx)) s('text', { class: 'tk', x: x + bw / 2, y: H - m.b + 15, 'text-anchor': 'middle', text: opts.labels[i] }, g);
      items.push({ x: x + bw / 2, y: y(v), tip: () => tipFn(i) });
    });
    if (opts.labelsAt === 'edge') opts.labels.forEach((l, i) => {
      if (narrow && i % 2) return;
      const xx = m.l + i * band;
      s('line', { class: 'bl', x1: xx, x2: xx, y1: H - m.b, y2: H - m.b + 4 }, g);
      s('text', { class: 'tk', x: xx, y: H - m.b + 15, 'text-anchor': 'middle', text: l }, g);
    });
    (opts.notes || []).forEach(([i, text]) => s('text', { class: 'dl2', x: m.l + i * band + band / 2, y: y(0) - 6, 'text-anchor': 'middle', text }, g));
    if (emphIdx >= 0) s('text', { class: 'dl', x: m.l + emphIdx * band + band / 2, y: y(values[emphIdx]) - 6, 'text-anchor': 'middle', text: fint(values[emphIdx]) }, g);
    interact(svg, items, 'x', i => { if (i < 0) hb.setAttribute('visibility', 'hidden'); else showBand(hb, m.l + i * band, m.t, band, H - m.t - m.b); });
  }
  function histChart() {
    const hs = D.histogram, total = hs.reduce((a, b) => a + b, 0);
    const lab = i => `[${(i / 10).toFixed(1)}, ${i === 9 ? '1.0]' : ((i + 1) / 10).toFixed(1) + ')'}`;
    columns('histChart', { values: hs, emphIdx: 0, labelsAt: 'edge', labels: hs.map((_, i) => (i / 10).toFixed(1)).concat('1.0'),
      title: 'Distribution of episode q', desc: `Histogram of ${fint(total)} episodes in ten bins of width 0.1. ${fint(hs[0])} fall in the lowest bin.`,
      yName: 'Episodes', xName: 'Episode q',
      tipFn: i => tipContent(`q in ${lab(i)}`, [{ v: fint(hs[i]), l: 'episodes' }, { v: ((hs[i] / total) * 100).toFixed(1) + '%', l: 'of all episodes' }]) });
  }
  function devKeys() { const ks = []; for (let k = 311; k <= 320; k++) ks.push(String(k)); return ks; }
  function devChart() {
    const ks = devKeys(), vs = ks.map(k => D.dev_instances[k] || 0), total = vs.reduce((a, b) => a + b, 0), ei = ks.indexOf('313');
    columns('devChart', { values: vs, emphIdx: ei, labels: ks, notes: vs.map((v, i) => [i, v ? null : '0']).filter(n => n[1]),
      title: 'Development rollouts per instance', desc: `Columns for development instances 311 to 320. Instance 313 has ${fint(vs[ei])} of ${fint(total)} rollouts; 320 has none.`,
      yName: 'Rollouts', xName: 'Development instance',
      tipFn: i => tipContent(`Instance ${ks[i]}`, [{ v: fint(vs[i]), l: 'rollouts' }, { v: ((vs[i] / total) * 100).toFixed(1) + '%', l: 'of the ledger' }]) });
  }
  function powChart() {
    const box = $('#powChart'), es = Object.keys(D.power).sort((a, b) => a - b), sel = D.breakdown.selection_n;
    const A = es.map(e => [+e, D.power[e]]), B = Object.keys(sel).sort((a, b) => a - b).map(e => [+e, sel[e]]);
    const { svg, W, H } = frame(box, 'Rollouts per policy needed versus difference in mean q',
      `Log-log chart. Significance test: ${A.map(p => `${p[0]} needs ${fint(p[1])}`).join('; ')}. Picking the better with 80% probability: ${B.map(p => `${p[0]} needs ${fint(p[1])}`).join('; ')}.`);
    const m = { l: 58, r: 16, t: 14, b: 40 };
    const x = logS(0.015, 0.27, m.l, W - m.r), y = logS(1, 2500, H - m.b, m.t), g = s('g', null, svg);
    [1, 10, 100, 1000].forEach((t, i) => {
      const yy = Math.round(y(t)) + 0.5;
      s('line', { class: i ? 'gl' : 'bl', x1: m.l, x2: W - m.r, y1: yy, y2: yy }, g);
      s('text', { class: 'tk', x: m.l - 6, y: yy + 3.5, 'text-anchor': 'end', text: fint(t) }, g);
    });
    es.forEach(e => s('text', { class: 'tk', x: x(+e), y: H - m.b + 15, 'text-anchor': 'middle', text: (+e).toFixed(2) }, g));
    s('line', { class: 'ref', x1: m.l, x2: W - m.r, y1: y(10), y2: y(10) }, g);
    s('text', { class: 'dl2', x: m.l + 6, y: y(10) + 14, text: '10 development instances' }, g);
    s('text', { class: 'al', x: (m.l + W - m.r) / 2, y: H - 4, 'text-anchor': 'middle', text: 'Difference in mean q (log scale)' }, g);
    yLabel(g, 'Rollouts per policy (log scale)', 13, (m.t + H - m.b) / 2);
    const path = P => 'M' + P.map(p => `${x(p[0])},${y(p[1])}`).join('L');
    s('path', { class: 'ln', d: path(A) }, g);
    s('path', { class: 'ln', d: path(B), style: 'stroke:var(--ink-2)' }, g);
    A.forEach(p => { s('circle', { class: 'dot-in', cx: x(p[0]), cy: y(p[1]), r: 4.5 }, g); s('text', { class: 'dl', x: x(p[0]) + 7, y: y(p[1]) - 7, text: fint(p[1]) }, g); });
    B.forEach(p => { s('circle', { class: 'dot-out', cx: x(p[0]), cy: y(p[1]), r: 4.5 }, g); s('text', { class: 'dl2', x: x(p[0]) + 7, y: y(p[1]) + 15, text: fint(p[1]) }, g); });
    const items = es.map(e => ({ x: x(+e), y: y(D.power[e]), tip: () => tipContent(`Difference ${(+e).toFixed(2)} in mean q`, [
      { v: fint(D.power[e]), l: 'significance test', c: 'var(--ink)' },
      { v: sel[e] != null ? fint(sel[e]) : 'not computed', l: 'pick the better (80%)', c: 'var(--ink-2)' }]) }));
    interact(svg, items, 'x');
  }
  const stageLabel = k => { const t = k.replace(/(\d)-(\d)/g, '$1–$2'); return t.charAt(0).toUpperCase() + t.slice(1); };
  function optRows() {
    const bd = D.breakdown.by_depth, bs = D.breakdown.by_stage;
    const dl = { 0: '0 own rollouts', 1: '1 own rollout', '2+': '2 or more own rollouts' };
    return [
      { head: 'By evidence depth at freeze' },
      ...Object.keys(bd).map((k, i) => Object.assign({ label: dl[k] || k, c: `var(--d${Math.min(i, 2)})` }, bd[k])),
      { head: 'By stage' },
      ...Object.keys(bs).map(k => Object.assign({ label: stageLabel(k), c: 'var(--ink)' }, bs[k])),
    ];
  }
  function optChart() {
    const box = $('#optChart'), R = optRows(), narrow = box.clientWidth < 560;
    const rowH = narrow ? 42 : 30, headH = 26;
    const H0 = R.reduce((a, r) => a + (r.head ? headH : rowH), 0) + 30;
    box.style.height = H0 + 'px';
    const { svg, W, H } = frame(box, 'Expected and realized mean q by evidence depth and by stage',
      R.filter(r => !r.head).map(r => `${r.label}, ${r.tasks} tasks: expected ${f3(r.expected)}, realized ${f3(r.realized)}, gap ${fmt(r.gap_points, 'sp1')} task points`).join('. ') + '.');
    const lw = narrow ? 0 : Math.min(250, W * 0.36), gw = 74, x0 = lw + (narrow ? 4 : 12), x1 = W - gw;
    const max = Math.max(...R.filter(r => !r.head).map(r => Math.max(r.expected, r.realized)));
    const x = lin(0, Math.ceil(max * 10) / 10, x0, x1), g = s('g', null, svg);
    const ticks = niceTicks(0, Math.ceil(max * 10) / 10, 3);
    ticks.forEach(t => { s('line', { class: 'gl', x1: x(t), x2: x(t), y1: 4, y2: H - 24 }, g); s('text', { class: 'tk', x: x(t), y: H - 8, 'text-anchor': 'middle', text: qt(t) }, g); });
    s('text', { class: 'tk', x: W, y: H - 8, 'text-anchor': 'end', text: 'gap, pts' }, g);
    const hb = hoverBand(g), items = [];
    let yy = 2;
    R.forEach(r => {
      if (r.head) { s('text', { class: 'tz-head', x: 0, y: yy + 17, text: r.head }, g); yy += headH; return; }
      const cy = narrow ? yy + 28 : yy + rowH / 2;
      s('text', { class: 'dl2', x: narrow ? 0 : lw, y: narrow ? yy + 13 : cy + 4, 'text-anchor': narrow ? 'start' : 'end', text: `${r.label} · ${r.tasks}` }, g);
      s('line', { class: 'bl', x1: x(Math.min(r.expected, r.realized)), x2: x(Math.max(r.expected, r.realized)), y1: cy, y2: cy, style: 'stroke-width:2' }, g);
      s('line', { class: 'xt', x1: x(r.expected), x2: x(r.expected), y1: cy - 8, y2: cy + 8 }, g);
      s('circle', { cx: x(r.realized), cy, r: 5.5, style: `fill:${r.c};stroke:var(--ring);stroke-width:2` }, g);
      s('text', { class: 'dl', x: W, y: cy + 4, 'text-anchor': 'end', text: fmt(r.gap_points, 'sp1') }, g);
      const top = yy;
      items.push({ x: x(r.realized), y: cy, tip: () => tipContent(`${r.label} (${r.tasks} tasks)`, [
        { v: f3(r.expected), l: 'expected mean q', c: 'var(--ink)' }, { v: f3(r.realized), l: 'realized mean q', c: r.c, box: true },
        { v: fmt(r.gap_points, 'sp1'), l: 'gap in task points' }]), band: [top, rowH] });
      yy += rowH;
    });
    interact(svg, items, 'y', i => { if (i < 0) hb.setAttribute('visibility', 'hidden'); else showBand(hb, 0, items[i].band[0], W, items[i].band[1]); });
    $('#optTable').replaceChildren(miniTable(['Group', 'Tasks', 'Expected', 'Realized', 'Gap (task points)'],
      R.filter(r => !r.head).map(r => [r.label, String(r.tasks), f3(r.expected), f3(r.realized), fmt(r.gap_points, 'sp1')]), 'Expected and realized mean q by group'));
  }

  /* ---------- simulation ---------- */
  function rulesChart() {
    const box = $('#rulesChart'), R = D.simulation.rules, keys = Object.keys(R), narrow = box.clientWidth < 400;
    const rowH = narrow ? 44 : 36;
    box.style.height = keys.length * rowH + 44 + 'px';
    const { svg, W, H } = frame(box, 'True and claimed Q by selection rule',
      keys.map(k => `${k}: true ${f3(R[k].true)} (90% range ${f3(R[k].true_p05)} to ${f3(R[k].true_p95)})${R[k].claimed != null ? `, claimed ${f3(R[k].claimed)}` : ', no claim'}`).join('. ') + '.');
    const lw = narrow ? 0 : Math.min(150, W * 0.32), x0 = lw + (narrow ? 4 : 12), x1 = W - 10;
    const lo = Math.min(...keys.map(k => R[k].true_p05)), hi = Math.max(...keys.map(k => Math.max(R[k].true_p95, R[k].claimed || 0)));
    const d0 = Math.floor(lo * 20) / 20, d1 = Math.ceil(hi * 20) / 20, x = lin(d0, d1, x0, x1), g = s('g', null, svg);
    niceTicks(d0, d1, 4).forEach(t => { s('line', { class: 'gl', x1: x(t), x2: x(t), y1: 2, y2: H - 36 }, g); s('text', { class: 'tk', x: x(t), y: H - 22, 'text-anchor': 'middle', text: qt(t) }, g); });
    s('text', { class: 'al', x: (x0 + x1) / 2, y: H - 5, 'text-anchor': 'middle', text: 'Q on tasks 50–99' }, g);
    const hb = hoverBand(g), items = [];
    keys.forEach((k, i) => {
      const r = R[k], top = 2 + i * rowH, cy = narrow ? top + 29 : top + rowH / 2, ours = /ours/.test(k);
      if (ours) s('rect', { class: 'rowband', x: 0, y: top, width: W, height: rowH, rx: 4 }, g);
      s('text', { class: ours ? 'dlb' : 'dl2', x: narrow ? 4 : lw, y: narrow ? top + 13 : cy + 4, 'text-anchor': narrow ? 'start' : 'end', text: k }, g);
      s('line', { class: 'ln', x1: x(r.true_p05), x2: x(r.true_p95), y1: cy, y2: cy, style: 'stroke:var(--ink-2);stroke-width:2' }, g);
      if (r.claimed != null) s('circle', { class: 'dot-out', cx: x(r.claimed), cy, r: 5.5 }, g);
      s('circle', { class: 'dot-in', cx: x(r.true), cy, r: 4.5 }, g);
      items.push({ x: x(r.true), y: cy, tip: () => tipContent(k, [
        { v: f3(r.true), l: `true Q (90%: ${f3(r.true_p05)}–${f3(r.true_p95)})`, c: 'var(--ink)' },
        { v: r.claimed != null ? f3(r.claimed) : 'none', l: 'claimed Q', c: 'var(--ink-2)' },
        ...(r.optimism != null ? [{ v: sgn(r.optimism), l: 'overclaim' }] : []),
        { v: f3(r.regret), l: 'regret against the oracle' }]), top });
    });
    interact(svg, items, 'y', i => { if (i < 0) hb.setAttribute('visibility', 'hidden'); else showBand(hb, 0, items[i].top, W, rowH); });
  }
  function budgetChart() {
    const box = $('#budgetChart'), C = D.simulation.curve, mult = Object.keys(C).sort((a, b) => a - b);
    const series = [
      { k: 'strict rules (ours)', label: 'strict (ours)', cls: 'ln', col: 'var(--ink)', shape: 'c' },
      { k: 'best dev mean', label: 'best dev mean', cls: 'ln', col: 'var(--ink-2)', shape: 's' },
      { k: 'oracle', label: 'oracle', cls: 'ln2', col: 'var(--muted)', shape: 'd' },
    ];
    const { svg, W, H } = frame(box, 'True Q as the development budget grows',
      series.map(se => `${se.label}: ` + mult.map(mm => `×${mm} ${f3(C[mm][se.k].true)}`).join(', ')).join('. ') + '.');
    const m = { l: 50, r: 92, t: 12, b: 40 };
    const vals = mult.flatMap(mm => series.flatMap(se => [C[mm][se.k].true_p05, C[mm][se.k].true_p95]));
    const d0 = Math.floor(Math.min(...vals) * 50) / 50, d1 = Math.ceil(Math.max(...vals) * 50) / 50;
    const x = logS(+mult[0], +mult[mult.length - 1], m.l + 10, W - m.r), y = lin(d0, d1, H - m.b, m.t), g = s('g', null, svg);
    yAxis(g, y, niceTicks(d0, d1, 4).filter(t => t >= d0), qt, m.l, W - m.r + 8, false);
    s('line', { class: 'bl', x1: m.l, x2: W - m.r + 8, y1: H - m.b + 0.5, y2: H - m.b + 0.5 }, g);
    mult.forEach(mm => s('text', { class: 'tk', x: x(+mm), y: H - m.b + 15, 'text-anchor': 'middle', text: '×' + mm }, g));
    s('text', { class: 'al', x: (m.l + W - m.r) / 2, y: H - 4, 'text-anchor': 'middle', text: 'Development budget (log scale)' }, g);
    yLabel(g, 'True Q, tasks 50–99', 13, (m.t + H - m.b) / 2);
    series.forEach(se => {
      const up = mult.map(mm => [x(+mm), y(C[mm][se.k].true_p95)]), dn = mult.map(mm => [x(+mm), y(C[mm][se.k].true_p05)]).reverse();
      s('path', { d: 'M' + up.concat(dn).map(p => p.join(',')).join('L') + 'Z', style: `fill:${se.col};opacity:0.09` }, g);
    });
    series.forEach(se => {
      const pts = mult.map(mm => [x(+mm), y(C[mm][se.k].true)]);
      s('path', { class: se.cls, d: 'M' + pts.map(p => p.join(',')).join('L'), style: se.cls === 'ln' ? `stroke:${se.col}` : null }, g);
      pts.forEach(([px, py]) => {
        if (se.shape === 'c') s('circle', { cx: px, cy: py, r: 4.5, style: `fill:${se.col};stroke:var(--ring);stroke-width:2` }, g);
        else if (se.shape === 's') s('rect', { x: px - 4, y: py - 4, width: 8, height: 8, style: `fill:${se.col};stroke:var(--ring);stroke-width:1.5` }, g);
        else s('path', { d: `M${px},${py - 5}L${px + 5},${py}L${px},${py + 5}L${px - 5},${py}Z`, style: `fill:${se.col};stroke:var(--ring);stroke-width:1.5` }, g);
      });
      const last = pts[pts.length - 1];
      s('text', { class: se.k.includes('ours') ? 'dlb' : 'dl2', x: last[0] + 10, y: last[1] + 4, text: se.label }, g);
    });
    const cross = s('line', { class: 'gl', y1: m.t, y2: H - m.b, visibility: 'hidden', style: 'stroke:var(--ink-2)' }, g);
    const items = mult.map(mm => ({ x: x(+mm), y: m.t + 10, tip: () => tipContent(`Budget ×${mm}`,
      series.map(se => ({ v: f3(C[mm][se.k].true), l: `${se.label} (90%: ${f3(C[mm][se.k].true_p05)}–${f3(C[mm][se.k].true_p95)})`, c: se.col }))) }));
    interact(svg, items, 'x', i => { if (i < 0) cross.setAttribute('visibility', 'hidden'); else { cross.setAttribute('x1', items[i].x); cross.setAttribute('x2', items[i].x); cross.setAttribute('visibility', 'visible'); } });
  }

  /* ---------- page wiring ---------- */
  function bindNumbers() {
    $$('[data-bind]').forEach(e => {
      const v = evalBind(D, e.dataset.bind);
      if (v != null) e.textContent = fmt(v, e.dataset.fmt || 'raw');
    });
  }
  /* Also produced by tools/prerender_site.py; keep the wording identical. */
  function disagreeText() {
    const R = D.reproduction;
    if (!R || !R.disagreements.length) return '';
    const items = R.disagreements.map(d => `task ${d.task_id} (${TASK[d.task_id] ? TASK[d.task_id]._name.toLowerCase() : ''}), where it prefers ${pname(d.ours)}, posterior ${f3(d.posterior_ours)}, and the frozen route chose ${pname(d.frozen)}, posterior ${f3(d.posterior_frozen)}`);
    return `It disagrees on ${items.join('; and on ')}.`;
  }
  function tables() {
    const hs = D.histogram, dv = D.dev_instances, sel = D.breakdown.selection_n;
    $('#histTable').replaceChildren(miniTable(['q bin', 'Episodes'], hs.map((v, i) => [`${(i / 10).toFixed(1)}–${((i + 1) / 10).toFixed(1)}`, fint(v)]), 'Episodes per q bin'));
    $('#devTable').replaceChildren(miniTable(['Instance', 'Rollouts'], devKeys().map(k => [k, fint(dv[k] || 0)]), 'Development rollouts per instance'));
    $('#powTable').replaceChildren(miniTable(['Difference', 'Significance test', 'Pick the better (80%)'],
      Object.keys(D.power).sort((a, b) => a - b).map(k => [k, fint(D.power[k]), sel[k] != null ? fint(sel[k]) : '–']), 'Rollouts per policy'));
    const R = D.simulation.rules;
    $('#rulesTable').replaceChildren(miniTable(['Rule', 'True Q', '90% range', 'Claimed', 'Regret'],
      Object.keys(R).map(k => [k, f3(R[k].true), `${f3(R[k].true_p05)}–${f3(R[k].true_p95)}`, R[k].claimed != null ? f3(R[k].claimed) : '–', f3(R[k].regret)]), 'Simulated true and claimed Q by rule'));
    const C = D.simulation.curve, mult = Object.keys(C).sort((a, b) => a - b), ks = Object.keys(C[mult[0]]);
    $('#budgetTable').replaceChildren(miniTable(['Budget', ...ks], mult.map(mm => ['×' + mm, ...ks.map(k => `${f3(C[mm][k].true)} (${f3(C[mm][k].true_p05)}–${f3(C[mm][k].true_p95)})`)]), 'True Q by development budget'));
  }
  function fail(err) {
    const el = $('#loadError');
    el.textContent = 'The results data could not be loaded, so the interactive figures and the explorer are unavailable. The numbers in the text are unaffected.';
    el.hidden = false;
    $('#filters').hidden = true;
    ['pointsChart', 'stripChart', 'calChart', 'histChart', 'devChart', 'powChart', 'optChart', 'rulesChart', 'budgetChart'].forEach(id => {
      const b = document.getElementById(id); b.style.height = 'auto';
      b.replaceChildren(h('p', { class: 'empty', text: 'Figure unavailable: the results data did not load.' }));
    });
    $('#taskBody').replaceChildren(h('tr', null, h('td', { colspan: 8, class: 'empty', text: 'Table unavailable: the results data did not load.' })));
    if (window.console) console.warn('results.json failed to load:', err);
  }
  function start(data) {
    D = data;
    D.tasks.forEach(t => { t._name = humanize(t.name); TASK[t.id] = t; });
    D.policies.forEach(p => { POL[p.policy] = p; });
    assignColors();
    bindNumbers();
    $('#reproDis').textContent = disagreeText();
    redraw('pipeline');
    reg('pointsChart', pointsChart);
    bankCards();
    buildFilters();
    tableEvents();
    readURL();
    syncControls();
    CUR = filtered();
    reg('stripChart', stripChart);
    renderExplorer();
    $('#calCI').addEventListener('change', e => { st.calCI = e.target.checked; redraw('calChart'); });
    reg('calChart', calChart);
    reg('histChart', histChart);
    reg('devChart', devChart);
    reg('powChart', powChart);
    reg('optChart', optChart);
    reg('rulesChart', rulesChart);
    reg('budgetChart', budgetChart);
    tables();
    addEventListener('resize', () => { if (!mobile() && $('#tableMore').hidden === false) renderTable(); });
    const m = /^#task-(\d+)$/.exec(location.hash);
    if (m) setTimeout(() => openTask(+m[1]), 0);
  }

  function themeInit() {
    const btn = $('#themeBtn'), root = document.documentElement, MODES = ['system', 'light', 'dark'];
    const NAMES = { system: 'follow system', light: 'light', dark: 'dark' };
    const cur = () => root.getAttribute('data-theme') || 'system';
    const label = () => {
      const c = cur(), n = MODES[(MODES.indexOf(c) + 1) % 3];
      btn.dataset.mode = c;
      btn.setAttribute('aria-label', `Theme: ${NAMES[c]}. Switch to ${NAMES[n]}.`);
      btn.title = `Theme: ${NAMES[c]}`;
    };
    btn.addEventListener('click', () => {
      const n = MODES[(MODES.indexOf(cur()) + 1) % 3];
      if (n === 'system') root.removeAttribute('data-theme'); else root.setAttribute('data-theme', n);
      try { if (n === 'system') localStorage.removeItem('pb-theme'); else localStorage.setItem('pb-theme', n); } catch (e) { /* storage unavailable */ }
      label();
    });
    label();
  }
  function copyInit() {
    document.addEventListener('click', e => {
      const btn = e.target.closest('button.copy');
      if (!btn) return;
      const src = btn.dataset.copyEl ? document.getElementById(btn.dataset.copyEl) : btn.previousElementSibling;
      const text = src ? src.textContent : '';
      const done = ok => {
        const old = btn.dataset.label || btn.textContent;
        btn.dataset.label = old;
        btn.textContent = ok ? 'Copied' : 'Select and copy';
        live.textContent = ok ? 'Copied to clipboard' : 'Copy failed; select the text and copy it';
        setTimeout(() => { btn.textContent = old; }, 1800);
      };
      const legacy = () => {
        const r = document.createRange(); r.selectNodeContents(src);
        const sel = getSelection(); sel.removeAllRanges(); sel.addRange(r);
        let ok = false; try { ok = document.execCommand('copy'); } catch (err) { ok = false; }
        done(ok);
      };
      if (navigator.clipboard && window.isSecureContext) navigator.clipboard.writeText(text).then(() => done(true), legacy); else legacy();
    });
  }
  function navInit() {
    const nav = $('#nav'), links = $$('a', nav);
    const secs = links.map(a => document.getElementById(a.getAttribute('href').slice(1))).filter(Boolean);
    let current = null, ticking = false;
    function fades() {
      nav.classList.toggle('fade-l', nav.scrollLeft > 2);
      nav.classList.toggle('fade-r', nav.scrollLeft + nav.clientWidth < nav.scrollWidth - 2);
    }
    function update() {
      ticking = false;
      const line = 120;
      let act = null;
      secs.forEach(sec => { if (sec.getBoundingClientRect().top <= line) act = sec.id; });
      if (act === current) return;
      current = act;
      links.forEach(a => { if (a.getAttribute('href') === '#' + act) a.setAttribute('aria-current', 'true'); else a.removeAttribute('aria-current'); });
      const a = act && links.find(l => l.getAttribute('href') === '#' + act);
      if (a && nav.scrollWidth > nav.clientWidth) {
        const l = a.offsetLeft - nav.offsetLeft, r = l + a.offsetWidth;
        if (l < nav.scrollLeft + 24 || r > nav.scrollLeft + nav.clientWidth - 24) nav.scrollTo({ left: l - nav.clientWidth / 2 + a.offsetWidth / 2, behavior: 'smooth' });
      }
    }
    addEventListener('scroll', () => { if (!ticking) { ticking = true; setTimeout(update, 60); } }, { passive: true });
    nav.addEventListener('scroll', fades, { passive: true });
    addEventListener('resize', fades);
    fades(); update();
  }

  function init() {
    themeInit(); copyInit(); navInit();
    reg('pipeline', () => flow('pipeline', pipelineNodes(), ['uni', 'uni', 'uni', 'uni', 'uni', 'uni'], 150));
    reg('servingDiagram', () => flow('servingDiagram', servingNodes, ['bi', 'bi', 'uni'], 150));
    $$('#selForm input').forEach(i => i.addEventListener('input', selUpdate));
    selRead();
    reg('selChart', selChart);
    selUpdate();
    fetch('data/results.json')
      .then(r => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
      .then(start, fail);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
