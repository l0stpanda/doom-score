// Assign team venues to regions from the committed map/data/regions.topo.json (no raw boundary files needed).
// Inputs:  map/data/regions.topo.json (regions object), map/data/team_locations.csv
// Output:  map/data/team_regions.csv
// This is step 4 of regions.mjs, run on the committed region shapes, so the default build (and adding a league)
// works without data/raw/geo/. regions.mjs still writes the same file when the regions are rebuilt (--rebuild-regions).
// A venue outside every region polygon (on a simplified shoreline) goes to the region with the nearest boundary
// vertex, marked how=nearest-region. See docs/MAP_DECISIONS.md, M49.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import mapshaper from 'mapshaper';
import * as topojson from 'topojson-client';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const MAP = path.dirname(HERE), OUT = path.join(MAP, 'data');

function readCsv(file) {
  const txt = fs.readFileSync(file, 'utf8').replace(/^﻿/, '');
  const rows = [];
  let row = [], f = '', q = false;
  for (let i = 0; i < txt.length; i++) {
    const c = txt[i];
    if (q) { if (c === '"' && txt[i + 1] === '"') { f += '"'; i++; } else if (c === '"') q = false; else f += c; }
    else if (c === '"') q = true;
    else if (c === ',') { row.push(f); f = ''; }
    else if (c === '\n' || c === '\r') { if (c === '\r' && txt[i + 1] === '\n') i++; row.push(f); rows.push(row); row = []; f = ''; }
    else f += c;
  }
  if (f.length || row.length) { row.push(f); rows.push(row); }
  const [head, ...body] = rows.filter(r => r.length > 1 || r[0] !== '');
  return body.map(r => Object.fromEntries(head.map((h, i) => [h, r[i] ?? ''])));
}
const csvCell = v => { const s = String(v ?? ''); return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s; };
const writeCsv = (file, rows, cols) =>
  fs.writeFileSync(file, [cols.join(','), ...rows.map(r => cols.map(c => csvCell(r[c])).join(','))].join('\n') + '\n');

const R = Math.PI / 180;
const miles = (lat1, lon1, lat2, lon2) => {
  const a = Math.sin((lat2 - lat1) * R / 2) ** 2 + Math.cos(lat1 * R) * Math.cos(lat2 * R) * Math.sin((lon2 - lon1) * R / 2) ** 2;
  return 2 * 3958.8 * Math.asin(Math.sqrt(a));
};

async function main() {
  const topo = JSON.parse(fs.readFileSync(path.join(OUT, 'regions.topo.json'), 'utf8'));
  const regions = topojson.feature(topo, topo.objects.regions);
  const locs = readCsv(path.join(OUT, 'team_locations.csv'));
  const pts = [...new Map(locs.map(l => [`${l.lat},${l.lon}`, { lat: +l.lat, lon: +l.lon }])).values()];
  const ptsGeo = { type: 'FeatureCollection', features: pts.map((p, i) => ({ type: 'Feature', properties: { pid: i },
    geometry: { type: 'Point', coordinates: [p.lon, p.lat] } })) };
  const out = await mapshaper.applyCommands(`-i pts.json name=pts -i regions.json name=regions ` +
    `-join target=pts regions fields=region_id -o format=geojson target=pts pts_out.json`,
    { 'pts.json': JSON.stringify(ptsGeo), 'regions.json': JSON.stringify(regions) });
  const ptRegion = new Map(JSON.parse(out['pts_out.json']).features.map(f => [f.properties.pid, f.properties.region_id]));
  const byKey = new Map(pts.map((p, i) => [`${p.lat},${p.lon}`, ptRegion.get(i)]));

  const vertices = [];                                     // [lat, lon, region_id] for the off-polygon fallback
  for (const f of regions.features) {
    const polys = f.geometry.type === 'MultiPolygon' ? f.geometry.coordinates : [f.geometry.coordinates];
    for (const poly of polys) for (const ring of poly) for (const [lon, lat] of ring) vertices.push([lat, lon, f.properties.region_id]);
  }
  const teamRows = locs.map(l => {
    let r = byKey.get(`${+l.lat},${+l.lon}`), how = 'in-polygon';
    if (!r) {
      let best = null;
      for (const [lat, lon, id] of vertices) { const d = miles(+l.lat, +l.lon, lat, lon); if (!best || d < best.d) best = { d, id }; }
      r = best.id; how = 'nearest-region';
    }
    return { league: l.league, season: l.season, franchise_id: l.franchise_id, metro_id: l.metro_id, region_id: r, how };
  });
  writeCsv(path.join(OUT, 'team_regions.csv'), teamRows, ['league', 'season', 'franchise_id', 'metro_id', 'region_id', 'how']);
  console.log(`team venues: ${teamRows.length}; off-polygon: ${teamRows.filter(t => t.how !== 'in-polygon').length}`);
}

main().catch(e => { console.error(e); process.exit(1); });
