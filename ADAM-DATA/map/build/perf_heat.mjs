// Heat timing: first paint, background prefetch, and repaints on season / palette changes (decision M35).
// Usage: node map/build/perf_heat.mjs  -> prints a table and writes reports/map_derived/heat_timing.csv
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright-core';

const ROOT = path.dirname(path.dirname(path.dirname(fileURLToPath(import.meta.url))));
const url = 'file:///' + path.join(ROOT, 'dashboard', 'index.html').split(path.sep).join('/');
const rows = [];
const b = await chromium.launch({ channel: 'msedge' });
for (const dpr of [1, 2]) {
  const p = await b.newPage({ viewport: { width: 1440, height: 980 }, deviceScaleFactor: dpr });
  const t0 = Date.now(); await p.goto(url + '#theme=light&season=2025');
  await p.waitForFunction(() => document.querySelector('#doom-map').dataset.painted);
  rows.push({ dpr, step: 'load to first paint', ms: Date.now() - t0 });
  const t1 = Date.now();
  await p.waitForFunction(() => document.querySelector('#doom-map').dataset.prefetched === '1', null, { timeout: 120000 });
  rows.push({ dpr, step: 'background prefetch, all seasons (fields in workers)', ms: Date.now() - t1 });
  const change = async (label, fn) => {
    const ms = await p.evaluate(async fn => {
      const el = document.querySelector('#doom-map'), n = el.dataset.painted, t = performance.now();
      new Function('DoomMap', fn)(window.DoomMap);
      await new Promise(r => { const f = () => el.dataset.painted !== n ? r() : requestAnimationFrame(f); f(); });
      return Math.round(performance.now() - t);
    }, fn);
    rows.push({ dpr, step: label, ms });
  };
  await change('season 2025 -> 2024 (cached image)', 'DoomMap.state.season = 2024; DoomMap.update();');
  await change('season 2024 -> 2015 (cached field, colour only)', 'DoomMap.state.season = 2015; DoomMap.update();');
  await change('season 2015 -> 2024 (cached image)', 'DoomMap.state.season = 2024; DoomMap.update();');
  await change('palette switch (cached field, colour only)', 'DoomMap.state.palette = "greenred"; DoomMap.update();');
  const st = await p.evaluate(() => ({ ...DoomMap.cache.stats, workers: DoomMap.cache.workers() }));
  rows.push({ dpr, step: `workers ${st.workers}; fields computed ${st.fieldsComputed}; mean field ${Math.round(st.workerMs / st.fieldsComputed)} ms`, ms: '' });
  await p.close();
}
await b.close();
for (const r of rows) console.log(`dpr ${r.dpr}  ${String(r.ms).padStart(6)}  ${r.step}`);
fs.writeFileSync(path.join(ROOT, 'reports', 'map_derived', 'heat_timing.csv'),
  'dpr,step,ms\n' + rows.map(r => `${r.dpr},"${r.step}",${r.ms}`).join('\n') + '\n');
