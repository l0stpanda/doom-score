// Build fan regions from US counties + Canadian census divisions, assign team venues to regions, and make an
// equal-area land grid for the heatmap diagnostics.
// Inputs:  data/raw/geo/us_county/cb_2023_us_county_5m.shp (US Census), data/raw/geo/cd_*.geojson (StatCan 2021),
//          map/data_src/region_rules.csv, region_anchors.csv, region_overrides.csv, regions.csv,
//          map/data/team_locations.csv, node_modules/world-atlas/countries-50m.json (context land only)
// Outputs: map/data/regions.topo.json (regions + context land), unit_regions.csv, team_regions.csv, land_grid.csv
// Method: every county / census division goes to its nearest anchor place (great-circle distance from the unit's
// interior point), choosing only among the regions its state/province allows; region_overrides.csv wins over both.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import mapshaper from 'mapshaper';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const MAP = path.dirname(HERE), ROOT = path.dirname(MAP);
const GEO = path.join(ROOT, 'data', 'raw', 'geo');
const SRC = path.join(MAP, 'data_src'), OUT = path.join(MAP, 'data');
export const CROP = { latMin: 24, latMax: 57, lonMin: -128, lonMax: -52 };   // study area shown on the map

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
export const miles = (lat1, lon1, lat2, lon2) => {
  const a = Math.sin((lat2 - lat1) * R / 2) ** 2 + Math.cos(lat1 * R) * Math.cos(lat2 * R) * Math.sin((lon2 - lon1) * R / 2) ** 2;
  return 2 * 3958.8 * Math.asin(Math.sqrt(a));
};
const PRUID = { 10: 'NL', 11: 'PE', 12: 'NS', 13: 'NB', 24: 'QC', 35: 'ON', 46: 'MB', 47: 'SK', 48: 'AB', 59: 'BC' };

async function ms(cmd, input) { return mapshaper.applyCommands(cmd, input); }

async function main() {
  const regions = readCsv(path.join(SRC, 'regions.csv'));
  const regionIds = new Set(regions.map(r => r.region_id));
  const rules = Object.fromEntries(readCsv(path.join(SRC, 'region_rules.csv')).map(r => [r.juris, r.allowed_regions.split('|')]));
  const anchors = readCsv(path.join(SRC, 'region_anchors.csv')).map(a => ({ ...a, lat: +a.lat, lon: +a.lon }));
  const overrides = Object.fromEntries(readCsv(path.join(SRC, 'region_overrides.csv')).map(o => [o.unit_id, o]));
  for (const a of anchors) if (!regionIds.has(a.region_id)) throw new Error(`anchor ${a.place}: unknown region ${a.region_id}`);
  for (const [j, rs] of Object.entries(rules)) for (const r of rs) if (!regionIds.has(r)) throw new Error(`rule ${j}: unknown region ${r}`);

  // 1. units with interior points (US: contiguous states + DC; Canada: provinces, not territories)
  const usShp = path.join(GEO, 'us_county', 'cb_2023_us_county_5m.shp').replace(/\\/g, '/');
  const cdFiles = ['cd_0', 'cd_100', 'cd_200'].map(f => path.join(GEO, f + '.geojson').replace(/\\/g, '/'));
  const out1 = await ms(
    `-i "${usShp}" name=us -filter '["02","15","60","66","69","72","78"].indexOf(STATEFP) < 0' ` +
    `-each 'unit_id="US"+GEOID, uname=NAMELSAD, juris=STUSPS' -filter-fields unit_id,uname,juris ` +
    `-i ${cdFiles.map(f => `"${f}"`).join(' ')} combine-files -merge-layers target=cd_0,cd_100,cd_200 name=ca ` +
    `-filter '+PRUID < 60' -each 'unit_id="CA"+CDUID, uname=CDNAME, juris=${JSON.stringify(PRUID)}[PRUID]' ` +
    `-filter-fields unit_id,uname,juris -merge-layers target=us,ca force name=units ` +
    `-clean gap-fill-area=200km2 snap-interval=0.0005 ` +
    `-each 'ix=this.innerX, iy=this.innerY' -o format=geojson units.json`);
  const units = JSON.parse(out1['units.json']);

  // 2. assign regions
  const assign = [];
  for (const f of units.features) {
    const p = f.properties, allowed = rules[p.juris];
    if (!allowed) throw new Error(`no region rule for ${p.juris}`);
    let best = null;
    for (const a of anchors) {
      if (!allowed.includes(a.region_id)) continue;
      const d = miles(p.iy, p.ix, a.lat, a.lon);
      if (!best || d < best.d) best = { a, d };
    }
    let region_id = best ? best.a.region_id : allowed[0], method = best ? 'nearest-anchor' : 'only-allowed';
    const o = overrides[p.unit_id];
    if (o) { region_id = o.region_id; method = 'override'; }
    p.region_id = region_id;
    assign.push({ unit_id: p.unit_id, name: p.uname, juris: p.juris, region_id, method,
                  anchor: best ? best.a.place : '', anchor_miles: best ? best.d.toFixed(0) : '',
                  override_reason: o ? o.reason : '' });
  }
  const unused = Object.keys(overrides).filter(k => !assign.find(a => a.unit_id === k));
  if (unused.length) throw new Error(`overrides for unknown units: ${unused}`);
  writeCsv(path.join(OUT, 'unit_regions.csv'), assign.sort((a, b) => a.unit_id.localeCompare(b.unit_id)),
           ['unit_id', 'name', 'juris', 'region_id', 'method', 'anchor', 'anchor_miles', 'override_reason']);

  // 3. dissolve to regions; full-res copy for point-in-polygon, simplified TopoJSON for the web
  const regionMeta = JSON.stringify(Object.fromEntries(regions.map(r => [r.region_id, [r.short_id, r.display_name]])));
  const world = path.join(MAP, 'node_modules', 'world-atlas', 'countries-50m.json').replace(/\\/g, '/');
  const out2 = await ms(
    `-i units.json name=units -dissolve region_id name=regions ` +
    `-each 'short_id=${regionMeta}[region_id][0], name=${regionMeta}[region_id][1]' ` +
    `-o format=geojson regions_full.json -dissolve + name=land -o format=geojson target=land land.json`,
    { 'units.json': JSON.stringify(units) });
  // Lakes = holes in the dissolved study-area land (no extra data: the world-atlas outline treats lakes as land).
  const lakes = { type: 'FeatureCollection', features: [] };
  const landJ = JSON.parse(out2['land.json']);
  for (const g of (landJ.features || []).map(f => f.geometry).concat(landJ.geometries || [])) {
    const f = { geometry: g };
    const polys = f.geometry.type === 'MultiPolygon' ? f.geometry.coordinates : [f.geometry.coordinates];
    for (const poly of polys) for (const hole of poly.slice(1)) {
      let a = 0;                                           // planar area in km2 (equirectangular, fine for a filter)
      for (let i = 0, n = hole.length - 1; i < n; i++) {
        const [x1, y1] = hole[i], [x2, y2] = hole[i + 1];
        a += (x1 * y2 - x2 * y1) * Math.cos(((y1 + y2) / 2) * R);
      }
      if (Math.abs(a / 2) * 111.32 ** 2 >= 300)
        lakes.features.push({ type: 'Feature', properties: {}, geometry: { type: 'Polygon', coordinates: [[...hole].reverse()] } });
    }
  }
  const out2b = await ms(
    `-i regions_full.json name=regions -i lakes.json name=lakes ` +
    `-simplify weighted 6% keep-shapes target=regions -filter-islands min-area=150km2 target=regions ` +
    `-simplify weighted 10% keep-shapes target=lakes ` +
    // context land: other countries + Alaska + Canada's territories only (US/Canada land elsewhere is all in
    // regions, so leaving it out lets the Great Lakes show as water)
    `-i "${world}" -drop target=land -filter-fields name target=countries ` +
    `-filter 'name == "United States of America"' + name=ak target=countries -clip bbox=-180,50,-129.5,75 target=ak ` +
    `-filter 'name == "Canada"' + name=terr target=countries -clip bbox=-145,59.99,-50,85 target=terr ` +
    `-filter 'name != "United States of America" && name != "Canada"' target=countries ` +
    `-merge-layers target=countries,ak,terr force name=context ` +
    `-clip bbox=-170,5,-30,75 target=context -simplify 20% target=context ` +
    `-o format=topojson target=regions,lakes,context quantization=1e5 regions.topo.json`,
    { 'regions_full.json': out2['regions_full.json'], 'lakes.json': JSON.stringify(lakes) });
  fs.writeFileSync(path.join(OUT, 'regions.topo.json'), out2b['regions.topo.json']);
  out2['regions.topo.json'] = out2b['regions.topo.json'];
  console.log(`lakes (holes >= 300 km2): ${lakes.features.length}`);
  const full = JSON.parse(out2['regions_full.json']);
  const missing = [...regionIds].filter(id => !full.features.find(f => f.properties.region_id === id));
  if (missing.length) throw new Error(`regions with no land: ${missing}`);

  // 4. team venues -> region (point-in-polygon on the full-resolution shapes; nearest region if on a shoreline)
  const locs = readCsv(path.join(OUT, 'team_locations.csv'));
  const pts = [...new Map(locs.map(l => [`${l.lat},${l.lon}`, { lat: +l.lat, lon: +l.lon }])).values()];
  const ptsGeo = { type: 'FeatureCollection', features: pts.map((p, i) => ({ type: 'Feature', properties: { pid: i },
    geometry: { type: 'Point', coordinates: [p.lon, p.lat] } })) };
  const out3 = await ms(`-i pts.json name=pts -i regions_full.json name=regions ` +
    `-join target=pts regions fields=region_id -o format=geojson target=pts pts_out.json`,
    { 'pts.json': JSON.stringify(ptsGeo), 'regions_full.json': out2['regions_full.json'] });
  const ptRegion = new Map(JSON.parse(out3['pts_out.json']).features.map(f => [f.properties.pid, f.properties.region_id]));
  const byKey = new Map(pts.map((p, i) => [`${p.lat},${p.lon}`, ptRegion.get(i)]));
  const teamRows = locs.map(l => {
    let r = byKey.get(`${+l.lat},${+l.lon}`), how = 'in-polygon';
    if (!r) {                                              // venue on a simplified shoreline: nearest unit point
      let best = null;
      for (const f of units.features) { const d = miles(+l.lat, +l.lon, f.properties.iy, f.properties.ix); if (!best || d < best.d) best = { d, r: f.properties.region_id }; }
      r = best.r; how = 'nearest-unit';
    }
    return { league: l.league, season: l.season, franchise_id: l.franchise_id, metro_id: l.metro_id, region_id: r, how };
  });
  writeCsv(path.join(OUT, 'team_regions.csv'), teamRows, ['league', 'season', 'franchise_id', 'metro_id', 'region_id', 'how']);

  // 5. equal-area land grid (25 km) inside the study crop, for the sigma diagnostics
  const proj = '+proj=aea +lat_1=29.5 +lat_2=52 +lat_0=40 +lon_0=-96 +datum=WGS84 +units=m';
  const out4 = await ms(
    `-i regions_full.json name=land -dissolve name=land -clip bbox=${CROP.lonMin},${CROP.latMin},${CROP.lonMax},${CROP.latMax} ` +
    `-proj "${proj}" -point-grid interval=25000 + name=grid -clip land target=grid -proj wgs84 target=grid ` +
    `-each 'lon=+this.x.toFixed(4), lat=+this.y.toFixed(4)' target=grid -o format=csv target=grid grid.csv`,
    { 'regions_full.json': out2['regions_full.json'] });
  fs.writeFileSync(path.join(OUT, 'land_grid.csv'), out4['grid.csv']);

  const counts = {};
  for (const a of assign) counts[a.region_id] = (counts[a.region_id] || 0) + 1;
  console.log(`units: ${assign.length} (${assign.filter(a => a.method === 'override').length} overrides); ` +
              `regions: ${full.features.length}; team points off-polygon: ${teamRows.filter(t => t.how !== 'in-polygon').length}; ` +
              `grid points: ${String(out4['grid.csv']).split('\n').length - 2}; topojson ${(String(out2['regions.topo.json']).length / 1024).toFixed(0)} KB`);
  console.log(counts);
}

main().catch(e => { console.error(e); process.exit(1); });
