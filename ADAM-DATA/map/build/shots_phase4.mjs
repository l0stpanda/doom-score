// Phase 4 captures and checks of dashboard/index.html (map + scatter + shared panel) with Playwright + installed Edge.
// Usage: node map/build/shots_phase4.mjs <frames_dir>
//   -> reports/figures/map_p4_*.png, reports/map_derived/perf_phase4.csv, GIF frames in <frames_dir>/linked_selection/
//   Exits non-zero on page errors or a failed check.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright-core';

const ROOT = path.dirname(path.dirname(path.dirname(fileURLToPath(import.meta.url))));
const PAGE = 'file:///' + path.join(ROOT, 'dashboard', 'index.html').split(path.sep).join('/');
const FIG = path.join(ROOT, 'reports', 'figures');
const FRAMES = process.argv[2] || path.join(ROOT, 'map', 'check', 'frames');
const errors = [], checks = [], perf = [];
const check = (name, ok, detail = '') => { checks.push(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? '  (' + detail + ')' : ''}`); if (!ok) errors.push('check failed: ' + name); };

async function open(browser, hash, { w = 1440, h = 1300, scheme = 'light', touch = false } = {}) {
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, colorScheme: scheme, hasTouch: touch, isMobile: touch, deviceScaleFactor: 1 });
  const page = await ctx.newPage();
  page.on('pageerror', e => errors.push(`${hash}: ${e.message}`));
  page.on('console', m => { if (m.type() === 'error') errors.push(`${hash}: ${m.text()}`); });
  const t0 = Date.now();
  await page.goto(PAGE + '#' + hash);
  await page.waitForFunction(() => document.querySelector('#doom-map')?.dataset.painted, null, { timeout: 30000 });
  page.loadMs = Date.now() - t0;
  return page;
}
const shot = async (page, name, full = false) => { await page.screenshot({ path: path.join(FIG, `map_p4_${name}.png`), fullPage: full }); console.log('wrote', `map_p4_${name}.png`); };
const zoomDone = page => page.waitForFunction(() => document.querySelector('#doom-map').dataset.zoomMs).then(() => page.waitForTimeout(450));
const center = (page, sel) => page.evaluate(sel => { const r = document.querySelector(sel).getBoundingClientRect(); return [r.x + r.width / 2, r.y + r.height / 2]; }, sel);
const ptCenter = (page, fid) => page.evaluate(fid => { const n = [...document.querySelectorAll('#dm-sc-svg path.pt')].find(n => n.__data__.franchise_id === fid); const r = n.getBoundingClientRect(); return [r.x + r.width / 2, r.y + r.height / 2]; }, fid);
const logoCenter = (page, name) => page.evaluate(name => { const n = [...document.querySelectorAll('#dm-svg g.dm-logo')].find(n => n.__data__ && n.__data__.t && n.__data__.t.season_team_name === name); const r = n.getBoundingClientRect(); return [r.x + r.width / 2, r.y + r.height / 2]; }, name);
const hash = page => page.evaluate(() => Object.fromEntries(new URLSearchParams(location.hash.slice(1))));

const browser = await chromium.launch({ channel: 'msedge' });

// 1. overview, both themes
{ const page = await open(browser, 'theme=light'); await shot(page, 'dashboard_light'); await page.close(); }
{ const page = await open(browser, 'theme=dark', { scheme: 'dark' }); await shot(page, 'dashboard_dark'); await page.close(); }

// 2. linked selection both ways (+ GIF frames)
{
  const page = await open(browser, 'theme=light&season=2025', { h: 1250 });
  await page.waitForTimeout(1500);
  const dir = path.join(FRAMES, 'linked_selection'); fs.rmSync(dir, { recursive: true, force: true }); fs.mkdirSync(dir, { recursive: true });
  const times = []; let n = 0; const T0 = Date.now();
  const frame = async () => { await page.screenshot({ path: path.join(dir, String(n++).padStart(3, '0') + '.png') }); times.push(Date.now() - T0); };
  const burst = async ms => { const end = Date.now() + ms; while (Date.now() < end) await frame(); };
  await frame(); await page.waitForTimeout(500); await frame();
  // scatter -> map: hover then click the most isolated point (stacked points can't be told apart by a click)
  const A = await page.evaluate(() => { const pts = [...document.querySelectorAll('#dm-sc-svg path.pt')].map(n => { const r = n.getBoundingClientRect(); return { f: n.__data__.franchise_id, reg: n.__data__.region_id, x: r.x + r.width / 2, y: r.y + r.height / 2 }; });
    return pts.map(p => ({ ...p, d: Math.min(...pts.filter(q => q !== p).map(q => Math.hypot(p.x - q.x, p.y - q.y))) })).sort((a, b) => b.d - a.d)[0]; });
  let p = [A.x, A.y];
  await page.mouse.move(p[0], p[1]); await page.waitForTimeout(250); await frame(); await page.waitForTimeout(500); await frame();
  await page.mouse.click(p[0], p[1]); await page.waitForTimeout(200); await frame(); await page.waitForTimeout(700); await frame();
  let st = await page.evaluate(() => ({ team: DoomMap.state.team, panel: document.querySelector('#dm-list').classList.contains('dm-panel'), marker: document.querySelectorAll('#dm-svg g.dm-selmark').length }));
  check('scatter click selects team in both views and opens the panel', st.team?.franchise_id === A.f && st.panel && st.marker === 1, JSON.stringify(st));
  await shot(page, 'linked_scatter_to_map');
  // panel "Show on map" -> zoom to region, selected badge highlighted
  await page.click('#dm-show-map'); await burst(1100); await zoomDone(page); await frame(); await page.waitForTimeout(400); await frame();
  // map -> scatter: click another badge in the zoomed region
  await page.evaluate(() => window.scrollTo(0, 0)); await page.waitForTimeout(150);
  const B = await page.evaluate(f => {                 // a badge in the region that is actually clickable (not under the legend)
    for (const n of document.querySelectorAll('#dm-svg g.dm-logo:not(.other)')) {
      if (!n.__data__ || n.__data__.t.franchise_id === f) continue;
      const r = n.getBoundingClientRect(), x = r.x + r.width / 2, y = r.y + r.height / 2, hit = document.elementFromPoint(x, y);
      if (hit && hit.closest('g.dm-logo') === n) return { f: n.__data__.t.franchise_id, name: n.__data__.t.season_team_name, x, y };
    }
    return null; }, A.f);
  p = [B.x, B.y];
  await page.mouse.move(p[0], p[1]); await page.waitForTimeout(250); await frame(); await page.waitForTimeout(400); await frame();
  await page.mouse.click(p[0], p[1]); await page.waitForTimeout(250); await frame(); await page.waitForTimeout(900); await frame();
  st = await page.evaluate(() => ({ team: DoomMap.state.team, sc: document.querySelectorAll('#dm-sc-svg g.dm-logo.on').length, scName: document.querySelector('#dm-sc-svg .selname')?.textContent }));
  check('map badge click selects team in the scatter and opens the panel', st.team?.franchise_id === B.f && st.sc === 1 && st.scName === B.name, JSON.stringify(st));
  await shot(page, 'linked_map_to_scatter');
  // season shared: change season, selection follows
  await page.selectOption('#dm-season', '2019'); await page.waitForTimeout(700); await frame(); await page.waitForTimeout(800); await frame();
  st = await page.evaluate(() => ({ season: DoomMap.state.season, name: document.querySelector('#dm-list h2')?.textContent, scTitle: document.querySelector('#dm-sc-title').textContent }));
  check('season is shared by map, scatter and panel', st.season === 2019 && !!st.name && /2019/.test(st.scTitle), JSON.stringify(st));
  fs.writeFileSync(path.join(dir, 'times.json'), JSON.stringify({ times, time_scale: 1, real: true }));
  // URL round trip
  const h = await hash(page);
  check('URL keeps view, region, season, leagues, team', h.view === 'both' && h.region === A.reg && h.season === '2019' && h.leagues === 'MLB,NHL' && h.team.endsWith(':' + B.f), JSON.stringify(h));
  const url = await page.evaluate(() => location.hash.slice(1)); await page.close();
  const p2 = await open(browser, url, { h: 1250 }); await p2.waitForTimeout(900);
  st = await p2.evaluate(() => ({ s: DoomMap.state.season, f: DoomMap.state.focus, l: DoomMap.state.level, t: DoomMap.state.team }));
  check('opening the URL restores the same view', st.s === 2019 && st.f === A.reg && st.l === 2 && st.t?.franchise_id === B.f, JSON.stringify(st));
  await shot(p2, 'url_restored'); await p2.close();
}

// 3. predicted vs actual
{ const page = await open(browser, 'theme=light&season=2019&mode=actual');
  const st = await page.evaluate(() => ({ showing: document.querySelector('#dm-showing').textContent, legend: document.querySelector('#dm-legend .showing').textContent, axis: [...document.querySelectorAll('#dm-sc-svg .axlbl')].map(t => t.textContent).join(' | ') }));
  check('actual mode is labeled in toolbar, legend and scatter axis', /actual/i.test(st.showing) && /actual/.test(st.legend) && /Actual standing/.test(st.axis), JSON.stringify(st));
  await shot(page, 'actual_2019');
  await page.selectOption('#dm-season', '2025'); await page.waitForTimeout(600);
  const dis = await page.evaluate(() => ({ btn: [...document.querySelectorAll('#dm-mode button')].find(b => b.textContent === 'Actual').disabled, showing: document.querySelector('#dm-showing').textContent }));
  check('actual toggle disabled where no actuals exist (2025), view falls back to predicted with a label', dis.btn && /predicted/i.test(dis.showing), JSON.stringify(dis));
  await page.close(); }
{ const page = await open(browser, 'theme=light&season=2023&mode=actual');
  const b = await page.evaluate(() => document.querySelector('#dm-banner').textContent);
  check('mixed actuals (2023: MLB yes, NHL no) are flagged', /MLB only/.test(b), b); await shot(page, 'actual_2023_partial'); await page.close(); }

// 4. search + keyboard
{ const page = await open(browser, 'theme=light');
  await page.click('#dm-search'); await page.keyboard.type('toro'); await page.waitForTimeout(150); await shot(page, 'search_results');
  const opts = await page.evaluate(() => [...document.querySelectorAll('#dm-results li')].map(l => l.textContent.trim()));
  check('search finds teams, cities and regions', opts.some(o => /Team/.test(o)) && opts.some(o => /City/.test(o)) && opts.some(o => /Region/.test(o)), opts.join(' / '));
  await page.keyboard.press('ArrowDown'); await page.keyboard.press('Enter'); await zoomDone(page);
  let st = await page.evaluate(() => ({ l: DoomMap.state.level, f: DoomMap.state.focus, t: DoomMap.state.team }));
  check('search Enter flies to the result', st.l === 2 && st.f === 'golden-horseshoe', JSON.stringify(st));
  await shot(page, 'search_flown_toronto');
  await page.keyboard.press('Escape'); await page.keyboard.press('Escape'); await page.waitForTimeout(800);
  // keyboard: Tab to the first region list item, Enter zooms; Tab to a badge, Enter opens the panel; Esc goes up
  await page.focus('#dm-rows li'); await page.keyboard.press('Enter'); await zoomDone(page);
  st = await page.evaluate(() => ({ l: DoomMap.state.level, f: DoomMap.state.focus }));
  check('Enter on a region list item zooms to it', st.l === 2, JSON.stringify(st));
  let tabs = 0, onLogo = false;
  await page.focus('#dm-all');
  for (; tabs < 12 && !onLogo; tabs++) { await page.keyboard.press('Tab'); onLogo = await page.evaluate(() => document.activeElement?.classList?.contains('dm-logo')); }
  await page.waitForTimeout(150); await shot(page, 'keyboard_focus_badge');
  await page.keyboard.press('Enter'); await page.waitForTimeout(200);
  const opened = await page.evaluate(() => !!DoomMap.state.team);
  check('Tab reaches a team badge and Enter opens the panel', onLogo && opened, `tabs ${tabs}`);
  await page.keyboard.press('Escape'); await page.waitForTimeout(100);
  const a = await page.evaluate(() => [!!DoomMap.state.team, DoomMap.state.level]);
  await page.keyboard.press('Escape'); await page.waitForTimeout(800);
  const b = await page.evaluate(() => DoomMap.state.level);
  check('Esc closes the panel, then goes up a level', a[0] === false && a[1] === 2 && b === 1, `after 1st Esc ${a}, after 2nd ${b}`);
  await page.close(); }

// 5. touch: tap shows a card with a button; tap the button acts
{ const page = await open(browser, 'theme=light&view=both', { w: 412, h: 1800, touch: true });
  const p = await page.evaluate(() => { const el = document.querySelector('#dm-svg [data-region="new-york"]'), r = el.getBoundingClientRect(); return [r.x + r.width * 0.45, r.y + r.height * 0.6]; });
  await page.touchscreen.tap(p[0], p[1]); await page.waitForTimeout(300);
  let st = await page.evaluate(() => ({ pinned: document.querySelector('#dm-card').classList.contains('pinned'), btn: !!document.querySelector('#dm-pin-zoom'), lvl: DoomMap.state.level }));
  check('touch: tapping a region shows its card with a Zoom in button (no zoom yet)', st.pinned && st.btn && st.lvl === 1, JSON.stringify(st));
  await shot(page, 'touch_region_card');
  await page.tap('#dm-pin-zoom'); await zoomDone(page);
  st = await page.evaluate(() => DoomMap.state.level); check('touch: Zoom in button zooms', st === 2);
  await shot(page, 'touch_zoomed');
  const q = await ptCenter(page, 'new-york-mets');
  await page.touchscreen.tap(q[0], q[1]); await page.waitForTimeout(250);
  st = await page.evaluate(() => ({ pinned: document.querySelector('#dm-card').classList.contains('pinned'), btn: !!document.querySelector('#dm-pin-details') }));
  check('touch: tapping a scatter point shows its card with a Details button', st.pinned && st.btn, JSON.stringify(st));
  await shot(page, 'touch_scatter_card');
  await page.tap('#dm-pin-details'); await page.waitForTimeout(250);
  st = await page.evaluate(() => DoomMap.state.team?.franchise_id); check('touch: Details opens the shared panel', st === 'new-york-mets', st);
  await page.close(); }

// 6. performance: first paint, season switch, zoom frame rate
for (const dpr of [1, 2]) {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 1250 }, deviceScaleFactor: dpr });
  const page = await ctx.newPage(); const t0 = Date.now();
  await page.goto(PAGE + '#theme=light&season=2025'); await page.waitForFunction(() => document.querySelector('#doom-map').dataset.painted);
  perf.push({ dpr, metric: 'load to first paint (ms)', value: Date.now() - t0 });
  await page.waitForFunction(() => document.querySelector('#doom-map').dataset.prefetched === '1', null, { timeout: 120000 });
  const sw = await page.evaluate(async () => {
    const out = [];
    for (const s of [2024, 2023, 2015, 2025]) {
      const el = document.querySelector('#doom-map'), n = el.dataset.painted, t = performance.now();
      DoomMap.state.season = s; DoomMap.update();
      await new Promise(r => { const f = () => el.dataset.painted !== n ? r() : requestAnimationFrame(f); f(); });
      out.push(performance.now() - t);
    }
    return out;
  });
  perf.push({ dpr, metric: 'season switch incl. map + scatter + list redraw, median of 4 (ms)', value: Math.round(sw.sort((a, b) => a - b)[2]) });
  await page.waitForTimeout(3000);
  for (const [rid, label] of [['new-york', 'continent -> New York'], ['cascadia', 'New York -> Cascadia (long jump)']]) {
    const f = await page.evaluate(async rid => {
      DoomMap.startFrameLog(); document.querySelector('#doom-map').dataset.zoomMs = ''; DoomMap.zoomToRegion(rid);
      await new Promise(r => { const g = () => document.querySelector('#doom-map').dataset.zoomMs ? r() : requestAnimationFrame(g); g(); });
      const t = DoomMap.stopFrameLog(), gaps = t.slice(1).map((v, i) => v - t[i]);
      return { frames: t.length, ms: t[t.length - 1] - t[0], maxGap: Math.max(...gaps), p95: gaps.sort((a, b) => a - b)[Math.floor(gaps.length * 0.95)] };
    }, rid);
    perf.push({ dpr, metric: `zoom ${label}: frame rate (fps)`, value: Math.round(1000 * (f.frames - 1) / f.ms) });
    perf.push({ dpr, metric: `zoom ${label}: worst frame gap / 95th pct (ms)`, value: `${Math.round(f.maxGap)} / ${Math.round(f.p95)}` });
    await page.waitForTimeout(800);
  }
  await ctx.close();
}
await browser.close();
fs.writeFileSync(path.join(ROOT, 'reports', 'map_derived', 'perf_phase4.csv'), 'dpr,metric,value\n' + perf.map(p => `${p.dpr},"${p.metric}",${p.value}`).join('\n') + '\n');
console.log(checks.join('\n')); console.log(perf.map(p => `dpr ${p.dpr}  ${p.metric}: ${p.value}`).join('\n'));
if (errors.length) { console.error('ERRORS:\n' + errors.join('\n')); process.exit(1); }
console.log('all checks passed, no page errors');
