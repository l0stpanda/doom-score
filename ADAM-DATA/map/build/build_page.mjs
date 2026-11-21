// Build dashboard/doom_map.html: a self-contained page (d3, topojson-client, heat.js, map.js, CSS and data inlined;
// no server). Like dashboard/doom_scatter.html it is git-ignored and rebuilt with `python map/build_map.py`.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const MAP = path.dirname(HERE), ROOT = path.dirname(MAP);
const read = (...p) => fs.readFileSync(path.join(...p), 'utf8');
const lib = p => read(MAP, 'node_modules', p);

function csv(file) {
  const txt = read(file).replace(/^﻿/, '').trim();
  const rows = []; let row = [], f = '', q = false;
  for (let i = 0; i < txt.length; i++) {
    const c = txt[i];
    if (q) { if (c === '"' && txt[i + 1] === '"') { f += '"'; i++; } else if (c === '"') q = false; else f += c; }
    else if (c === '"') q = true; else if (c === ',') { row.push(f); f = ''; }
    else if (c === '\n' || c === '\r') { if (c === '\r' && txt[i + 1] === '\n') i++; row.push(f); rows.push(row); row = []; f = ''; }
    else f += c;
  }
  row.push(f); rows.push(row);
  const [h, ...b] = rows;
  return b.map(r => Object.fromEntries(h.map((k, i) => [k, r[i] ?? ''])));
}
const num = v => (v === '' || v == null ? null : Math.round(+v * 1e4) / 1e4);

export function payload() {
  const derived = JSON.parse(read(MAP, 'data', 'derived.json'));
  const palette = JSON.parse(read(MAP, 'data', 'palette.json'));
  const leagues = Object.fromEntries(csv(path.join(MAP, 'data_src', 'leagues.csv')).map(r =>
    [r.league, { display_name: r.display_name, season_spans_two_years: r.season_spans_two_years === '1', order: +r.order }]));
  const regions = csv(path.join(MAP, 'data_src', 'regions.csv'));
  // model drivers for the team panel (doom_predictions.csv: top contributions as "Phrase (+x.x)")
  const drv = new Map(csv(path.join(ROOT, 'dashboard', 'data', 'doom_predictions.csv')).map(r => [`${r.league}|${r.season_start_year}|${r.franchise_id}`,
    { up: [1, 2, 3].map(i => r[`driver_up_${i}`]).filter(Boolean), down: [1, 2, 3].map(i => r[`driver_down_${i}`]).filter(Boolean), note: r.driver_note || '' }]));
  const teams = csv(path.join(MAP, 'data', 'team_seasons.csv')).map(t => ({
    league: t.league, season: +t.season, franchise_id: t.franchise_id, team: t.team || t.season_team_name,
    season_team_name: t.season_team_name, city: t.city, metro: t.metro, metro_id: t.metro_id, lat: +t.lat, lon: +t.lon,
    region_id: t.region_id, scored: t.scored === 'True', z: num(t.z_pred), doom: num(t.doom_pred), band: t.doom_band,
    lo80: num(t.doom_lo80), hi80: num(t.doom_hi80), win_pct: num(t.win_pct), wpp: num(t.win_pct_percentile),
    quadrant: t.quadrant, z_actual: num(t.z_actual), actual_doom: num(t.actual_doom), pred_type: t.pred_type,
    drivers: drv.get(`${t.league}|${t.season}|${t.franchise_id}`) || null,
  }));
  const topo = JSON.parse(read(MAP, 'data', 'regions.topo.json'));
  // logos: team_meta.csv URLs cached by dashboard/fetch_logos.py (git-ignored) -> data URIs; monogram always present
  const logos = {};
  let inlined = 0;
  for (const m of csv(path.join(MAP, 'data', 'logo_manifest.csv'))) {
    const f = m.local_file && path.join(ROOT, m.local_file);
    const ok = m.use_logo === 'True' && f && fs.existsSync(f);
    logos[`${m.league}|${m.franchise_id}|${m.season_team_name}`] = { mono: m.monogram,
      uri: ok ? 'data:image/svg+xml;base64,' + fs.readFileSync(f).toString('base64') : null };
    if (ok) inlined++;
  }
  console.log(`logos inlined: ${inlined} of ${Object.keys(logos).length} identities (rest use monograms)`);
  return { derived, palette, leagues, regions, teams, topo, logos };
}

export function buildHtml(data = payload()) {
  return `<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Doom Dashboard</title>
<style>${read(MAP, 'src', 'map.css')}</style></head>
<body><div id="doom-map"></div>
<script>${lib('d3/dist/d3.min.js')}</script>
<script>${lib('topojson-client/dist/topojson-client.min.js')}</script>
<script>${read(MAP, 'src', 'heat.js')}</script>
<script id="dm-heat-src" type="text/plain">${read(MAP, 'src', 'heat.js')}</script>
<script>${read(MAP, 'src', 'heat_cache.js')}</script>
<script>window.DOOM_MAP_DATA=${JSON.stringify(data)};</script>
<script>${read(MAP, 'src', 'map.js')}</script>
</body></html>`;
}

if (import.meta.url === `file:///${process.argv[1].replace(/\\/g, '/')}` || process.argv[1].endsWith('build_page.mjs')) {
  const out = path.join(ROOT, 'dashboard', 'index.html');
  const html = buildHtml();
  fs.writeFileSync(out, html);
  console.log(`wrote ${path.relative(ROOT, out)} (${(html.length / 1024).toFixed(0)} KB)`);
}
