// Phase 2 screenshots of dashboard/doom_map.html (Level 1) with Playwright driving the installed Edge.
// Usage: node map/build/shots_phase2.mjs   -> reports/figures/map_p2_*.png ; exits non-zero on page errors.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright-core';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.dirname(path.dirname(HERE));
const PAGE = 'file:///' + path.join(ROOT, 'dashboard', 'doom_map.html').split(path.sep).join('/');
const FIG = path.join(ROOT, 'reports', 'figures');
const errors = [];

async function open(browser, hash, { w = 1440, h = 980, scheme = 'light' } = {}) {
  const page = await browser.newPage({ viewport: { width: w, height: h }, colorScheme: scheme });
  page.on('pageerror', e => errors.push(`${hash}: ${e.message}`));
  page.on('console', m => { if (m.type() === 'error') errors.push(`${hash}: ${m.text()}`); });
  await page.goto(PAGE + '#' + hash);
  await page.waitForFunction(() => document.querySelector('#doom-map')?.dataset.painted, null, { timeout: 30000 });
  await page.waitForTimeout(150);
  return page;
}
async function hoverRegion(page, id, dx = 0, dy = 0) {
  const p = await page.evaluate(({ id, dx, dy }) => {
    const el = document.querySelector(`#dm-svg [data-region="${id}"]`), b = el.getBBox(), r = document.querySelector('#dm-svg').getBoundingClientRect();
    // a point inside the region: centre of its bbox nudged until it hits the path
    for (let k = 0; k < 60; k++) {
      const x = r.left + b.x + b.width * (0.5 + dx) + (k % 8 - 4) * 6, y = r.top + b.y + b.height * (0.5 + dy) + (Math.floor(k / 8) - 4) * 6;
      const hit = document.elementFromPoint(x, y);
      if (hit && hit.getAttribute('data-region') === id) return { x, y };
    }
    return { x: r.left + b.x + b.width / 2, y: r.top + b.y + b.height / 2 };
  }, { id, dx, dy });
  await page.mouse.move(p.x - 5, p.y - 5); await page.mouse.move(p.x, p.y);
  await page.waitForTimeout(120);
}
const shot = async (page, name) => { await page.screenshot({ path: path.join(FIG, `map_p2_${name}.png`) }); console.log('wrote', `map_p2_${name}.png`); };

const browser = await chromium.launch({ channel: 'msedge' });
for (const [theme, pal] of [['light', 'default'], ['dark', 'default'], ['light', 'greenred'], ['dark', 'greenred']]) {
  const page = await open(browser, `theme=${theme}&palette=${pal}`, { scheme: theme });
  await shot(page, `overview_${pal}_${theme}`); await page.close();
}
{ const page = await open(browser, 'theme=light&palette=default');
  await hoverRegion(page, 'new-york'); await shot(page, 'hover_region_newyork_light');
  await hoverRegion(page, 'prairies', -0.1, 0.25); await shot(page, 'hover_region_prairies_light');
  await page.hover('#dm-rows li[data-region="southeast"]'); await page.waitForTimeout(120); await shot(page, 'hover_list_southeast_light');
  await page.close(); }
{ const page = await open(browser, 'theme=dark&palette=default', { scheme: 'dark' });
  await hoverRegion(page, 'socal'); await shot(page, 'hover_region_socal_dark'); await page.close(); }
{ const page = await open(browser, 'season=2026&theme=light&palette=default');
  await shot(page, 'mlb_only_2026_light'); await page.close(); }
{ const page = await open(browser, 'theme=light&palette=default&leagues=NHL');
  await shot(page, 'nhl_only_toggle_light'); await page.close(); }
{ const page = await open(browser, 'theme=light&palette=default', { w: 390, h: 1500 });
  await shot(page, 'phone_light'); await page.close(); }
await browser.close();
if (errors.length) { console.error('PAGE ERRORS:\n' + errors.join('\n')); process.exit(1); }
console.log('no page errors');
