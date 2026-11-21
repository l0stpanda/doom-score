// Heatmap test map (Phase 1 check d, regenerated after the palette change): local outlook at the chosen sigma for
// the default season, drawn with the shared surface code in map/src/heat.js and the palette LUT in palette.json.
import fs from 'node:fs';
import path from 'node:path';

const HEAT_JS = `
document.getElementById('sub').textContent = DATA.sub;
const cv = document.getElementById('cv'); cv.width = W; cv.height = H;
document.getElementById('wrap').style.background = '#dfe7ef';
const mask = DoomHeat.landMask(W, H, g => d3.geoPath(proj, g)(regions));
const t0 = performance.now();
DoomHeat.paint(cv.getContext('2d'), W, H, { proj, teams: DATA.teams, sigma: DATA.sigma, w0: DATA.w0, w1: DATA.w1,
  zlo: DATA.zlo, zhi: DATA.zhi, table: DoomHeat.colorTable(DATA.lut, DATA.grey), mask });
document.title += ' ' + Math.round(performance.now() - t0) + 'ms';
svg.append('g').selectAll('path').data(context.features).join('path').attr('d', geo).attr('fill', '#ecece8').attr('stroke', '#d0d0cb').attr('stroke-width', .5);
svg.append('path').attr('d', geo(topojson.mesh(TOPO_DATA, TOPO_DATA.objects.regions, (a, b) => a !== b))).attr('fill', 'none').attr('stroke', '#fff').attr('stroke-opacity', .5).attr('stroke-width', .8);
const g = svg.append('g');
for (const t of DATA.teams) { const [x, y] = proj([t.lon, t.lat]);
  g.append('circle').attr('cx', x).attr('cy', y).attr('r', 2.6).attr('fill', '#1d2330').attr('stroke', '#fff').attr('stroke-width', .8); }
const lg = svg.append('g').attr('transform', 'translate(30,' + (H - 92) + ')').attr('font-size', 13).attr('fill', '#1d2330');
lg.append('rect').attr('x', -12).attr('y', -26).attr('width', 470).attr('height', 104).attr('rx', 8).attr('fill', '#fff').attr('fill-opacity', .9);
const gr = svg.append('defs').append('linearGradient').attr('id', 'rg');
DATA.lut.forEach((c, i) => { if (i % 5 === 0 || i === 255) gr.append('stop').attr('offset', i / 255).attr('stop-color', c); });
lg.append('rect').attr('width', 300).attr('height', 16).attr('fill', 'url(#rg)').attr('rx', 3);
lg.append('text').attr('y', -8).text('Bright future'); lg.append('text').attr('x', 300).attr('y', -8).attr('text-anchor', 'end').text('Doomed');
lg.append('rect').attr('x', 320).attr('width', 26).attr('height', 16).attr('fill', DATA.grey).attr('rx', 3);
lg.append('text').attr('x', 352).attr('y', 13).text('No teams nearby');
lg.append('circle').attr('cx', 333).attr('cy', 40).attr('r', 7).attr('fill', 'none').attr('stroke', '#8a909c').attr('stroke-width', 3);
lg.append('text').attr('x', 352).attr('y', 45).text('Too new to score');
lg.append('text').attr('y', 45).attr('fill', '#545b69').text('Colors compare teams within their league,');
lg.append('text').attr('y', 62).attr('fill', '#545b69').text('then across leagues.');
`;

export default async function ({ page, shoot, csv, DATA_DIR }) {
  const derived = JSON.parse(fs.readFileSync(path.join(DATA_DIR, 'derived.json'), 'utf8'));
  const pal = JSON.parse(fs.readFileSync(path.join(DATA_DIR, 'palette.json'), 'utf8')).palettes.default;
  const T = csv(path.join(DATA_DIR, 'team_seasons.csv'));
  const season = String(derived.default_season);
  const teams = T.filter(t => t.season === season && t.scored === 'True').map(t => ({ lat: +t.lat, lon: +t.lon, z: +t.z_pred }));
  const sigma = derived.sigma_mi;
  const sub = `Local outlook, predicted, season ${season} (${teams.length} teams, ${derived.leagues.join(' + ')}); sigma = ${sigma} mi; ` +
    `opacity 0 at W <= ${derived.opacity_w0}, full at W >= ${derived.opacity_w1}; colour ends z ${derived.z_lo} / +${derived.z_hi}; ` +
    `palette ${pal.method.family} (${pal.method.variant}); render-time smoothing on`;
  await shoot(`map_heatmap_sigma${String(sigma).padStart(3, '0')}`, page('Doom Map: heatmap test', HEAT_JS,
    { teams, sigma, w0: derived.opacity_w0, w1: derived.opacity_w1, zlo: derived.z_lo, zhi: derived.z_hi,
      lut: pal.lut.light, grey: pal.light.grey, sub }));
}
