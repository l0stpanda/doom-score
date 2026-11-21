// Phase-1 check renders (static, not the product): region check map and heatmap test maps.
// Usage: node map/build/render_checks.mjs regions|heatmap
// Writes self-contained HTML to map/check/*.html and PNG screenshots to reports/figures/map_*.png
// (Playwright drives the locally installed Microsoft Edge; nothing is downloaded).
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright-core';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const MAP = path.dirname(HERE), ROOT = path.dirname(MAP);
const DATA = path.join(MAP, 'data'), CHECK = path.join(MAP, 'check'), FIG = path.join(ROOT, 'reports', 'figures');
const lib = p => fs.readFileSync(path.join(MAP, 'node_modules', p), 'utf8');
const D3 = lib('d3/dist/d3.min.js'), TOPO = lib('topojson-client/dist/topojson-client.min.js');
const HEAT = fs.readFileSync(path.join(MAP, 'src', 'heat.js'), 'utf8');

function csv(file) {
  const [h, ...rows] = fs.readFileSync(file, 'utf8').trim().split('\n');
  const cols = h.split(',');
  const split = line => { const out = []; let f = '', q = false;
    for (let i = 0; i < line.length; i++) { const c = line[i];
      if (q) { if (c === '"' && line[i + 1] === '"') { f += '"'; i++; } else if (c === '"') q = false; else f += c; }
      else if (c === '"') q = true; else if (c === ',') { out.push(f); f = ''; } else f += c; }
    out.push(f); return out; };
  return rows.map(r => Object.fromEntries(split(r).map((v, i) => [cols[i], v])));
}

// Shared map frame: conic conformal fitted to the study crop, ocean, context land, regions.
const FRAME = `
const W = 1400, H = 860;
const crop = {type:'Polygon', coordinates:[[[-127,24],[-128,56],[-60,56],[-52,47],[-66,24],[-127,24]]]};
const proj = d3.geoConicConformal().parallels([30, 52]).rotate([96, 0]).fitExtent([[10, 40], [W - 10, H - 10]], crop);
const geo = d3.geoPath(proj);
const regions = topojson.feature(TOPO_DATA, TOPO_DATA.objects.regions);
const context = topojson.feature(TOPO_DATA, TOPO_DATA.objects.context);
const lakes = topojson.feature(TOPO_DATA, TOPO_DATA.objects.lakes);
const svg = d3.select('#map').attr('viewBox', [0, 0, W, H]).attr('width', W).attr('height', H);
`;

function page(title, body, data) {
  return `<!doctype html><html><head><meta charset="utf-8"><title>${title}</title>
<style>body{margin:0;background:#f4f5f7;font:13px system-ui,Segoe UI,sans-serif;color:#1d2330}
h1{font-size:18px;margin:10px 16px 0}.sub{margin:2px 16px;color:#5a6170}#wrap{position:relative}
canvas{position:absolute;left:0;top:0}#map{position:relative;z-index:1;display:block}</style></head><body>
<h1>${title}</h1><div class="sub" id="sub"></div><div id="wrap"><canvas id="cv"></canvas><svg id="map"></svg></div>
<script>${D3}</script><script>${TOPO}</script><script>${HEAT}</script>
<script>const TOPO_DATA=${fs.readFileSync(path.join(DATA, 'regions.topo.json'), 'utf8')};const DATA=${JSON.stringify(data)};</script>
<script>${FRAME}${body}</script></body></html>`;
}

const REGIONS_JS = `
document.getElementById('sub').textContent = DATA.sub;
const pal = [...d3.schemeTableau10, ...d3.schemeSet3, ...d3.schemePastel2];
const ids = regions.features.map(f => f.properties.region_id).sort();
const color = id => pal[ids.indexOf(id) % pal.length];
svg.append('path').attr('d', geo({type:'Sphere'})).attr('fill', '#dfe7ef');
svg.append('g').selectAll('path').data(context.features).join('path').attr('d', geo).attr('fill', '#e8e8e4').attr('stroke', '#c9c9c4').attr('stroke-width', .5);
svg.append('g').selectAll('path').data(regions.features).join('path').attr('d', geo)
  .attr('fill', d => color(d.properties.region_id)).attr('fill-opacity', .55).attr('stroke', d => color(d.properties.region_id)).attr('stroke-opacity', .55).attr('stroke-width', .8);
// region outlines from the topology mesh (shared borders drawn once; hairline US-Canada gaps <300 m are hidden by the fill stroke)
svg.append('path').attr('d', geo(topojson.mesh(TOPO_DATA, TOPO_DATA.objects.regions, (a, b) => a !== b && a.properties.region_id !== b.properties.region_id))).attr('fill', 'none').attr('stroke', '#fff').attr('stroke-width', 1.4);
svg.append('g').selectAll('path').data(lakes.features).join('path').attr('d', geo).attr('fill', '#dfe7ef');
// labels at the largest polygon's centroid inside the crop
const lab = svg.append('g').attr('font-weight', 700).attr('font-size', 12).attr('text-anchor', 'middle');
for (const f of regions.features) {
  const polys = f.geometry.type === 'MultiPolygon' ? f.geometry.coordinates : [f.geometry.coordinates];
  const big = polys.map(c => ({type:'Polygon', coordinates:c})).map(p => [p, d3.geoArea(p)]).sort((a,b) => b[1]-a[1])[0][0];
  let [x, y] = geo.centroid(big); if (y < 60) y = 60 + (f.properties.short_id === 'OTM' ? 120 : 0);
  if (f.properties.short_id === 'OTM') { const p = proj([-73.5, 47.3]); x = p[0]; y = p[1]; }
  if (f.properties.short_id === 'PRA') { const p = proj([-106, 52.3]); x = p[0]; y = p[1]; }
  if (f.properties.short_id === 'GHS') { const p = proj([-81.5, 46.3]); x = p[0]; y = p[1]; }
  lab.append('text').attr('x', x).attr('y', y).attr('fill', '#1d2330').attr('stroke', '#fff').attr('stroke-width', 3)
     .attr('paint-order', 'stroke').text(f.properties.short_id);
}
const pts = svg.append('g');
for (const t of DATA.teams) {
  const [x, y] = proj([t.lon, t.lat]);
  if (t.league === 'MLB') pts.append('circle').attr('cx', x).attr('cy', y).attr('r', 4.2).attr('fill', '#111').attr('stroke', '#fff');
  else pts.append('rect').attr('x', x - 4).attr('y', y - 4).attr('width', 8).attr('height', 8).attr('fill', '#c21f32').attr('stroke', '#fff');
}
const lg = svg.append('g').attr('transform', 'translate(24,' + (H - 70) + ')').attr('font-size', 13);
lg.append('circle').attr('cx', 6).attr('cy', 0).attr('r', 4.2).attr('fill', '#111'); lg.append('text').attr('x', 16).attr('y', 4).text('MLB venue (' + DATA.mlbSeason + ')');
lg.append('rect').attr('x', 2).attr('y', 16).attr('width', 8).attr('height', 8).attr('fill', '#c21f32'); lg.append('text').attr('x', 16).attr('y', 24).text('NHL venue (' + DATA.nhlSeason + ')');
lg.append('text').attr('x', 0).attr('y', 48).attr('fill', '#5a6170').text('Region shapes: US counties (Census 2023) + Canadian census divisions (StatCan 2021), assigned to the nearest fan-identity anchor allowed for their state/province.');
`;

async function shoot(name, html, w = 1400, h = 920) {
  fs.mkdirSync(CHECK, { recursive: true }); fs.mkdirSync(FIG, { recursive: true });
  const file = path.join(CHECK, name + '.html'); fs.writeFileSync(file, html);
  const browser = await chromium.launch({ channel: 'msedge' });
  const pg = await browser.newPage({ viewport: { width: w, height: h }, deviceScaleFactor: 1 });
  await pg.goto('file:///' + file.replace(/\\/g, '/'));
  await pg.waitForTimeout(400);
  await pg.screenshot({ path: path.join(FIG, name + '.png'), fullPage: true });
  await browser.close();
  console.log('wrote', path.relative(ROOT, path.join(FIG, name + '.png')));
}

async function regionsCheck() {
  const locs = csv(path.join(DATA, 'team_locations.csv'));
  for (const [mlb, nhl, tag] of [[null, null, 'latest'], ['2015', '2015', '2015']]) {
    const mlbS = mlb ?? String(Math.max(...locs.filter(l => l.league === 'MLB').map(l => +l.season)));
    const nhlS = nhl ?? String(Math.max(...locs.filter(l => l.league === 'NHL').map(l => +l.season)));
    const teams = locs.filter(l => (l.league === 'MLB' && l.season === mlbS) || (l.league === 'NHL' && l.season === nhlS))
      .map(l => ({ league: l.league, lat: +l.lat, lon: +l.lon }));
    await shoot(`map_check_regions_${tag}`, page('Doom Map: region check', REGIONS_JS,
      { teams, mlbSeason: mlbS, nhlSeason: nhlS, sub: `23 fan regions with MLB ${mlbS} and NHL ${nhlS} venues (${teams.length} teams)` }));
  }
}

const which = process.argv[2] || 'regions';
if (which === 'regions') await regionsCheck();
else if (which === 'heatmap') await (await import('./render_heatmap.mjs')).default({ page, shoot, csv, DATA_DIR: DATA });
