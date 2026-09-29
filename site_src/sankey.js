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
    const color = o.color || ((n, i) => PAL[kept[0].indexOf(n) >= 0 ? kept[0].indexOf(n) % PAL.length : i % PAL.length]);
    // colour each link by the first-column ancestor it traces back to (or its source)
    const srcCol = n => { const i = kept[0].indexOf(n); return i >= 0 ? PAL[i % PAL.length] : null; };
    L.sort((a, b) => (byId[a.s].y - byId[b.s].y) || (byId[a.t].y - byId[b.t].y));
    let out = `<svg viewBox='0 0 ${W} ${H}' width='100%' role='img' aria-label='${esc(o.label || 'flow diagram')}' style='display:block;font:11px system-ui,sans-serif'>`;
    L.forEach(l => {
      const s = byId[l.s], t = byId[l.t], h = l.v * k; if (s.h === undefined || t.h === undefined) return;
      const xa = s.x + nodeW, xb = t.x, ya = s.sy + h / 2, yb = t.ty + h / 2; s.sy += h; t.ty += h;
      const mx = (xa + xb) / 2, c = l.color || srcCol(s) || color(s, col[l.s]);
      out += `<path d='M${xa},${ya}C${mx},${ya} ${mx},${yb} ${xb},${yb}' fill='none' stroke='${c}' stroke-opacity='.32' stroke-width='${Math.max(1, h)}'><title>${esc(s.label)} → ${esc(t.label)}: ${esc(fmt(l.v))}</title></path>`;
    });
    kept.forEach((c, i) => c.forEach(n => {
      const fill = n.color || (i === 0 ? srcCol(n) : '#64748b');
      out += `<rect x='${n.x}' y='${n.y}' width='${nodeW}' height='${n.h}' rx='2' fill='${fill}'><title>${esc(n.label)}: ${esc(fmt(n.v))}</title></rect>`;
      const lx = i === nc - 1 ? n.x + nodeW + 4 : (i === 0 ? n.x - 4 : n.x + nodeW + 4);
      const anchor = i === 0 ? 'end' : 'start';
      if (n.h >= 7 || c.length <= 8) out += `<text x='${lx}' y='${n.y + n.h / 2 + 3.5}' text-anchor='${anchor}' fill='#334155' stroke='#fff' stroke-width='3' stroke-linejoin='round' paint-order='stroke'>${esc(String(n.label).length > 22 ? String(n.label).slice(0, 21) + '…' : String(n.label))}</text>`;
    }));
    return out + `</svg>`;
  }
  function hbarsSVG(rows, o = {}){
    const W = o.width || 360, fmt = o.fmt || (v => v), lw = o.labelW || 118, vw = 52, rh = 18;
    const max = o.max || Math.max(...rows.map(r => r.v), 1e-9), H = rows.length * rh + 2;
    let out = `<svg viewBox='0 0 ${W} ${H}' width='100%' role='img' aria-label='${esc(o.label || 'bar chart')}' style='display:block;font:11px system-ui,sans-serif'>`;
    rows.forEach((r, i) => {
      const y = i * rh + 1, bw = Math.max(1, (W - lw - vw - 8) * r.v / max), c = r.color || o.color || '#2a78d6';
      const lab = String(r.label).length > 20 ? String(r.label).slice(0, 19) + '…' : String(r.label);
      out += `<text x='${lw - 6}' y='${y + 12}' text-anchor='end' fill='#334155'>${esc(lab)}<title>${esc(r.label)}</title></text>`
        + `<rect x='${lw}' y='${y + 3}' width='${bw}' height='${rh - 7}' rx='3' fill='${c}'><title>${esc(r.label)}: ${esc(fmt(r.v))}</title></rect>`
        + `<text x='${lw + bw + 5}' y='${y + 12}' fill='#475569'>${esc(fmt(r.v))}</text>`;
    });
    return out + `</svg>`;
  }
  g.sankeySVG = sankeySVG; g.hbarsSVG = hbarsSVG; g.SANKEY_PAL = PAL;
})(typeof window !== 'undefined' ? window : globalThis);
