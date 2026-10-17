/* Policy Bank project page. Vanilla ES2020, no dependencies.
   All numbers come from data/results.json; charts follow the dataviz method:
   categorical hues identify policies only, everything else is neutral ink. */
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

  /* ---------- formatting ---------- */
  const f3 = x => (x == null || isNaN(x) ? '–' : (+x).toFixed(3));
  const f2 = x => (+x).toFixed(2);
  const fint = x => Math.round(x).toLocaleString('en-US');
  const sgn = (x, d = 3) => (x >= 0 ? '+' : '−') + Math.abs(x).toFixed(d);
  const qt = t => (t === 0 ? '0' : t === 1 ? '1' : String(+t.toFixed(2)));
  const humanize = n => { const t = n.replace(/_/g, ' ').replace(/^re /, 're-'); return t.charAt(0).toUpperCase() + t.slice(1); };
  const get = (o, path) => path.split('.').reduce((a, k) => (a == null ? undefined : a[k]), o);
  const lin = (d0, d1, r0, r1) => v => r0 + ((v - d0) / (d1 - d0)) * (r1 - r0);
  const logS = (d0, d1, r0, r1) => { const a = Math.log10(d0), b = Math.log10(d1); return v => r0 + ((Math.log10(v) - a) / (b - a)) * (r1 - r0); };
  function niceTicks(max, n = 4) {
    const raw = max / n, p = Math.pow(10, Math.floor(Math.log10(raw))), m = raw / p;
    const st = (m <= 1 ? 1 : m <= 2 ? 2 : m <= 2.5 ? 2.5 : m <= 5 ? 5 : 10) * p;
    const out = [];
    for (let v = 0; v <= Math.ceil(max / st) * st + 1e-9; v += st) out.push(+v.toFixed(6));
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

  let D = null;            // results.json
  const TASK = {};         // id -> task
  const POL = {};          // policy id -> policy record
  const COLOR = {};        // policy id -> css colour
  let OTHER = [];          // policies folded into grey (palette has 8 validated hues)
  const pcol = id => COLOR[id] || 'var(--c-other)';
  const pname = id => (POL[id] ? POL[id].display : id);
  const FAMILY = { comet: 'comet', winner: 'winner', winner100: 'winner-format specialist' };

  /* ---------- tooltip ---------- */
  const tip = $('#tip');
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
        h('b', { text: r.v }), r.l ? h('span', { text: r.l }) : null))];
  }
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
    function set(i, cx, cy) {
      idx = i;
      if (onHover) onHover(i);
      if (i < 0) { tipHide(); return; }
      const it = items[i];
      if (cx == null) { const r = svg.getBoundingClientRect(); cx = r.left + it.x; cy = r.top + it.y; }
      tipShow(it.tip(), cx, cy);
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
      if (e.key === 'ArrowRight' || e.key === 'ArrowDown') { e.preventDefault(); set(Math.min(n - 1, idx + 1)); }
      else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') { e.preventDefault(); set(Math.max(0, idx - 1)); }
      else if (e.key === 'Home') { e.preventDefault(); set(0); }
      else if (e.key === 'End') { e.preventDefault(); set(n - 1); }
      else if (e.key === 'Escape') set(-1);
      else if (e.key === 'Enter' && idx >= 0 && onActivate) onActivate(items[idx]);
    });
    svg.addEventListener('focus', () => { if (idx < 0 && svg.matches(':focus-visible')) set(0); });
    svg.addEventListener('blur', () => set(-1));
  }

  /* ---------- chart scaffolding ---------- */
  const charts = new Map();
  const widths = new Map();
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
  function frame(box, title, desc, interactive = true) {
    const W = Math.max(box.clientWidth, 200), H = box.clientHeight || 240;
    const svg = s('svg', { width: W, height: H, viewBox: `0 0 ${W} ${H}`, role: 'img' });
    s('title', { id: box.id + '-t', text: title }, svg);
    s('desc', { id: box.id + '-d', text: desc + (interactive ? ' Focus the chart and use the arrow keys to read values.' : '') }, svg);
    svg.setAttribute('aria-labelledby', box.id + '-t');
    svg.setAttribute('aria-describedby', box.id + '-d');
    box.replaceChildren(svg);
    return { svg, W, H };
  }
  function yAxis(g, y, ticks, fmt, x0, x1, base = true) {
    ticks.forEach((t, i) => {
      const yy = Math.round(y(t)) + 0.5;
      s('line', { class: i === 0 && base ? 'bl' : 'gl', x1: x0, x2: x1, y1: yy, y2: yy }, g);
      s('text', { class: 'tk', x: x0 - 6, y: yy + 3.5, 'text-anchor': 'end', text: fmt(t) }, g);
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
  function yLabel(g, text, x, y) { s('text', { class: 'al', transform: `translate(${x},${y}) rotate(-90)`, 'text-anchor': 'middle', text }, g); }
  function miniTable(cols, rows) {
    return h('table', { class: 'mini' },
      h('thead', null, h('tr', null, cols.map((c, i) => h('th', { scope: 'col', class: i ? 'n' : null, text: c })))),
      h('tbody', null, rows.map(r => h('tr', null, r.map((v, i) => h('td', { class: i ? 'n' : null, text: v }))))));
  }

  /* ---------- flow diagrams (pipeline + serving) ---------- */
  function flow(id, nodes, edges, minW) {
    const box = document.getElementById(id);
    const W = Math.max(box.clientWidth, 240);
    const n = nodes.length;
    let cols = W < 520 ? 1 : Math.max(1, Math.min(n, Math.floor((W + 34) / (minW + 34))));
    cols = Math.ceil(n / Math.ceil(n / cols));
    const gx = cols > 1 ? 34 : 0, gy = 34;
    const bw = (W - (cols - 1) * gx) / cols;
    const tc = Math.max(12, Math.floor((bw - 26) / 7.6)), lc = Math.max(14, Math.floor((bw - 26) / 6.4));
    const L = nodes.map(nd => ({ t: wrap(nd.t, tc), l: nd.l.flatMap(x => wrap(x, lc)) }));
    const rows = Math.ceil(n / cols), rowH = [], rowY = [];
    let yy = 1;
    for (let r = 0; r < rows; r++) {
      let mh = 0;
      for (let c = 0; c < cols; c++) { const k = r * cols + c; if (k < n) mh = Math.max(mh, 34 + L[k].t.length * 18 + L[k].l.length * 16 + 12); }
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
      s('text', { class: 'nn', x: p.x + 13, y: p.y + 20, text: nd.n }, g);
      let ty = p.y + 40;
      L[k].t.forEach(t => { s('text', { class: 'nt', x: p.x + 13, y: ty, text: t }, g); ty += 18; });
      ty += 2;
      L[k].l.forEach(t => { s('text', { class: 'nl', x: p.x + 13, y: ty, text: t }, g); ty += 16; });
    });
    box.replaceChildren(svg);
  }
  function pipelineNodes() {
    const hd = D ? D.headline : null;
    return [
      { n: 'STEP 1', t: 'Public checkpoints', l: [hd ? `${hd.policies_routed} routed of ${hd.policies_tested} tested` : 'ten routed policies', 'Comet π0.5, 2025 winner, specialists, ours'] },
      { n: 'STEP 2', t: 'Development rollouts', l: ['instances 311–320', hd ? `${fint(hd.dev_rollouts)} rollouts in the ledger` : 'development ledger'] },
      { n: 'STEP 3', t: 'Empirical-Bayes posterior', l: ['per (task, policy)', 'reference prior + own rollouts'] },
      { n: 'STEP 4', t: 'Strict switching rules', l: ['≥ 2 own rollouts', 'beats incumbent on ≥ 2 shared instances', 'gain ≥ 0.01 · veto', 'one checkpoint per family'], k: 'core' },
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
  let SEL = null;
  function selRead() {
    const v = k => +$('#s_' + k).value;
    const mu = v('mu'), sd = v('sd'), n = v('n'), xb = v('x'), sig = v('sig'), inc = v('inc');
    const prec = 1 / (sd * sd) + n / (sig * sig);
    const pm = (mu / (sd * sd) + (n * xb) / (sig * sig)) / prec;
    SEL = { mu, sd, n, xb, sig, inc, pm, psd: Math.sqrt(1 / prec), w: n / (sig * sig) / prec, gain: pm - inc };
  }
  function selUpdate() {
    selRead();
    const P = SEL;
    $('#o_mu').textContent = P.mu.toFixed(2); $('#o_sd').textContent = P.sd.toFixed(2);
    $('#o_n').textContent = P.n; $('#o_x').textContent = P.xb.toFixed(2);
    $('#o_sig').textContent = P.sig.toFixed(2); $('#o_inc').textContent = P.inc.toFixed(2);
    $('#s_x').disabled = P.n === 0;
    const stat = (v, l) => h('div', null, h('b', { text: v }), h('span', { text: l }));
    $('#selStats').replaceChildren(stat(f3(P.pm), 'posterior mean'), stat(f3(P.psd), 'posterior s.d.'), stat(sgn(P.gain), 'gain vs incumbent'));
    const wt = ` Own rollouts carry ${Math.round(P.w * 100)}% of the posterior weight.`;
    let lead, rest;
    if (P.n < 2) { lead = 'Keep the incumbent.'; rest = ` The challenger has ${P.n} own rollout${P.n === 1 ? '' : 's'}; the rules need at least 2.`; }
    else if (P.gain < 0.01) { lead = 'Keep the incumbent.'; rest = ` Posterior gain ${sgn(P.gain)} is below the 0.01 threshold.`; }
    else { lead = 'Switch allowed by these rules.'; rest = ` Gain ${sgn(P.gain)} ≥ 0.01 with ${P.n} own rollouts. The challenger must still win on at least 2 shared instances, pass the veto, and respect one checkpoint per family.`; }
    $('#selVerdict').replaceChildren(h('b', { text: lead }), rest + wt);
    const fn = charts.get('selChart'); if (fn) fn();
  }
  function selChart() {
    const box = $('#selChart'), P = SEL;
    const { svg, W, H } = frame(box, 'Prior and posterior for the challenger',
      `Prior mean ${f3(P.mu)}, s.d. ${f3(P.sd)}. Posterior mean ${f3(P.pm)}, s.d. ${f3(P.psd)}. Incumbent ${f3(P.inc)}.`);
    const m = { l: 8, r: 10, t: 18, b: 24 };
    const x = lin(-0.1, 1, m.l, W - m.r);
    const ymax = Math.max(pdf(P.mu, P.mu, P.sd), pdf(P.pm, P.pm, P.psd));
    const y = lin(0, ymax * 1.06, H - m.b, m.t);
    const g = s('g', null, svg);
    [0, 0.2, 0.4, 0.6, 0.8, 1].forEach(t => {
      s('line', { class: 'gl', x1: x(t), x2: x(t), y1: m.t, y2: H - m.b }, g);
      s('text', { class: 'tk', x: x(t), y: H - 7, 'text-anchor': 'middle', text: qt(t) }, g);
    });
    s('line', { class: 'bl', x1: m.l, x2: W - m.r, y1: H - m.b + 0.5, y2: H - m.b + 0.5 }, g);
    const xs = []; for (let i = 0; i <= 220; i++) xs.push(-0.1 + (1.1 * i) / 220);
    const curve = (mu, sd) => xs.map(v => [x(v), y(pdf(v, mu, sd))]);
    const pathOf = pts => 'M' + pts.map(p => p[0].toFixed(1) + ',' + p[1].toFixed(1)).join('L');
    const area = pts => pathOf(pts) + `L${x(1)},${y(0)}L${x(-0.1)},${y(0)}Z`;
    const pr = curve(P.mu, P.sd), po = curve(P.pm, P.psd);
    s('path', { d: area(pr), class: 'wash2' }, g); s('path', { d: pathOf(pr), class: 'ln2' }, g);
    s('path', { d: area(po), class: 'wash' }, g); s('path', { d: pathOf(po), class: 'ln' }, g);
    const xi = x(P.inc);
    s('line', { class: 'inc', x1: xi, x2: xi, y1: m.t - 4, y2: H - m.b }, g);
    s('text', { class: 'dl2', x: xi + (xi > W - 90 ? -5 : 5), y: m.t + 2, 'text-anchor': xi > W - 90 ? 'end' : 'start', text: 'incumbent' }, g);
    if (P.n > 0) { const xm = x(P.xb), yb = H - m.b; s('path', { class: 'ink-fill', d: `M${xm},${yb - 7}L${xm + 5},${yb}L${xm - 5},${yb}Z` }, g); }
    const cross = s('line', { class: 'gl', x1: 0, x2: 0, y1: m.t, y2: H - m.b, visibility: 'hidden', style: 'stroke:var(--ink-2)' }, g);
    const items = [];
    for (let v = 0; v <= 1.0001; v += 0.02) items.push({ x: x(v), y: m.t + 10, v, tip: () => tipContent(`q = ${f2(v)}`, [
      { v: pdf(v, P.pm, P.psd).toFixed(2), l: 'posterior density', c: 'var(--ink)' },
      { v: pdf(v, P.mu, P.sd).toFixed(2), l: 'prior density', c: 'var(--muted)' }]) });
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
    const total = D.tasks.reduce((a, t) => a + t.q, 0);
    const { svg, W } = frame(box, 'Task points contributed per policy',
      `Horizontal bars, one per routed policy, sorted by task points. Total ${total.toFixed(2)} task points across 100 tasks.`);
    const lw = narrow ? 0 : Math.min(230, W * 0.34), x0 = lw + (narrow ? 0 : 10), x1 = W - 46;
    const x = lin(0, Math.max(...ps.map(p => p.task_points)), x0, x1);
    const g = s('g', null, svg);
    const hb = s('rect', { class: 'hb', x: 0, width: W, height: rowH, visibility: 'hidden' }, g);
    const items = [];
    ps.forEach((p, i) => {
      const top = 4 + i * rowH, bh = narrow ? 12 : 14;
      const by = narrow ? top + 22 : top + (rowH - bh) / 2;
      s('text', { class: 'dl2', x: narrow ? 0 : lw, y: narrow ? top + 14 : by + bh / 2 + 4, 'text-anchor': narrow ? 'start' : 'end', text: p.display }, g);
      s('path', { class: 'bar', d: hbar(x0, by, Math.max(x(p.task_points), x0 + 2), bh), style: 'fill:' + pcol(p.policy) }, g);
      s('text', { class: 'dl', x: Math.max(x(p.task_points), x0 + 2) + 6, y: by + bh / 2 + 4, text: p.task_points.toFixed(2) }, g);
      items.push({ x: x(p.task_points), y: top + rowH / 2, p, tip: () => tipContent(p.display, [
        { v: p.task_points.toFixed(2), l: 'task points', c: pcol(p.policy), box: true },
        { v: String(p.tasks), l: 'tasks routed' },
        { v: f3(p.q_mean), l: 'realized mean q' },
        { v: f3(p.expected_mean), l: 'expected mean q' }]) });
    });
    s('line', { class: 'bl', x1: x0 + 0.5, x2: x0 + 0.5, y1: 2, y2: ps.length * rowH + 6 }, g);
    interact(svg, items, 'y', i => {
      if (i < 0) hb.setAttribute('visibility', 'hidden');
      else { hb.setAttribute('y', 4 + i * rowH); hb.setAttribute('visibility', 'visible'); }
    }, it => focusPolicy(it.p.policy));
    $('#pointsCap').textContent = `Task points are the sum of a policy's realized task means. Over all 100 tasks they total ${total.toFixed(2)}, which is 100 × Q. Activate a bar to filter the explorer to that policy.`;
  }
  function bankCards() {
    const ps = D.policies.slice().sort((a, b) => b.task_points - a.task_points);
    const stat = (v, l) => h('div', null, h('b', { text: v }), h('span', { text: l }));
    $('#bankCards').replaceChildren(...ps.map(p => {
      const hex = /^[0-9a-f]{40}$/i.test(p.revision);
      const src = p.source.includes('/')
        ? h('a', { href: 'https://huggingface.co/' + p.source, text: p.source })
        : h('span', { text: p.source });
      return h('article', { class: 'pc' },
        h('div', { class: 'pc-head' }, h('span', { class: 'sw', style: 'background:' + pcol(p.policy) }),
          h('div', null, h('h3', { text: p.display }), h('div', { class: 'pid', text: p.policy }))),
        h('div', { class: 'badges' }, h('span', { class: 'badge', text: FAMILY[p.family] || p.family }),
          p.kind === 'ours' ? h('span', { class: 'badge ours', text: 'ours' }) : null,
          OTHER.includes(p.policy) ? h('span', { class: 'badge', text: 'grey in charts' }) : null),
        h('div', { class: 'pc-stats' }, stat(String(p.tasks), 'tasks routed'), stat(f3(p.q_mean), 'realized q'),
          stat(f3(p.expected_mean), 'expected q'), stat(String(p.successes), 'successes')),
        h('div', { class: 'pc-src' }, 'Source: ', src, ' @ ', h('code', { text: hex ? p.revision.slice(0, 7) : p.revision }),
          p.subfolder ? [' / ', h('code', { text: p.subfolder })] : null, ` · replay ${p.replay}`),
        h('p', { text: p.lineage }),
        h('p', { class: 'lic', text: 'Licence: ' + p.license_status }),
        h('button', { class: 'linkbtn', type: 'button', onclick: () => focusPolicy(p.policy), text: `Show its ${p.tasks} task${p.tasks === 1 ? '' : 's'} in the explorer` }));
    }));
    $('#bankCards').style.minHeight = '0';
  }

  /* ---------- explorer ---------- */
  const st = { pol: new Set(), stage: 'all', scene: 'all', q: '', sort: 'q' };
  const SORTS = { q: ['realized q', t => -t.q], e: ['expected q', t => -t.expected], gap: ['gap (realized − expected)', t => t.q - t.expected], id: ['task id', t => t.id] };
  let CUR = [];
  function filtered() {
    const q = st.q.trim().toLowerCase();
    const key = SORTS[st.sort][1];
    return D.tasks.filter(t => (!st.pol.size || st.pol.has(t.policy))
      && (st.stage === 'all' || String(t.stage) === st.stage)
      && (st.scene === 'all' || t.scene === st.scene)
      && (!q || t._name.toLowerCase().includes(q) || String(t.id) === q))
      .sort((a, b) => key(a) - key(b) || a.id - b.id);
  }
  function buildFilters() {
    const ps = D.policies.slice().sort((a, b) => b.tasks - a.tasks || b.task_points - a.task_points);
    $('#fPolicies').replaceChildren(...ps.map(p => h('button', {
      class: 'chip', type: 'button', 'aria-pressed': 'false', 'data-p': p.policy,
      onclick: () => { st.pol.has(p.policy) ? st.pol.delete(p.policy) : st.pol.add(p.policy); syncChips(); renderExplorer(); },
      onpointerenter: () => emph(p.policy), onpointerleave: () => emph(null), onfocus: () => emph(p.policy), onblur: () => emph(null),
    }, h('span', { class: 'sw', style: 'background:' + pcol(p.policy) }), h('span', { text: p.display }), h('span', { class: 'ct', text: p.tasks }))));
    const sc = $('#fScene');
    Object.keys(D.scenes).sort().forEach(k => sc.append(h('option', { value: k, text: `${humanize(k)} (${D.scenes[k].tasks})` })));
    sc.addEventListener('change', () => { st.scene = sc.value; renderExplorer(); });
    $('#fSort').addEventListener('change', e => { st.sort = e.target.value; renderExplorer(); });
    let t = 0;
    $('#fSearch').addEventListener('input', e => { clearTimeout(t); t = setTimeout(() => { st.q = e.target.value; renderExplorer(); }, 120); });
    $$('.seg button').forEach(b => b.addEventListener('click', () => { st.stage = b.dataset.stage; syncSeg(); renderExplorer(); }));
    $('#fReset').addEventListener('click', () => {
      Object.assign(st, { stage: 'all', scene: 'all', q: '', sort: 'q' }); st.pol.clear();
      sc.value = 'all'; $('#fSort').value = 'q'; $('#fSearch').value = '';
      syncChips(); syncSeg(); renderExplorer();
    });
  }
  function syncChips() {
    $('#fPolicies').classList.toggle('sel', st.pol.size > 0);
    $$('#fPolicies .chip').forEach(c => c.setAttribute('aria-pressed', String(st.pol.has(c.dataset.p))));
  }
  function syncSeg() { $$('.seg button').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.stage === st.stage))); }
  function emph(pid) { $$('#stripChart .bar').forEach(b => b.classList.toggle('dim', !!pid && b.dataset.p !== pid)); }
  function focusPolicy(pid) {
    st.pol = new Set([pid]); syncChips(); renderExplorer();
    $('#results').scrollIntoView({ block: 'start' });
  }
  function renderExplorer() {
    CUR = filtered();
    const n = CUR.length;
    const mean = k => CUR.reduce((a, t) => a + t[k], 0) / (n || 1);
    $('#exSummary').textContent = n
      ? `Showing ${n} of ${D.tasks.length} tasks · mean realized q ${f3(mean('q'))} · mean expected q ${f3(mean('expected'))} · ${(k => `${k} full success${k === 1 ? '' : 'es'}`)(CUR.reduce((a, t) => a + t.successes, 0))}`
      : 'No tasks match these filters.';
    const fn = charts.get('stripChart'); if (fn) fn();
    renderTable();
  }
  function taskTip(t) {
    return tipContent(`#${t.id} ${t._name}`, [
      { v: f3(t.q), l: 'realized mean q', c: pcol(t.policy), box: true },
      { v: f3(t.expected), l: 'expected at freeze', c: 'var(--ink)' },
      { v: sgn(t.q - t.expected), l: 'gap' },
      { v: `${t.successes}/10`, l: 'full successes' },
      { v: pname(t.policy), l: `stage ${t.stage}` }]);
  }
  function stripChart() {
    const box = $('#stripChart'), rows = CUR;
    const { svg, W, H } = frame(box, 'Realized and expected q per task',
      `${rows.length} tasks sorted by ${SORTS[st.sort][0]}. Bars show realized mean q over instances 301–310, coloured by routed policy; ticks show expected q at freeze.`);
    const m = { l: 34, r: 6, t: 10, b: 26 };
    const pw = W - m.l - m.r, ph = H - m.t - m.b;
    const y = lin(0, 1, m.t + ph, m.t);
    const g = s('g', null, svg);
    yAxis(g, y, [0, 0.25, 0.5, 0.75, 1], qt, m.l, W - m.r);
    s('text', { class: 'al', x: m.l, y: H - 6, text: rows.length ? `${rows.length} task${rows.length === 1 ? '' : 's'}, sorted by ${SORTS[st.sort][0]}` : 'No tasks match these filters' }, g);
    if (!rows.length) return;
    const band = Math.min(pw / rows.length, 30);
    const bw = band >= 6 ? Math.min(24, band - 2) : Math.max(1, band * 0.72);
    const hb = s('rect', { class: 'hb', y: m.t, height: ph, width: band, visibility: 'hidden' }, g);
    const items = [], yb = y(0);
    rows.forEach((t, i) => {
      const x = m.l + i * band + (band - bw) / 2;
      const a = { class: 'bar', 'data-p': t.policy, style: 'fill:' + pcol(t.policy) };
      if (t.q > 0) s('path', Object.assign(a, { d: bw >= 6 ? vbar(x, y(t.q), yb, bw) : `M${x},${yb}V${y(t.q)}H${x + bw}V${yb}Z` }), g);
      else s('rect', Object.assign(a, { x, y: yb - 2, width: bw, height: 2 }), g);
      const tw = Math.max(bw + 4, band), cx = x + bw / 2, ye = Math.round(y(t.expected));
      s('line', { class: 'xt', x1: cx - tw / 2, x2: cx + tw / 2, y1: ye, y2: ye }, g);
      items.push({ x: cx, y: y(Math.max(t.q, t.expected)), t, tip: () => taskTip(t) });
    });
    interact(svg, items, 'x', i => {
      if (i < 0) hb.setAttribute('visibility', 'hidden');
      else { hb.setAttribute('x', m.l + i * band); hb.setAttribute('visibility', 'visible'); }
    }, it => openTask(it.t.id, true));
  }
  function heat(t) {
    return h('div', { class: 'heat', 'data-id': t.id, role: 'img', 'aria-label': 'Per-instance q, instances 301 to 310: ' + t.qs.map(f2).join(', ') },
      t.qs.map((v, i) => h('i', { 'data-i': i, style: `background:color-mix(in oklab, var(--heat1) ${Math.round(v * 100)}%, var(--heat0))` })));
  }
  function renderTable() {
    const frag = document.createDocumentFragment();
    if (!CUR.length) frag.append(h('tr', null, h('td', { colspan: 8, class: 'empty', text: 'No tasks match these filters.' })));
    CUR.forEach(t => frag.append(h('tr', { class: 'row', 'data-id': t.id },
      h('td', { class: 'c-id', text: t.id }),
      h('td', { class: 'c-task' }, h('button', { class: 'tbtn', type: 'button', 'aria-expanded': 'false', 'aria-controls': 'det-' + t.id, text: t._name })),
      h('td', { class: 'c-pol' }, h('span', { class: 'pol' }, h('span', { class: 'sw', style: 'background:' + pcol(t.policy) }), h('span', { class: 'nm', text: pname(t.policy) }))),
      h('td', { class: 'c-num c-st', 'data-label': 'Stage', text: t.stage }),
      h('td', { class: 'c-num c-ex', 'data-label': 'Expected', text: f3(t.expected) }),
      h('td', { class: 'c-num c-re', 'data-label': 'Realized', text: f3(t.q) }),
      h('td', { class: 'c-num c-su', 'data-label': 'Success', text: `${t.successes}/10` }),
      h('td', { class: 'c-heat' }, heat(t)))));
    $('#taskBody').replaceChildren(frag);
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
        h('dl', { class: 'facts' }, dt('Scene', humanize(t.scene)), dt('Mean demo length', `${t.demo_s} s`),
          dt('Routed policy', `${pname(t.policy)} · stage ${t.stage}`), dt('Fallback recorded at freeze', fb)),
        h('div', { class: 'iv' }, t.qs.map((v, i) => h('span', null, `${301 + i} `, h('b', { text: f2(v) }))))),
      h('div', null,
        h('div', { class: 'lbl', text: `Development evidence · ${totalN} rollout${totalN === 1 ? '' : 's'}` }),
        devs.length ? h('table', { class: 'mini' },
          h('thead', null, h('tr', null, h('th', { scope: 'col', text: 'Policy' }), h('th', { scope: 'col', class: 'n', text: 'n' }), h('th', { scope: 'col', class: 'n', text: 'mean q' }))),
          h('tbody', null, devs.map(([p, v]) => h('tr', { class: p === t.policy ? 'rt' : null },
            h('td', { class: 'pidc' }, h('span', { class: 'pcell' }, POL[p] ? h('span', { class: 'sw', style: 'background:' + pcol(p) }) : null, h('span', { text: p }),
              p === t.policy ? h('span', { class: 'tag', text: 'routed' }) : null,
              p === t.fallback && p !== t.policy ? h('span', { class: 'tag', text: 'fallback' }) : null)),
            h('td', { class: 'n', text: v.n }), h('td', { class: 'n', text: f3(v.mean) }))))) : null,
        t.dev[t.policy] ? null : h('p', { class: 'mini-note', text: 'The routed policy has no development rollouts on this task.' })))));
  }
  function toggleTask(id, force) {
    const tr = $(`#taskBody tr.row[data-id="${id}"]`);
    if (!tr) return null;
    const btn = $('.tbtn', tr), open = btn.getAttribute('aria-expanded') === 'true';
    const want = force == null ? !open : force;
    if (want === open) return tr;
    btn.setAttribute('aria-expanded', String(want));
    tr.classList.toggle('open', want);
    if (want) tr.after(detailRow(TASK[id])); else { const d = $('#det-' + id); if (d) d.remove(); }
    return tr;
  }
  function openTask(id) {
    const tr = toggleTask(id, true);
    if (tr) { tr.scrollIntoView({ block: 'center' }); $('.tbtn', tr).focus({ preventScroll: true }); }
  }
  function tableEvents() {
    const body = $('#taskBody');
    body.addEventListener('click', e => { if (e.target.closest('a')) return; const tr = e.target.closest('tr.row'); if (tr) toggleTask(+tr.dataset.id); });
    body.addEventListener('pointerover', e => {
      const c = e.target.closest('.heat i'); if (!c || e.pointerType === 'touch') return;
      const t = TASK[+c.parentNode.dataset.id], i = +c.dataset.i;
      tipShow(tipContent(`#${t.id} ${t._name}`, [{ v: f3(t.qs[i]), l: `q on instance ${301 + i}` }]), e.clientX, e.clientY);
    });
    body.addEventListener('pointerout', e => { if (e.target.closest('.heat i')) tipHide(); });
  }

  /* ---------- analysis charts ---------- */
  function calChart() {
    const box = $('#calChart'), T = D.tasks, C = D.calibration;
    const { svg, W, H } = frame(box, 'Expected versus realized q per task',
      `Scatter of ${T.length} tasks: x is expected q at freeze, y is realized mean q. Spearman ${f2(C.spearman)}, Pearson ${f2(C.pearson)}.`);
    const m = { l: 46, r: 10, t: 10, b: 40 };
    const top = Math.min(1, Math.ceil(Math.max(...T.map(t => Math.max(t.q, t.expected))) * 10) / 10);
    const x = lin(0, top, m.l, W - m.r), y = lin(0, top, H - m.b, m.t);
    const g = s('g', null, svg), ticks = niceTicks(top, top > 0.6 ? 5 : 4).filter(v => v <= top + 1e-9);
    yAxis(g, y, ticks, qt, m.l, W - m.r);
    ticks.forEach(t => { if (t) s('text', { class: 'tk', x: x(t), y: H - m.b + 16, 'text-anchor': 'middle', text: qt(t) }, g); });
    s('line', { class: 'bl', x1: m.l + 0.5, x2: m.l + 0.5, y1: m.t, y2: H - m.b }, g);
    s('line', { class: 'ref', x1: x(0), y1: y(0), x2: x(top), y2: y(top) }, g);
    s('text', { class: 'dl2', x: x(top) - 4, y: y(top) + 14, 'text-anchor': 'end', text: 'y = x' }, g);
    s('text', { class: 'al', x: (m.l + W - m.r) / 2, y: H - 6, 'text-anchor': 'middle', text: 'Expected q at freeze' }, g);
    yLabel(g, 'Realized mean q, 301–310', 12, (m.t + H - m.b) / 2);
    const ring = s('circle', { r: 8, class: 'hl', fill: 'none', visibility: 'hidden' }, g);
    const order = T.slice().sort((a, b) => b.stage - a.stage);
    order.forEach(t => s('circle', { cx: x(t.expected), cy: y(t.q), r: 4.5, class: t.stage === 1 ? 'dot1' : 'dot2' }, g));
    const items = order.map(t => ({ x: x(t.expected), y: y(t.q), t, tip: () => {
      const same = T.filter(o => o !== t && o.expected === t.expected && o.q === t.q).length;
      const nodes = taskTip(t);
      if (same) nodes.push(h('div', { class: 'tr' }, h('span', { text: `and ${same} other task${same === 1 ? '' : 's'} at this point` })));
      return nodes;
    } }));
    interact(svg, items, 'xy', i => {
      if (i < 0) ring.setAttribute('visibility', 'hidden');
      else { ring.setAttribute('cx', items[i].x); ring.setAttribute('cy', items[i].y); ring.setAttribute('visibility', 'visible'); }
    }, it => openTask(it.t.id));
  }
  function columns(id, labels, values, emphIdx, title, desc, yName, tipFn) {
    const box = document.getElementById(id);
    const { svg, W, H } = frame(box, title, desc);
    const m = { l: 46, r: 8, t: 22, b: 38 };
    const ticks = niceTicks(Math.max(...values), 4);
    const y = lin(0, ticks[ticks.length - 1], H - m.b, m.t);
    const g = s('g', null, svg);
    yAxis(g, y, ticks, fint, m.l, W - m.r);
    yLabel(g, yName, 12, (m.t + H - m.b) / 2);
    const band = (W - m.l - m.r) / values.length, bw = Math.min(24, band - 2);
    const hb = s('rect', { class: 'hb', y: m.t, height: H - m.t - m.b, width: band, visibility: 'hidden' }, g);
    const items = [];
    values.forEach((v, i) => {
      const x = m.l + i * band + (band - bw) / 2;
      s('path', { d: vbar(x, y(v), y(0), bw), class: 'bar ' + (i === emphIdx ? 'ink-fill' : 'ink2-fill') }, g);
      if (labels[i] != null) s('text', { class: 'tk', x: x + bw / 2, y: H - m.b + 15, 'text-anchor': 'middle', text: labels[i] }, g);
      items.push({ x: x + bw / 2, y: y(v), tip: () => tipFn(i) });
    });
    if (emphIdx >= 0) {
      const x = m.l + emphIdx * band + band / 2;
      s('text', { class: 'dl', x: Math.min(x, W - 30), y: y(values[emphIdx]) - 6, 'text-anchor': 'middle', text: fint(values[emphIdx]) }, g);
    }
    interact(svg, items, 'x', i => {
      if (i < 0) hb.setAttribute('visibility', 'hidden');
      else { hb.setAttribute('x', m.l + i * band); hb.setAttribute('visibility', 'visible'); }
    });
    return { g, m, W, H };
  }
  function histChart() {
    const hs = D.histogram, total = hs.reduce((a, b) => a + b, 0);
    const lab = i => `[${(i / 10).toFixed(1)}, ${i === 9 ? '1.0]' : ((i + 1) / 10).toFixed(1) + ')'}`;
    const narrow = $('#histChart').clientWidth < 380;
    const r = columns('histChart', hs.map((_, i) => (narrow && i % 2 ? null : (i / 10).toFixed(1))), hs, 0,
      'Distribution of episode q', `Histogram of ${fint(total)} episodes in ten bins of width 0.1. ${fint(hs[0])} fall in the lowest bin.`, 'Episodes',
      i => tipContent(`q in ${lab(i)}`, [{ v: fint(hs[i]), l: 'episodes' }, { v: ((hs[i] / total) * 100).toFixed(1) + '%', l: 'of all episodes' }]));
    s('text', { class: 'al', x: (r.m.l + r.W - r.m.r) / 2, y: r.H - 4, 'text-anchor': 'middle', text: 'Episode q (bin start)' }, r.g);
  }
  function devChart() {
    const ks = Object.keys(D.dev_instances).sort(), vs = ks.map(k => D.dev_instances[k]);
    const total = vs.reduce((a, b) => a + b, 0), ei = ks.indexOf('313');
    const r = columns('devChart', ks, vs, ei, 'Development rollouts per instance',
      `Columns for development instances ${ks[0]} to ${ks[ks.length - 1]}. Instance 313 has ${fint(vs[ei])} of ${fint(total)} rollouts.`, 'Rollouts',
      i => tipContent(`Instance ${ks[i]}`, [{ v: fint(vs[i]), l: 'rollouts' }, { v: ((vs[i] / total) * 100).toFixed(1) + '%', l: 'of the ledger' }]));
    s('text', { class: 'al', x: (r.m.l + r.W - r.m.r) / 2, y: r.H - 4, 'text-anchor': 'middle', text: 'Development instance' }, r.g);
  }
  function powChart() {
    const box = $('#powChart'), es = Object.keys(D.power).sort((a, b) => a - b), ns = es.map(k => D.power[k]);
    const sd = D.headline.within_task_sd;
    const { svg, W, H } = frame(box, 'Rollouts per policy needed versus effect size',
      `Log-log line: ${es.map((e, i) => `${e} needs ${fint(ns[i])}`).join('; ')}, at rollout s.d. ${f2(sd)}.`);
    const m = { l: 58, r: 22, t: 14, b: 40 };
    const x = logS(+es[0] * 0.8, +es[es.length - 1] * 1.25, m.l, W - m.r), y = logS(8, 2500, H - m.b, m.t);
    const g = s('g', null, svg);
    [10, 30, 100, 300, 1000].forEach(t => {
      const yy = Math.round(y(t)) + 0.5;
      s('line', { class: 'gl', x1: m.l, x2: W - m.r, y1: yy, y2: yy }, g);
      s('text', { class: 'tk', x: m.l - 6, y: yy + 3.5, 'text-anchor': 'end', text: fint(t) }, g);
    });
    s('line', { class: 'bl', x1: m.l, x2: W - m.r, y1: H - m.b + 0.5, y2: H - m.b + 0.5 }, g);
    es.forEach(e => s('text', { class: 'tk', x: x(+e), y: H - m.b + 15, 'text-anchor': 'middle', text: (+e).toFixed(2) }, g));
    s('line', { class: 'ref', x1: m.l, x2: W - m.r, y1: y(10), y2: y(10) }, g);
    s('text', { class: 'dl2', x: m.l + 6, y: y(10) - 6, text: '10 development instances per task' }, g);
    s('text', { class: 'al', x: (m.l + W - m.r) / 2, y: H - 4, 'text-anchor': 'middle', text: 'Difference in mean q to detect' }, g);
    yLabel(g, 'Rollouts per policy (log)', 12, (m.t + H - m.b) / 2);
    s('path', { class: 'ln', d: 'M' + es.map((e, i) => `${x(+e)},${y(ns[i])}`).join('L') }, g);
    const items = es.map((e, i) => {
      s('circle', { class: 'dot2', cx: x(+e), cy: y(ns[i]), r: 4.5 }, g);
      s('text', { class: 'dl', x: x(+e) + 8, y: y(ns[i]) - 7, text: fint(ns[i]) }, g);
      return { x: x(+e), y: y(ns[i]), tip: () => tipContent(`Effect size ${(+e).toFixed(2)}`, [{ v: fint(ns[i]), l: 'rollouts per policy' }]) };
    });
    interact(svg, items, 'x');
  }
  function stageChart() {
    const box = $('#stageChart'), S = D.stages, ks = Object.keys(S).sort();
    const { svg, W, H } = frame(box, 'Expected and realized mean q by stage',
      ks.map(k => `Stage ${k}: ${S[k].tasks} tasks, expected ${f3(S[k].expected_mean)}, realized ${f3(S[k].q_mean)}`).join('. ') + '.');
    const narrow = W < 520, lw = narrow ? 0 : 130, m = { l: lw + (narrow ? 0 : 12), r: 16, t: 4, b: 22 };
    const max = Math.ceil(Math.max(...ks.map(k => Math.max(S[k].expected_mean, S[k].q_mean))) * 20) / 20 + 0.05;
    const x = lin(0, max, m.l, W - m.r), g = s('g', null, svg);
    niceTicks(max, 4).filter(v => v <= max).forEach(t => {
      s('line', { class: 'gl', x1: x(t), x2: x(t), y1: m.t, y2: H - m.b }, g);
      s('text', { class: 'tk', x: x(t), y: H - 6, 'text-anchor': 'middle', text: qt(t) }, g);
    });
    s('line', { class: 'bl', x1: m.l + 0.5, x2: m.l + 0.5, y1: m.t, y2: H - m.b }, g);
    const rh = (H - m.t - m.b) / ks.length, items = [];
    ks.forEach((k, i) => {
      const st0 = S[k], top = m.t + i * rh, bh = narrow ? 12 : 14, by = top + (narrow ? 18 : (rh - bh) / 2);
      s('text', { class: 'dl2', x: narrow ? 0 : lw, y: narrow ? top + 12 : by + 11, 'text-anchor': narrow ? 'start' : 'end', text: `Stage ${k} · ${st0.tasks} tasks` }, g);
      s('path', { class: 'bar ink2-fill', d: hbar(m.l, by, x(st0.q_mean), bh) }, g);
      const xe = Math.round(x(st0.expected_mean)) + 0.5;
      s('line', { class: 'xt', x1: xe, x2: xe, y1: by - 4, y2: by + bh + 4 }, g);
      s('text', { class: 'dl', x: narrow ? 0 : Math.max(x(st0.q_mean), xe) + 8, y: narrow ? top + 46 : by + 11, text: `${f3(st0.q_mean)} realized · ${f3(st0.expected_mean)} expected` }, g);
      items.push({ x: x(st0.q_mean), y: by + bh / 2, tip: () => tipContent(`Stage ${k}`, [
        { v: f3(st0.q_mean), l: 'realized mean q', c: 'var(--muted)', box: true }, { v: f3(st0.expected_mean), l: 'expected mean q', c: 'var(--ink)' },
        { v: String(st0.tasks), l: 'tasks' }, { v: st0.task_points.toFixed(2), l: 'task points' }]) });
    });
    interact(svg, items, 'y');
  }

  /* ---------- page wiring ---------- */
  function bindNumbers() {
    $$('[data-bind]').forEach(e => {
      const v = get(D, e.dataset.bind); if (v == null) return;
      const f = e.dataset.fmt;
      e.textContent = f === 'int' ? fint(v) : f === 'q3' ? f3(v) : String(v);
    });
  }
  function captions() {
    const C = D.calibration, H = D.headline, hs = D.histogram, total = hs.reduce((a, b) => a + b, 0);
    $('#calCap').textContent = `Spearman ${f2(C.spearman)}, Pearson ${f2(C.pearson)}. Mean expected q ${f3(C.mean_expected)} versus mean realized ${f3(C.mean_realized)}: development estimates were optimistic by ${f2(C.mean_expected - C.mean_realized)} on average. Points below the diagonal did worse than expected.`;
    $('#histCap').textContent = `${fint(hs[0])} of ${fint(total)} episodes score below 0.1, and ${fint(H.episodes - H.episodes_nonzero)} score exactly zero. ${fint(hs[9])} reach 0.9 or more; ${fint(H.successes)} are full successes.`;
    const dv = D.dev_instances, dt = Object.values(dv).reduce((a, b) => a + b, 0);
    $('#devCap').textContent = `${(D.share_313 * 100).toFixed(1)}% of the ${fint(dt)} development rollouts ran on instance 313, so development estimates lean heavily on a single instance.`;
    const p05 = D.power['0.05'];
    $('#powCap').textContent = `With rollout noise of s.d. ${f2(H.within_task_sd)} within a task, telling apart two policies that differ by 0.05 takes about ${fint(p05)} rollouts each. The development split has 10 instances per task.`;
    $('#histTable').replaceChildren(miniTable(['q bin', 'Episodes'], hs.map((v, i) => [`${(i / 10).toFixed(1)}–${((i + 1) / 10).toFixed(1)}`, fint(v)])));
    $('#devTable').replaceChildren(miniTable(['Instance', 'Rollouts'], Object.keys(dv).sort().map(k => [k, fint(dv[k])])));
    $('#powTable').replaceChildren(miniTable(['Effect size', 'Rollouts per policy'], Object.keys(D.power).sort((a, b) => a - b).map(k => [k, fint(D.power[k])])));
    $('#stageTable').replaceChildren(miniTable(['Stage', 'Tasks', 'Expected mean', 'Realized mean', 'Task points'],
      Object.keys(D.stages).sort().map(k => { const S = D.stages[k]; return [`Stage ${k}`, String(S.tasks), f3(S.expected_mean), f3(S.q_mean), S.task_points.toFixed(2)]; })));
    const R = D.reproduction;
    if (R) {
      const dis = R.disagreements.map(d => `task ${d.task_id} (${TASK[d.task_id] ? TASK[d.task_id]._name.toLowerCase() : ''}: ${pname(d.ours)} at ${f3(d.posterior_ours)} vs. frozen ${pname(d.frozen)} at ${f3(d.posterior_frozen)})`);
      $('#repro').textContent = `A clean reimplementation of the selector, run on ${fint(R.dev_rollouts_used)} development rollouts, reproduces ${R.agree} of ${R.tasks} stage-2 decisions.` + (dis.length ? ` It disagrees on ${dis.join(' and ')}.` : '');
    }
    // legends
    const leg = (el, items) => $(el).replaceChildren(...items.map(([sw, t]) => h('span', null, sw, t)));
    leg('#stripLegend', [[h('span', { class: 'sw', style: 'background:var(--ink-2)' }), 'bar: realized mean q, coloured by policy (chips above)'],
      [h('span', { class: 'sw-tick' }), 'tick: expected q at freeze'],
      ...(OTHER.length ? [[h('span', { class: 'sw', style: 'background:var(--c-other)' }), `grey: ${OTHER.map(pname).join(', ')}`]] : [])]);
    const n1 = D.tasks.filter(t => t.stage === 1).length;
    leg('#calLegend', [[h('span', { class: 'sw-ring' }), `stage 1 (${n1} tasks)`], [h('span', { class: 'sw-dot' }), `stage 2 (${D.tasks.length - n1} tasks)`],
      [h('span', { class: 'sw-line', style: 'background:var(--axis)' }), 'y = x']]);
  }
  function fail(err) {
    const msg = 'The results data (data/results.json) could not be loaded, so the figures and the explorer are unavailable. If you opened this file directly from disk, serve the folder over HTTP instead.';
    const el = $('#loadError'); el.textContent = msg; el.hidden = false;
    ['pointsChart', 'stripChart', 'calChart', 'histChart', 'devChart', 'powChart', 'stageChart'].forEach(id => {
      const b = document.getElementById(id); b.style.height = 'auto';
      b.replaceChildren(h('p', { class: 'empty', text: 'Figure unavailable: the results data did not load.' }));
    });
    $('#bankCards').replaceChildren(); $('#bankCards').style.minHeight = '0';
    $('#taskBody').replaceChildren(h('tr', null, h('td', { colspan: 8, class: 'empty', text: 'Table unavailable: the results data did not load.' })));
    if (window.console) console.warn('results.json failed to load:', err);
  }
  function start(data) {
    D = data;
    D.tasks.forEach(t => { t._name = humanize(t.name); TASK[t.id] = t; });
    D.policies.forEach(p => { POL[p.policy] = p; });
    const order = D.policies.slice().sort((a, b) => b.tasks - a.tasks || b.task_points - a.task_points);
    order.forEach((p, i) => { COLOR[p.policy] = i < 8 ? `var(--c${i + 1})` : 'var(--c-other)'; });
    OTHER = order.slice(8).map(p => p.policy);
    bindNumbers();
    charts.get('pipeline')();
    captions();
    reg('pointsChart', pointsChart);
    bankCards();
    buildFilters();
    tableEvents();
    CUR = filtered();
    reg('stripChart', stripChart);
    renderExplorer();
    reg('calChart', calChart);
    reg('histChart', histChart);
    reg('devChart', devChart);
    reg('powChart', powChart);
    reg('stageChart', stageChart);
  }

  function themeInit() {
    const btn = $('#themeBtn'), root = document.documentElement;
    const eff = () => root.getAttribute('data-theme') || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
    const label = () => btn.setAttribute('aria-label', `Switch to ${eff() === 'dark' ? 'light' : 'dark'} theme`);
    btn.addEventListener('click', () => {
      const n = eff() === 'dark' ? 'light' : 'dark';
      root.setAttribute('data-theme', n);
      try { localStorage.setItem('pb-theme', n); } catch (e) { /* storage unavailable */ }
      label();
    });
    label();
  }
  function copyInit() {
    const btn = $('#copyBib');
    btn.addEventListener('click', () => {
      const text = $('#bibtex').textContent;
      const done = ok => { btn.textContent = ok ? 'Copied' : 'Select and copy'; setTimeout(() => { btn.textContent = 'Copy'; }, 1800); };
      const legacy = () => {
        const r = document.createRange(); r.selectNodeContents($('#bibtex'));
        const sel = getSelection(); sel.removeAllRanges(); sel.addRange(r);
        let ok = false; try { ok = document.execCommand('copy'); } catch (e) { ok = false; }
        done(ok);
      };
      if (navigator.clipboard && window.isSecureContext) navigator.clipboard.writeText(text).then(() => done(true), legacy); else legacy();
    });
  }
  function navInit() {
    if (!('IntersectionObserver' in window)) return;
    const links = new Map($$('.nav a').map(a => [a.getAttribute('href').slice(1), a]));
    const io = new IntersectionObserver(es => es.forEach(e => {
      if (e.isIntersecting) links.forEach((a, id) => a.classList.toggle('on', id === e.target.id));
    }), { rootMargin: '-45% 0px -50% 0px' });
    links.forEach((_, id) => { const sec = document.getElementById(id); if (sec) io.observe(sec); });
  }

  function init() {
    themeInit(); copyInit(); navInit();
    reg('pipeline', () => flow('pipeline', pipelineNodes(), ['uni', 'uni', 'uni', 'uni', 'uni', 'uni'], 150));
    reg('servingDiagram', () => flow('servingDiagram', servingNodes, ['bi', 'bi', 'uni'], 150));
    $$('#selForm input').forEach(i => i.addEventListener('input', selUpdate));
    selRead();
    reg('selChart', selChart);
    selUpdate();
    const leg = $('#selLegend');
    leg.replaceChildren(
      h('span', null, h('span', { class: 'sw-line', style: 'background:var(--muted)' }), 'prior'),
      h('span', null, h('span', { class: 'sw-line', style: 'background:var(--ink)' }), 'posterior'),
      h('span', null, h('span', { class: 'sw-line', style: 'background:var(--ink-2);width:2px;height:12px' }), 'incumbent'),
      h('span', null, h('span', { class: 'sw-line', style: 'background:none;width:0;height:0;border-left:5px solid transparent;border-right:5px solid transparent;border-bottom:7px solid var(--ink)' }), 'mean of own rollouts'));
    fetch('data/results.json', { cache: 'no-cache' })
      .then(r => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
      .then(start, fail);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
