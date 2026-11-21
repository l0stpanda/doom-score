// Heatmap test maps (Phase 1, check d): local outlook at candidate sigmas for one season.
// Local outlook at a point = sum(w_i * z_i) / sum(w_i), w_i = exp(-d_i^2 / 2 sigma^2), d = great-circle miles.
// Colour = OKLab ramp at the scale position of that average (ends clamped at the derived z_lo / z_hi);
// opacity = (W - w0) / (w1 - w0) clamped to [0, 1], mixed in OKLab over the "no teams nearby" grey.
import fs from 'node:fs';
import path from 'node:path';

const HEAT_JS = `
document.getElementById('sub').textContent = DATA.sub;
const pal = DATA.palette, cv = document.getElementById('cv');
cv.width = W; cv.height = H;
const ctx = cv.getContext('2d');
// --- OKLab helpers (same matrices as map/build/palette.py) ---
const toLin = c => c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
const toSrgb = c => c <= 0.0031308 ? 12.92 * c : 1.055 * Math.pow(Math.max(c, 0), 1 / 2.4) - 0.055;
const hex = h => [1, 3, 5].map(i => parseInt(h.slice(i, i + 2), 16) / 255);
function oklab([r, g, b]) { r = toLin(r); g = toLin(g); b = toLin(b);
  const l = Math.cbrt(0.4122214708*r + 0.5363325363*g + 0.0514459929*b), m = Math.cbrt(0.2119034982*r + 0.6806995451*g + 0.1073969566*b),
        s = Math.cbrt(0.0883024619*r + 0.2817188376*g + 0.6299787005*b);
  return [0.2104542553*l + 0.7936177850*m - 0.0040720468*s, 1.9779984951*l - 2.4285922050*m + 0.4505937099*s, 0.0259040371*l + 0.7827717662*m - 0.8086757660*s]; }
function rgb([L, a, b]) { const l = (L + 0.3963377774*a + 0.2158037573*b) ** 3, m = (L - 0.1055613458*a - 0.0638541728*b) ** 3, s = (L - 0.0894841775*a - 1.2914855480*b) ** 3;
  return [4.0767416621*l - 3.3077115913*m + 0.2309699292*s, -1.2684380046*l + 2.6097574011*m - 0.3413193965*s, -0.0041960863*l - 0.7034186147*m + 1.7076147010*s].map(v => Math.round(Math.min(1, Math.max(0, toSrgb(v))) * 255)); }
const [LO, MID, HI, GREY] = ['lo', 'mid', 'hi', 'grey'].map(k => oklab(hex(pal[k])));
const mix = (a, b, u) => a.map((v, i) => v + (b[i] - v) * u);
const rampLab = t => t <= 0.5 ? mix(LO, MID, t * 2) : mix(MID, HI, (t - 0.5) * 2);
const pos = z => z < 0 ? 0.5 * (1 - Math.max(z, DATA.zlo) / DATA.zlo) : 0.5 + 0.5 * Math.min(z, DATA.zhi) / DATA.zhi;
// --- land mask ---
const mk = document.createElement('canvas'); mk.width = W; mk.height = H;
const mctx = mk.getContext('2d'); mctx.fillStyle = '#000'; mctx.strokeStyle = '#000'; mctx.lineWidth = 1;
const gm = d3.geoPath(proj, mctx); mctx.beginPath(); gm(regions); mctx.fill(); mctx.stroke();
const mask = mctx.getImageData(0, 0, W, H).data;
// --- raster ---
const R = Math.PI / 180, two_s2 = 2 * DATA.sigma * DATA.sigma;
const T = DATA.teams.map(t => ({ phi: t.lat * R, lam: t.lon * R, cos: Math.cos(t.lat * R), z: t.z }));
const img = ctx.createImageData(W, H), px = img.data;
const t0 = performance.now();
for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) {
  const k = (y * W + x) * 4; if (mask[k + 3] < 8) continue;
  const ll = proj.invert([x + 0.5, y + 0.5]); if (!ll) continue;
  const phi = ll[1] * R, lam = ll[0] * R, cphi = Math.cos(phi);
  let Wt = 0, S = 0;
  for (const t of T) {
    const a = Math.sin((t.phi - phi) / 2) ** 2 + cphi * t.cos * Math.sin((t.lam - lam) / 2) ** 2;
    const d = 2 * 3958.8 * Math.asin(Math.sqrt(a)), w = Math.exp(-d * d / two_s2);
    Wt += w; S += w * t.z;
  }
  const alpha = Math.min(1, Math.max(0, (Wt - DATA.w0) / (DATA.w1 - DATA.w0)));
  const c = rgb(mix(GREY, rampLab(pos(Wt > 0 ? S / Wt : 0)), alpha));
  px[k] = c[0]; px[k + 1] = c[1]; px[k + 2] = c[2]; px[k + 3] = mask[k + 3];
}
ctx.putImageData(img, 0, 0);
document.title += ' ' + Math.round(performance.now() - t0) + 'ms';
// --- vector overlay: water/context underneath via CSS bg, outlines + teams on top ---
svg.insert('path', ':first-child').attr('d', geo({type:'Sphere'})).attr('fill', 'none');
document.getElementById('wrap').style.background = '#dfe7ef';
const ctxLand = svg.append('g'); ctxLand.selectAll('path').data(context.features).join('path').attr('d', geo).attr('fill', '#ecece8').attr('stroke', '#d0d0cb').attr('stroke-width', .5);
svg.append('path').attr('d', geo(topojson.mesh(TOPO_DATA, TOPO_DATA.objects.regions, (a, b) => a !== b))).attr('fill', 'none').attr('stroke', '#fff').attr('stroke-opacity', .55).attr('stroke-width', .8);
const g = svg.append('g');
for (const t of DATA.teams) { const [x, y] = proj([t.lon, t.lat]);
  g.append('circle').attr('cx', x).attr('cy', y).attr('r', 2.6).attr('fill', '#1d2330').attr('stroke', '#fff').attr('stroke-width', .8); }
// --- legend ---
const lg = svg.append('g').attr('transform', 'translate(30,' + (H - 92) + ')').attr('font-size', 13).attr('fill', '#1d2330');
lg.append('rect').attr('x', -12).attr('y', -26).attr('width', 470).attr('height', 104).attr('rx', 8).attr('fill', '#fff').attr('fill-opacity', .9);
const gr = svg.append('defs').append('linearGradient').attr('id', 'rg');
for (let i = 0; i <= 20; i++) gr.append('stop').attr('offset', i / 20).attr('stop-color', 'rgb(' + rgb(rampLab(i / 20)) + ')');
lg.append('rect').attr('width', 300).attr('height', 16).attr('fill', 'url(#rg)').attr('rx', 3);
lg.append('text').attr('y', -8).text('Bright future'); lg.append('text').attr('x', 300).attr('y', -8).attr('text-anchor', 'end').text('Doomed');
lg.append('rect').attr('x', 320).attr('width', 26).attr('height', 16).attr('fill', pal.grey).attr('rx', 3);
lg.append('text').attr('x', 352).attr('y', 13).text('No teams nearby');
lg.append('circle').attr('cx', 333).attr('cy', 40).attr('r', 7).attr('fill', 'none').attr('stroke', '#8a909c').attr('stroke-width', 3);
lg.append('text').attr('x', 352).attr('y', 45).text('Too new to score');
lg.append('text').attr('y', 45).attr('fill', '#545b69').text('Colors compare teams within their league,');
lg.append('text').attr('y', 62).attr('fill', '#545b69').text('then across leagues.');
`;

export default async function ({ page, shoot, csv, DATA_DIR }) {
  const derived = JSON.parse(fs.readFileSync(path.join(DATA_DIR, 'derived.json'), 'utf8'));
  const palette = JSON.parse(fs.readFileSync(path.join(DATA_DIR, 'palette.json'), 'utf8')).palettes.default.light;
  const T = csv(path.join(DATA_DIR, 'team_seasons.csv'));
  // test season: latest season in which every league has predictions (read from the data)
  const common = derived.seasons.filter(s => derived.leagues.every(l => derived.league_seasons[l].includes(s)));
  const season = String(Math.max(...common));
  const teams = T.filter(t => t.season === season && t.scored === 'True')
    .map(t => ({ lat: +t.lat, lon: +t.lon, z: +t.z_pred, league: t.league }));
  const cands = [derived.sigma_mi - 25, derived.sigma_mi, derived.sigma_mi + 25];
  for (const sigma of cands) {
    const sub = `Local outlook, predicted, season ${season} (${teams.length} teams, ${derived.leagues.join(' + ')}); ` +
      `sigma = ${sigma} mi${sigma === derived.sigma_mi ? ' (chosen)' : ' (candidate)'}; opacity 0 at W <= ${derived.opacity_w0}, ` +
      `full at W >= ${derived.opacity_w1}; colour ends z ${derived.z_lo} / +${derived.z_hi}; palette as specified`;
    await shoot(`map_heatmap_sigma${String(sigma).padStart(3, '0')}`, page('Doom Map: heatmap test', HEAT_JS,
      { teams, sigma, w0: derived.opacity_w0, w1: derived.opacity_w1, zlo: derived.z_lo, zhi: derived.z_hi, palette, sub }));
  }
}
