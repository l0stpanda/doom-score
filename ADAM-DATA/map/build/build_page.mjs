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
  const teams = csv(path.join(MAP, 'data', 'team_seasons.csv')).map(t => ({
    league: t.league, season: +t.season, franchise_id: t.franchise_id, team: t.team || t.season_team_name,
    season_team_name: t.season_team_name, city: t.city, metro: t.metro, metro_id: t.metro_id, lat: +t.lat, lon: +t.lon,
    region_id: t.region_id, scored: t.scored === 'True', z: num(t.z_pred), doom: num(t.doom_pred), band: t.doom_band,
    lo80: num(t.doom_lo80), hi80: num(t.doom_hi80), win_pct: num(t.win_pct), wpp: num(t.win_pct_percentile),
    quadrant: t.quadrant, z_actual: num(t.z_actual), actual_doom: num(t.actual_doom), pred_type: t.pred_type,
  }));
  const topo = JSON.parse(read(MAP, 'data', 'regions.topo.json'));
  return { derived, palette, leagues, regions, teams, topo };
}

export function buildHtml(data = payload()) {
  return `<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Doom Map</title>
<style>${read(MAP, 'src', 'map.css')}</style></head>
<body><div id="doom-map"></div>
<script>${lib('d3/dist/d3.min.js')}</script>
<script>${lib('topojson-client/dist/topojson-client.min.js')}</script>
<script>${read(MAP, 'src', 'heat.js')}</script>
<script>window.DOOM_MAP_DATA=${JSON.stringify(data)};</script>
<script>${read(MAP, 'src', 'map.js')}</script>
</body></html>`;
}

if (import.meta.url === `file:///${process.argv[1].replace(/\\/g, '/')}` || process.argv[1].endsWith('build_page.mjs')) {
  const out = path.join(ROOT, 'dashboard', 'doom_map.html');
  const html = buildHtml();
  fs.writeFileSync(out, html);
  console.log(`wrote ${path.relative(ROOT, out)} (${(html.length / 1024).toFixed(0)} KB)`);
}
