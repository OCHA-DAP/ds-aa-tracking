/* Minimal dependency-free Sankey + horizontal-bar renderer (inline SVG strings).
   Shared by the landing map sidebar and the dashboard pages; no CDN, no build step.

   sankeySVG({columns, links, width, height, fmt, color, nodePad, labelW})
     columns: [[{id, label}], ...]  left -> right; a node's value is max(inflow, outflow)
     links:   [{s, t, v}]           s/t are node ids in adjacent (or later) columns
     fmt(v)   value formatter for tooltips; color(node, colIndex) -> fill
   Returns an <svg> string; each band and node carries a <title> tooltip.

   hbarsSVG(rows, {width, fmt, color, max})
     rows: [{label, v}] sorted by caller; bars scaled to max (default: largest v). */
(function(g){
  const esc = s => String(s == null ? '' : s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  const PAL = ['#2a78d6','#eb6834','#1baf7a','#eda100','#e87ba4','#008300','#7a5cc4','#0f9ab8','#b0413e','#6b7a8f'];
  const NEUTRAL = '#94a3b8';
  // agencies keep one colour on every chart
  const AGENCY = {WFP:'#e8a33d', FAO:'#3aa35b', UNICEF:'#1ca0d4', WHO:'#7a5cc4', UNFPA:'#e0679a', UNHCR:'#2f6fb0',
    IOM:'#0f8a8a', UNDP:'#b0413e', 'UN WOMEN':'#9b59b6', OCHA:'#4b6584', UNOPS:'#8d6e63', UNAIDS:'#c2185b', UNHABITAT:'#607d8b', PAHO:'#7cb342'};
  const CBPF_SHADES = ['#eb6834','#d9534f','#f08c3a','#c0392b','#f4a259','#a84a1f','#e2703a','#cf6a4c','#b5542c','#f39c6b','#dd4b39','#e67e22'];
  const RHPF_SHADES = ['#1baf7a','#138a60','#4cc79a','#0e6b4b','#2ecc8f','#6fd6ae'];
  const hash = str => { let h = 0; for (const ch of String(str)) h = (h * 31 + ch.charCodeAt(0)) >>> 0; return h; };
  function sankeyColor(id, label){
    const [pre, ...rest] = String(id).split(':'), key = rest.join(':');
    if (pre === 'f') {
      if (key === 'cerf') return '#2a78d6';
      if (key.startsWith('rhpf')) return RHPF_SHADES[hash(key) % RHPF_SHADES.length];
      return CBPF_SHADES[hash(key) % CBPF_SHADES.length];
    }
    if (pre === 'a') {
      const u = String(label || key).toUpperCase().replace(/\s+/g, ' ').trim();
      if (AGENCY[u]) return AGENCY[u];
      if (/GRANTEE|PARTNER|NOT RECORDED/.test(u)) return NEUTRAL;
      return PAL[hash(u) % PAL.length];
    }
    return null;   // donors, sectors, partner types: neutral
  }
  function sankeySVG(o){
    const cols = o.columns.filter(c => c && c.length), links = (o.links||[]).filter(l => l.v > 0);
    const W = o.width || 360, fmt = o.fmt || (v => v), pad = o.nodePad == null ? 6 : o.nodePad;
    const nodeW = 9, labelW = o.labelW == null ? Math.min(120, W * 0.3) : o.labelW;
    const col = {}, byId = {};
    cols.forEach((c, i) => c.forEach(n => { col[n.id] = i; byId[n.id] = n; n.in = 0; n.out = 0; }));
    const L = links.filter(l => byId[l.s] && byId[l.t] && col[l.t] > col[l.s]);
    L.forEach(l => { byId[l.s].out += l.v; byId[l.t].in += l.v; });
    cols.forEach(c => c.forEach(n => n.v = Math.max(n.in, n.out)));
    cols.forEach(c => c.sort((a, b) => b.v - a.v));
    const kept = cols.map(c => c.filter(n => n.v > 0));
    const maxN = Math.max(...kept.map(c => c.length), 1);
    const H = o.height || Math.max(120, maxN * 22 + 20);
    const tot = Math.max(...kept.map(c => c.reduce((s, n) => s + n.v, 0)), 1e-9);
    const minH = o.minNode == null ? 11 : o.minNode;   // small nodes still get room for their label
    const k = Math.max(1e-9, (H - 10 - pad * (maxN - 1) - minH * maxN) / tot);
    const nc = kept.length, x0 = labelW, x1 = W - labelW - nodeW;
    const xs = kept.map((_, i) => nc === 1 ? x0 : x0 + (x1 - x0) * i / (nc - 1));
    kept.forEach((c, i) => {
      const used = c.reduce((s, n) => s + Math.max(minH, n.v * k), 0) + pad * (c.length - 1);
      let y = 5 + Math.max(0, (H - 10 - used) / 2);
      c.forEach(n => { n.x = xs[i]; n.y = y; n.h = Math.max(minH, n.v * k); const off = (n.h - n.v * k) / 2; n.sy = y + off; n.ty = y + off; y += n.h + pad; });
    });
    // every node: its fund / agency colour, else neutral. A link takes its source's colour,
    // or its target's when the source is neutral (donor -> fund bands in the fund's colour)
    kept.forEach(c => c.forEach(n => { n.fill = n.color || (o.nodeColor && o.nodeColor(n)) || sankeyColor(n.id, n.label); }));
    L.sort((a, b) => (byId[a.s].y - byId[b.s].y) || (byId[a.t].y - byId[b.t].y));
    let out = `<svg class='sk' viewBox='0 0 ${W} ${H}' width='100%' role='img' aria-label='${esc(o.label || 'flow diagram')}' style='display:block;font:11px system-ui,sans-serif'>`;
    L.forEach(l => {
      const s = byId[l.s], t = byId[l.t], h = l.v * k; if (s.h === undefined || t.h === undefined) return;
      const xa = s.x + nodeW, xb = t.x, ya = s.sy + h / 2, yb = t.ty + h / 2; s.sy += h; t.ty += h;
      const mx = (xa + xb) / 2, c = l.color || s.fill || t.fill || NEUTRAL;
      out += `<path class='sk-l' data-s='${esc(l.s)}' data-t='${esc(l.t)}' data-tip='${esc(s.label)} → ${esc(t.label)}: ${esc(fmt(l.v))}' d='M${xa},${ya}C${mx},${ya} ${mx},${yb} ${xb},${yb}' fill='none' stroke='${c}' stroke-opacity='.35' stroke-width='${Math.max(1, h)}'></path>`;
    });
    kept.forEach((c, i) => c.forEach(n => {
      const fill = n.fill || '#64748b';
      const tip = `${n.label}: ${fmt(n.v)}` + (n.in && n.out && Math.abs(n.in - n.out) > 1 ? ` (in ${fmt(n.in)}, out ${fmt(n.out)})` : '') + ' · click to focus';
      out += `<rect class='sk-n' data-id='${esc(n.id)}' data-tip='${esc(tip)}' x='${n.x - 2}' y='${n.y}' width='${nodeW + 4}' height='${n.h}' rx='2' fill='${fill}' stroke='#fff' stroke-width='2'></rect>`;
      const lx = i === nc - 1 ? n.x + nodeW + 4 : (i === 0 ? n.x - 4 : n.x + nodeW + 4);
      const anchor = i === 0 ? 'end' : 'start';
      if (n.h >= 7 || c.length <= 8) out += `<text class='sk-t' data-id='${esc(n.id)}' x='${lx}' y='${n.y + n.h / 2 + 3.5}' text-anchor='${anchor}' fill='#334155' stroke='#fff' stroke-width='3' stroke-linejoin='round' paint-order='stroke'>${esc(String(n.label).length > 22 ? String(n.label).slice(0, 21) + '…' : String(n.label))}</text>`;
    }));
    return out + `</svg>`;
  }
  function hbarsSVG(rows, o = {}){
    const W = o.width || 360, fmt = o.fmt || (v => v), lw = o.labelW || 118, vw = 52, rh = 18;
    const max = o.max || Math.max(...rows.map(r => r.v), 1e-9), H = rows.length * rh + 2;
    let out = `<svg viewBox='0 0 ${W} ${H}' width='100%' role='img' aria-label='${esc(o.label || 'bar chart')}' style='display:block;font:11px system-ui,sans-serif'>`;
    rows.forEach((r, i) => {
      const y = i * rh + 1, bw = Math.max(1, (W - lw - vw - 8) * r.v / max), c = r.color || (o.colorBy ? sankeyColor(o.colorBy + ':' + r.label, r.label) : null) || o.color || '#2a78d6';
      const lab = String(r.label).length > 20 ? String(r.label).slice(0, 19) + '…' : String(r.label);
      out += `<text x='${lw - 6}' y='${y + 12}' text-anchor='end' fill='#334155'>${esc(lab)}<title>${esc(r.label)}</title></text>`
        + `<rect x='${lw}' y='${y + 3}' width='${bw}' height='${rh - 7}' rx='3' fill='${c}'><title>${esc(r.label)}: ${esc(fmt(r.v))}</title></rect>`
        + `<text x='${lw + bw + 5}' y='${y + 12}' fill='#475569'>${esc(fmt(r.v))}</text>`;
    });
    return out + `</svg>`;
  }
  // hover a band: that flow; hover a node: everything upstream and downstream of it;
  // click a node: keep that focus (click again, or on empty space, to clear)
  function install(){
    if (typeof document === 'undefined' || g.__skInstalled) return; g.__skInstalled = true;
    const st = document.createElement('style');
    st.textContent = `.sk .sk-l{transition:stroke-opacity .12s;cursor:pointer}.sk .sk-n{cursor:pointer}.sk text{pointer-events:none;transition:opacity .12s}
      .sk.sk-f .sk-l{stroke-opacity:.07}.sk.sk-f .sk-l.on{stroke-opacity:.65}.sk.sk-f .sk-n:not(.on){opacity:.3}.sk.sk-f .sk-t:not(.on){opacity:.35}
      .sk-tip{position:fixed;z-index:9999;pointer-events:none;background:#0f2540;color:#fff;font:12px system-ui,sans-serif;padding:5px 8px;border-radius:5px;max-width:320px;box-shadow:0 4px 14px rgba(0,0,0,.25)}`;
    document.head.appendChild(st);
    const tip = document.createElement('div'); tip.className = 'sk-tip'; tip.hidden = true; document.body.appendChild(tip);
    const svgOf = el => el && el.closest && el.closest('svg.sk');
    function clear(svg){ svg.classList.remove('sk-f'); svg.querySelectorAll('.on').forEach(e => e.classList.remove('on')); }
    function focusNode(svg, id){
      clear(svg); const links = [...svg.querySelectorAll('.sk-l')];
      const on = new Set([id]);
      const walk = dir => { const q = [id], seen = new Set([id]);
        while (q.length) { const x = q.shift();
          links.forEach(l => { const a = dir > 0 ? l.dataset.s : l.dataset.t, b = dir > 0 ? l.dataset.t : l.dataset.s;
            if (a === x) { l.classList.add('on'); on.add(b); if (!seen.has(b)) { seen.add(b); q.push(b); } } }); } };
      walk(1); walk(-1);
      svg.querySelectorAll('.sk-n,.sk-t').forEach(e => { if (on.has(e.dataset.id)) e.classList.add('on'); });
      svg.classList.add('sk-f');
    }
    function focusLink(svg, l){
      clear(svg); l.classList.add('on');
      svg.querySelectorAll('.sk-n,.sk-t').forEach(e => { if (e.dataset.id === l.dataset.s || e.dataset.id === l.dataset.t) e.classList.add('on'); });
      svg.classList.add('sk-f');
    }
    document.addEventListener('mouseover', ev => {
      const t = ev.target, svg = svgOf(t); if (!svg) return;
      if (t.dataset && t.dataset.tip) { tip.textContent = t.dataset.tip; tip.hidden = false; }
      if (svg.dataset.pin) return;
      if (t.classList.contains('sk-n')) focusNode(svg, t.dataset.id);
      else if (t.classList.contains('sk-l')) focusLink(svg, t);
    });
    document.addEventListener('mousemove', ev => { if (!tip.hidden) { tip.style.left = Math.min(ev.clientX + 12, innerWidth - 330) + 'px'; tip.style.top = (ev.clientY + 14) + 'px'; } });
    document.addEventListener('mouseout', ev => {
      const t = ev.target, svg = svgOf(t); if (!svg) return;
      tip.hidden = true;
      if (!svg.dataset.pin && !svgOf(ev.relatedTarget)) clear(svg);
      else if (!svg.dataset.pin && ev.relatedTarget === svg) clear(svg);
    });
    document.addEventListener('click', ev => {
      const t = ev.target, svg = svgOf(t); if (!svg) return;
      if (t.classList.contains('sk-n')) {
        if (svg.dataset.pin === t.dataset.id) { delete svg.dataset.pin; clear(svg); }
        else { svg.dataset.pin = t.dataset.id; focusNode(svg, t.dataset.id); }
      } else if (!t.classList.contains('sk-l')) { delete svg.dataset.pin; clear(svg); }
    });
  }
  if (typeof document !== 'undefined') { if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', install); else install(); }
  g.sankeySVG = sankeySVG; g.hbarsSVG = hbarsSVG; g.SANKEY_PAL = PAL; g.sankeyColor = sankeyColor;
})(typeof window !== 'undefined' ? window : globalThis);
