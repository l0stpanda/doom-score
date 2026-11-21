// Phase 3 captures of dashboard/doom_map.html (Level 2) with Playwright driving the installed Edge.
// Usage: node map/build/shots_phase3.mjs <frames_dir>
//   -> reports/figures/map_p3_*.png, and zoom-animation frames + timing JSON in <frames_dir> (assembled into GIFs by
//      map/build/make_gif.py). Exits non-zero on page errors or overlapping logos.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright-core';

const ROOT = path.dirname(path.dirname(path.dirname(fileURLToPath(import.meta.url))));
const PAGE = 'file:///' + path.join(ROOT, 'dashboard', 'doom_map.html').split(path.sep).join('/');
const FIG = path.join(ROOT, 'reports', 'figures');
const FRAMES = process.argv[2] || path.join(ROOT, 'map', 'check', 'frames');
fs.mkdirSync(FRAMES, { recursive: true });
const errors = [], notes = [];

async function open(browser, hash, { w = 1440, h = 980, scheme = 'light', reduced = 'no-preference' } = {}) {
  const page = await browser.newPage({ viewport: { width: w, height: h }, colorScheme: scheme, reducedMotion: reduced });
  page.on('pageerror', e => errors.push(`${hash}: ${e.message}`));
  page.on('console', m => { if (m.type() === 'error') errors.push(`${hash}: ${m.text()}`); });
  await page.goto(PAGE + '#' + hash);
  await page.waitForFunction(() => document.querySelector('#doom-map')?.dataset.painted, null, { timeout: 30000 });
  return page;
}
const shot = async (page, name) => { await page.screenshot({ path: path.join(FIG, `map_p3_${name}.png`) }); console.log('wrote', `map_p3_${name}.png`); };
const settled = page => page.waitForFunction(() => window.DoomMap.state.level === 2 && (document.querySelector('#doom-map').dataset.zoomMs || window.DoomMap.state.focus === new URLSearchParams(location.hash.slice(1)).get('region')))
  .then(() => page.waitForTimeout(500));

/** Overlap check: no two logo badges closer than their diameter. */
async function overlaps(page) {
  return page.evaluate(() => {
    const g = [...document.querySelectorAll('g.dm-logo')].map(n => { const m = n.transform.baseVal.consolidate().matrix; return [m.e, m.f, n.__data__.t.season_team_name]; });
    const bad = [];
    for (let i = 0; i < g.length; i++) for (let j = i + 1; j < g.length; j++) if (Math.hypot(g[i][0] - g[j][0], g[i][1] - g[j][1]) < 2 * 22.5 - 0.5) bad.push(`${g[i][2]} / ${g[j][2]}`);
    return bad;
  });
}
/** Record a zoom animation: frames of the map box with in-page timestamps (slowed x timeScale; times are rescaled). */
async function record(page, name, fn, timeScale = 6) {
  const box = await page.evaluate(() => { const r = document.querySelector('#dm-wrap').getBoundingClientRect(); return { x: r.x, y: r.y, width: r.width, height: r.height }; });
  await page.evaluate(ts => { window.DoomMap.state.timeScale = ts; document.querySelector('#doom-map').dataset.zoomMs = ''; }, timeScale);
  const dir = path.join(FRAMES, name); fs.rmSync(dir, { recursive: true, force: true }); fs.mkdirSync(dir, { recursive: true });
  const times = [];
  const t0 = await page.evaluate(() => performance.now());
  await page.screenshot({ path: path.join(dir, '000.png'), clip: box }); times.push(0);
  await page.evaluate(fn);
  for (let i = 1; i < 200; i++) {
    const t = await page.evaluate(() => performance.now());
    await page.screenshot({ path: path.join(dir, String(i).padStart(3, '0') + '.png'), clip: box });
    times.push((t - t0) / timeScale);
    const done = await page.evaluate(() => document.querySelector('#doom-map').dataset.zoomMs);
    if (done && (t - t0) / timeScale > (+done / timeScale) + 450) break;
  }
  const real = await page.evaluate(() => +document.querySelector('#doom-map').dataset.zoomMs);
  await page.evaluate(() => { window.DoomMap.state.timeScale = 1; });
  fs.writeFileSync(path.join(dir, 'times.json'), JSON.stringify({ times, zoom_ms_slowed: real, time_scale: timeScale }));
  notes.push(`${name}: ${times.length} frames; camera + settle ${Math.round(real / timeScale)} ms at real speed`);
}

const browser = await chromium.launch({ channel: 'msedge' });
// 1. zoom-in recordings: continent -> New York; long jump Cascadia -> South Florida (zooms out first)
{ const page = await open(browser, 'theme=light&palette=default'); await page.waitForTimeout(2500);
  await record(page, 'zoom_in_newyork', () => window.DoomMap.zoomToRegion('new-york'));
  await page.close(); }
{ const page = await open(browser, 'theme=light&palette=default&region=cascadia'); await settled(page);
  await record(page, 'long_jump_cascadia_to_southflorida', () => window.DoomMap.zoomToRegion('south-florida'));
  await page.close(); }
// 2. busiest clusters + cards
for (const [region, name] of [['new-york', 'cluster_newyork'], ['socal', 'cluster_losangeles'], ['chicagoland', 'cluster_chicago'], ['golden-horseshoe', 'cluster_toronto_buffalo']]) {
  const page = await open(browser, 'theme=light&palette=default');
  await page.evaluate(r => window.DoomMap.zoomToRegion(r), region); await settled(page);
  const bad = await overlaps(page); if (bad.length) errors.push(`${region}: overlapping logos ${bad.join(', ')}`);
  await shot(page, name);
  if (region === 'new-york') {
    const b = await page.evaluate(() => { const n = [...document.querySelectorAll('g.dm-logo')].find(n => n.__data__.t.season_team_name === 'New York Yankees'); const r = n.getBoundingClientRect(); return [r.x + r.width / 2, r.y + r.height / 2]; });
    await page.mouse.move(b[0], b[1]); await page.waitForTimeout(150); await shot(page, 'team_card_yankees');
    await page.mouse.click(b[0], b[1]); await page.waitForTimeout(150); await shot(page, 'team_panel_yankees');
    await page.keyboard.press('Escape'); await page.keyboard.press('Escape'); await page.waitForTimeout(900);
    const lvl = await page.evaluate(() => window.DoomMap.state.level); notes.push(`Esc twice from team panel -> level ${lvl}`);
    await shot(page, 'after_esc_level1');
  }
  await page.close();
}
{ const page = await open(browser, 'theme=dark&palette=default', { scheme: 'dark' });
  await page.evaluate(() => window.DoomMap.zoomToRegion('socal')); await settled(page); await shot(page, 'cluster_losangeles_dark'); await page.close(); }
{ const page = await open(browser, 'theme=light&palette=default&logos=monograms');
  await page.evaluate(() => window.DoomMap.zoomToRegion('new-york')); await settled(page); await shot(page, 'cluster_newyork_monograms'); await page.close(); }
{ const page = await open(browser, 'theme=light&palette=greenred&season=2015');
  await page.evaluate(() => window.DoomMap.zoomToRegion('desert-sw')); await settled(page); await shot(page, 'desert_sw_2015_coyotes_greenred'); await page.close(); }
// 3. scroll handling: wheel without activation must not zoom; reduced motion jumps
{ const page = await open(browser, 'theme=light');
  const box = await page.evaluate(() => { const r = document.querySelector('#dm-wrap').getBoundingClientRect(); return [r.x + r.width / 2, r.y + r.height / 2]; });
  await page.mouse.move(box[0], box[1]); await page.mouse.wheel(0, -400); await page.waitForTimeout(250);
  const k1 = await page.evaluate(() => window.DoomMap.transform().k);
  await shot(page, 'scroll_hint');
  await page.keyboard.down('Control'); await page.mouse.wheel(0, -100); await page.keyboard.up('Control'); await page.waitForTimeout(500);
  const k2 = await page.evaluate(() => window.DoomMap.transform().k);
  notes.push(`plain wheel over map: k ${k1.toFixed(2)} (expected 1, page scrolls instead); Ctrl+wheel one notch: k ${k2.toFixed(2)}`);
  await page.close(); }
{ const page = await open(browser, 'theme=light', { reduced: 'reduce' });
  const t = await page.evaluate(async () => { const t0 = performance.now(); window.DoomMap.zoomToRegion('heartland');
    await new Promise(r => { const f = () => window.DoomMap.state.level === 2 && document.querySelector('#doom-map').dataset.zoomMs ? r() : requestAnimationFrame(f); f(); }); return performance.now() - t0; });
  notes.push(`reduced motion: zoom completes in ${Math.round(t)} ms (jump)`); await page.close(); }
{ const page = await open(browser, 'theme=light', { w: 390, h: 1100 });
  await page.evaluate(() => window.DoomMap.zoomToRegion('new-york')); await settled(page); await shot(page, 'phone_newyork'); await page.close(); }
await browser.close();
fs.writeFileSync(path.join(FRAMES, 'notes.txt'), notes.join('\n') + '\n');
console.log(notes.join('\n'));
if (errors.length) { console.error('ERRORS:\n' + errors.join('\n')); process.exit(1); }
console.log('no page errors, no overlapping logos');
