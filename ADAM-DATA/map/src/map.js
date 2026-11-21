/* Doom Map: Level 1 (continent overview) and Level 2 (region zoom with team logos).
 * Reads window.DOOM_MAP_DATA (built by map/build/build_page.mjs). Leagues, seasons, regions and teams all come from
 * the data; nothing here names a league. Heat surface: heat.js + heat_cache.js. Decisions: docs/MAP_DECISIONS.md.
 */
(function () {
  'use strict';
  const D = window.DOOM_MAP_DATA, X = D.derived, H = window.DoomHeat;
  const LEAGUES = X.leagues.slice().sort((a, b) => (D.leagues[a]?.order ?? 99) - (D.leagues[b]?.order ?? 99));
  const REG = new Map(D.regions.map(r => [r.region_id, r]));
  const V_LO = X.verdict_lo, V_HI = X.verdict_hi;            // M28: tertiles of pooled raw region averages
  const LEVEL_IN = 1.8, LEVEL_OUT = 1.4;                       // M38: zoom thresholds with hysteresis
  const LOGO_R = 20, RING_W = 5;                               // constant on-screen logo size (px)
  const REDUCED = matchMedia('(prefers-reduced-motion: reduce)');
  const state = { season: X.default_season, leagues: new Set(LEAGUES), palette: 'default', theme: 'auto', hover: null,
    hoverFrom: null, level: 1, focus: null, monograms: false, active: false, team: null, timeScale: 1 };

  // ---------- URL hash ----------
  let pendingRegion = null;
  (function readHash() {
    const p = new URLSearchParams(location.hash.slice(1));
    if (p.has('season') && X.seasons.includes(+p.get('season'))) state.season = +p.get('season');
    if (p.has('leagues')) { const l = p.get('leagues').split(',').filter(x => LEAGUES.includes(x)); state.leagues = new Set(l); }
    if (p.has('palette') && D.palette.palettes[p.get('palette')]) state.palette = p.get('palette');
    if (['auto', 'light', 'dark'].includes(p.get('theme'))) state.theme = p.get('theme');
    if (p.get('logos') === 'monograms') state.monograms = true;
    if (p.has('region') && REG.has(p.get('region'))) pendingRegion = p.get('region');
  })();
  function writeHash() {
    const p = new URLSearchParams({ season: state.season, leagues: [...state.leagues].join(','), palette: state.palette, theme: state.theme });
    if (state.monograms) p.set('logos', 'monograms');
    if (state.level === 2 && state.focus) p.set('region', state.focus);
    history.replaceState(null, '', '#' + p.toString());
  }

  // ---------- helpers ----------
  const $ = s => document.querySelector(s);
  const el = (tag, attrs = {}, html) => { const e = document.createElement(tag); for (const k in attrs) e.setAttribute(k, attrs[k]); if (html != null) e.innerHTML = html; return e; };
  const esc = s => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const ord = n => { const s = ['th', 'st', 'nd', 'rd'], v = n % 100; return n + (s[(v - 20) % 10] || s[v] || s[0]); };
  const mean = a => a.length ? a.reduce((x, y) => x + y, 0) / a.length : null;
  const themeNow = () => state.theme !== 'auto' ? state.theme : (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
  const pal = () => D.palette.palettes[state.palette];
  const lut = () => pal().lut[themeNow()];
  const colorOf = z => lut()[Math.round(H.position(z, X.z_lo, X.z_hi) * 255)];
  const greyOf = () => pal()[themeNow()].grey;
  const words = z => z <= V_LO ? 'Bright future' : z >= V_HI ? 'Doomed' : 'Middling';
  const seasonLabel = (lg, s) => D.leagues[lg]?.season_spans_two_years ? `${s}–${String(s + 1).slice(2)}` : String(s);
  const leagueSeasons = lg => X.league_seasons[lg] || [];
  const ms = d => (REDUCED.matches ? 0 : d * state.timeScale);
  const logoOf = t => D.logos[`${t.league}|${t.franchise_id}|${t.season_team_name}`] || { mono: t.season_team_name.slice(0, 3).toUpperCase(), uri: null };
  const BAND_TXT = { 'Low': 'Low risk', 'Moderate': 'Moderate risk', 'High': 'High risk', 'Very high': 'Very high risk' };
  const bandText = b => BAND_TXT[b] || 'Risk band not available';

  // ---------- data views ----------
  const inView = (season, leagues) => D.teams.filter(t => t.season === season && leagues.has(t.league));
  function regionStats(season, leagues) {
    const ts = inView(season, leagues), scored = ts.filter(t => t.scored);
    const mu = mean(scored.map(t => t.z)) ?? 0;
    const out = new Map();
    for (const r of D.regions) out.set(r.region_id, { region: r, teams: [], tooNew: [], n: 0 });
    for (const t of ts) (t.scored ? out.get(t.region_id).teams : out.get(t.region_id).tooNew).push(t);
    for (const s of out.values()) {
      s.n = s.teams.length;
      if (!s.n) continue;
      s.rawZ = mean(s.teams.map(t => t.z)); s.rawDoom = mean(s.teams.map(t => t.doom));
      const B = X.eb_tau2 / (X.eb_tau2 + X.eb_s2_within / s.n);
      s.B = B; s.shrunk = mu + B * (s.rawZ - mu);
      s.best = s.teams.reduce((a, b) => (b.z < a.z ? b : a)); s.worst = s.teams.reduce((a, b) => (b.z > a.z ? b : a));
      s.quads = { 'Contender': 0, 'Cliff ahead': 0, 'Rising': 0, 'Stuck': 0 };
      for (const t of s.teams) if (t.quadrant) s.quads[t.quadrant]++;
      s.byLeague = {}; for (const t of s.teams) s.byLeague[t.league] = (s.byLeague[t.league] || 0) + 1;
    }
    const ranked = [...out.values()].filter(s => s.n).sort((a, b) => a.shrunk - b.shrunk || a.region.display_name.localeCompare(b.region.display_name));
    ranked.forEach((s, i) => { s.rank = i + 1; });
    return { byRegion: out, ranked, empty: [...out.values()].filter(s => !s.n), mu, scored, all: ts };
  }
  function regionTrend(region_id) {
    return X.seasons.map(s => {
      const ls = new Set([...state.leagues].filter(l => leagueSeasons(l).includes(s)));
      const z = D.teams.filter(t => t.season === s && ls.has(t.league) && t.scored && t.region_id === region_id).map(t => t.z);
      return { season: s, z: mean(z) };
    });
  }
  function regionChange(region_id) {
    const prev = state.season - 1;
    if (!X.seasons.includes(prev)) return null;
    const both = new Set([...state.leagues].filter(l => leagueSeasons(l).includes(prev) && leagueSeasons(l).includes(state.season)));
    const zOf = s => mean(D.teams.filter(t => t.season === s && both.has(t.league) && t.scored && t.region_id === region_id).map(t => t.z));
    const a = zOf(prev), b = zOf(state.season);
    if (a == null || b == null) return null;
    return { prev, delta: b - a };
  }
  const teamSeries = t => D.teams.filter(x => x.franchise_id === t.franchise_id && x.league === t.league).sort((a, b) => a.season - b.season);

  // ---------- DOM ----------
  const root = $('#doom-map');
  root.innerHTML = `
  <header class="dm-head"><h1>Doom Map</h1>
    <p>How doomed is your part of the country? Color shows the outlook for the next three seasons, blended from nearby
    ${LEAGUES.join(' and ')} teams. Hover a region for its story, click it to see its teams; the list ranks every region.</p></header>
  <div class="dm-controls" role="toolbar" aria-label="Map controls">
    <span><span class="lbl" id="lg-l">Leagues</span><span class="dm-seg" id="dm-leagues" role="group" aria-labelledby="lg-l"></span></span>
    <span class="dm-season"><span class="lbl" id="se-l">Season</span>
      <button id="dm-prev" aria-label="Previous season">&#9664;</button><select id="dm-season" aria-labelledby="se-l"></select>
      <button id="dm-next" aria-label="Next season">&#9654;</button></span>
    <span><span class="lbl" id="pa-l">Colors</span><span class="dm-seg" id="dm-palette" role="group" aria-labelledby="pa-l"></span></span>
    <span><span class="lbl" id="th-l">Theme</span><span class="dm-seg" id="dm-theme" role="group" aria-labelledby="th-l"></span></span>
    <span><span class="lbl" id="lo-l">Badges</span><span class="dm-seg" id="dm-logos" role="group" aria-labelledby="lo-l"></span></span>
    <span class="dm-tag" id="dm-mode">Predicted doom</span>
  </div>
  <div class="dm-main">
    <div class="dm-mapcol">
      <div class="dm-mapwrap" id="dm-wrap">
        <canvas id="dm-heat" aria-hidden="true"></canvas>
        <svg id="dm-svg" role="img" aria-label="Doom map of the US and southern Canada"></svg>
        <nav class="dm-crumb" id="dm-crumb" aria-label="Map level"></nav>
        <div class="dm-banner" id="dm-banner" role="status"></div>
        <div class="dm-hint" id="dm-hint">Click the map or hold Ctrl / ⌘ to zoom with the wheel</div>
        <div class="dm-empty" id="dm-empty">Pick at least one league to see the map.</div>
      </div>
      <div class="dm-legend" id="dm-legend"></div>
    </div>
    <aside class="dm-list" id="dm-list" aria-label="Regions ranked by outlook"></aside>
  </div>
  <div class="dm-card" id="dm-card" role="tooltip"></div>`;

  const segButtons = (host, items, isOn, onClick) => {
    host.innerHTML = '';
    for (const it of items) {
      const b = el('button', { type: 'button', 'aria-pressed': String(isOn(it.key)) }, esc(it.label));
      b.addEventListener('click', () => onClick(it.key)); host.appendChild(b);
    }
  };
  function drawControls() {
    segButtons($('#dm-leagues'), LEAGUES.map(l => ({ key: l, label: l })), k => state.leagues.has(k), k => {
      state.leagues.has(k) ? state.leagues.delete(k) : state.leagues.add(k); snapSeason(); update();
    });
    segButtons($('#dm-palette'), Object.keys(D.palette.palettes).map(k => ({ key: k, label: k === 'default' ? 'Colorblind-safe' : 'Green–red' })),
      k => state.palette === k, k => { state.palette = k; update(); });
    segButtons($('#dm-theme'), [['auto', 'Auto'], ['light', 'Light'], ['dark', 'Dark']].map(([key, label]) => ({ key, label })),
      k => state.theme === k, k => { state.theme = k; update(); });
    segButtons($('#dm-logos'), [['logos', 'Logos'], ['monograms', 'Monograms']].map(([key, label]) => ({ key, label })),
      k => (state.monograms ? 'monograms' : 'logos') === k, k => { state.monograms = k === 'monograms'; update(); });
    const seasons = availableSeasons(), sel = $('#dm-season');
    sel.innerHTML = seasons.map(s => `<option value="${s}"${s === state.season ? ' selected' : ''}>${s}</option>`).join('');
    $('#dm-prev').disabled = !seasons.length || state.season <= seasons[0];
    $('#dm-next').disabled = !seasons.length || state.season >= seasons[seasons.length - 1];
  }
  const availableSeasons = () => X.seasons.filter(s => [...state.leagues].some(l => leagueSeasons(l).includes(s)));
  function snapSeason() {
    const av = availableSeasons();
    if (av.length && !av.includes(state.season)) state.season = av.reduce((a, b) => Math.abs(b - state.season) < Math.abs(a - state.season) ? b : a);
  }
  $('#dm-season').addEventListener('change', e => { state.season = +e.target.value; update(); });
  $('#dm-prev').addEventListener('click', () => { const av = availableSeasons(), i = av.indexOf(state.season); if (i > 0) { state.season = av[i - 1]; update(); } });
  $('#dm-next').addEventListener('click', () => { const av = availableSeasons(), i = av.indexOf(state.season); if (i < av.length - 1) { state.season = av[i + 1]; update(); } });

  // ---------- map geometry and layers ----------
  const regionsFC = topojson.feature(D.topo, D.topo.objects.regions);
  const contextFC = topojson.feature(D.topo, D.topo.objects.context);
  const meshInner = topojson.mesh(D.topo, D.topo.objects.regions, (a, b) => a !== b && a.properties.region_id !== b.properties.region_id);
  const CROP = { type: 'Polygon', coordinates: [[[-127, 24], [-128, 56], [-60, 56], [-52, 47], [-66, 24], [-127, 24]]] };
  const makeProj = (w, h, k = 1) => d3.geoConicConformal().parallels([30, 52]).rotate([96, 0]).fitExtent([[8 * k, 8 * k], [w * k - 8 * k, h * k - 8 * k]], CROP);
  let W = 0, Hh = 0, proj, path, prepped = [], view = null, T = d3.zoomIdentity;
  const svg = d3.select('#dm-svg');
  const gWorld = svg.append('g').attr('class', 'dm-world');            // scaled with the camera
  const gContext = gWorld.append('g'), gOutline = gWorld.append('path'), gDim = gWorld.append('path'),
        gHl = gWorld.append('path'), gHit = gWorld.append('g');
  const gOver = svg.append('g');                                       // screen space: constant size
  const gDots = gOver.append('g'), gLeaders = gOver.append('g'), gLogos = gOver.append('g'), gLabels = gOver.append('g');

  function layout() {
    const wrap = $('#dm-wrap');
    W = wrap.clientWidth; Hh = Math.round(Math.min(780, W * (W < 640 ? 0.8 : 0.66)));
    wrap.style.height = Hh + 'px';
    proj = makeProj(W, Hh); path = d3.geoPath(proj);
    svg.attr('width', W).attr('height', Hh).attr('viewBox', `0 0 ${W} ${Hh}`);
    gContext.selectAll('path').data(contextFC.features).join('path').attr('d', path)
      .attr('fill', 'var(--context)').attr('stroke', 'var(--context-line)').attr('stroke-width', .5);
    gOutline.attr('d', path(meshInner)).attr('fill', 'none').attr('stroke', 'var(--outline)').attr('stroke-width', .8);
    gHit.selectAll('path').data(regionsFC.features, d => d.properties.region_id).join('path').attr('d', path)
      .attr('fill', 'transparent').attr('data-region', d => d.properties.region_id).style('cursor', 'pointer');
    zoom.extent([[0, 0], [W, Hh]]).translateExtent([[-W * 0.1, -Hh * 0.1], [W * 1.1, Hh * 1.1]]);
  }

  // ---------- heat (cached, M35) ----------
  const cache = window.DoomHeatCache({ sigma: X.sigma_mi, smooth: 2.5, workerSource: document.getElementById('dm-heat-src').textContent });
  const dprNow = () => Math.min(window.devicePixelRatio || 1, 2);
  const dataKey = (season, leagues) => season + '|' + [...leagues].sort().join(',');
  const styleKey = () => state.palette + '|' + themeNow();
  const tables = new Map();
  const tableFor = k => tables.get(k) || (tables.set(k, H.colorTable(lut(), greyOf())), tables.get(k));
  const colorOpts = () => ({ w0: X.opacity_w0, w1: X.opacity_w1, zlo: X.z_lo, zhi: X.z_hi, table: tableFor(styleKey()) });
  const teamsFor = (season, leagues) => D.teams.filter(t => t.season === season && leagues.has(t.league) && t.scored)
    .map(t => ({ lat: t.lat, lon: t.lon, z: t.z }));
  /** A cache view for camera transform t (identity = continent). Zoomed views keep their own sharp raster. */
  function viewFor(t) {
    const dpr = dprNow(), cw = Math.round(W * dpr), ch = Math.round(Hh * dpr), pc = makeProj(W, Hh, dpr);
    if (t.k <= 1.0001) return cache.view(`base:${cw}x${ch}`, cw, ch, Math.round(3 * dpr), p => pc.invert(p), g => d3.geoPath(pc, g)(regionsFC));
    const s = pc.scale(), tr = pc.translate();
    const pz = makeProj(W, Hh, dpr).scale(s * t.k).translate([tr[0] * t.k + t.x * dpr, tr[1] * t.k + t.y * dpr]);
    const key = `z:${cw}x${ch}:${t.k.toFixed(3)}:${Math.round(t.x)}:${Math.round(t.y)}`;
    rememberZoomView(key);
    return cache.view(key, cw, ch, Math.round(3 * dpr), p => pz.invert(p), g => d3.geoPath(pz, g)(regionsFC));
  }
  const zoomViews = [];
  function rememberZoomView(key) {                                    // keep the 30 most recent zoom views
    const i = zoomViews.indexOf(key); if (i >= 0) zoomViews.splice(i, 1); zoomViews.push(key);
    if (zoomViews.length > 30) { const keep = new Set(zoomViews.slice(-30)); zoomViews.splice(0, zoomViews.length - 30);
      cache.clearViews(k => !k.startsWith('z:') || keep.has(k)); }
  }
  let baseImg = null, sharp = null, heatJob = 0, prefetchTimer = 0, sharpTimer = 0;
  function drawHeat() {                                                // composite: sharp raster if it matches T, else scaled base
    const cv = $('#dm-heat'), dpr = dprNow(), cw = Math.round(W * dpr), ch = Math.round(Hh * dpr);
    if (cv.width !== cw || cv.height !== ch) { cv.width = cw; cv.height = ch; cv.style.width = W + 'px'; cv.style.height = Hh + 'px'; }
    const ctx = cv.getContext('2d'); ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.clearRect(0, 0, cw, ch);
    if (sharp && sharp.k === T.k && sharp.x === T.x && sharp.y === T.y) { ctx.drawImage(sharp.img, 0, 0); return; }
    if (!baseImg) return;
    ctx.imageSmoothingEnabled = true; ctx.imageSmoothingQuality = 'high';
    ctx.drawImage(baseImg, T.x * dpr, T.y * dpr, baseImg.width * T.k, baseImg.height * T.k);
  }
  function paintHeat() {
    const job = ++heatJob, dk = dataKey(state.season, state.leagues), teams = teamsFor(state.season, state.leagues), t0 = performance.now();
    cache.image(viewFor(d3.zoomIdentity), dk, teams, styleKey(), colorOpts(), 0).then(img => {
      if (job !== heatJob) return;
      baseImg = img; sharp = null; drawHeat(); requestSharp(0);
      root.dataset.painted = String(job); root.dataset.paintMs = String(Math.round(performance.now() - t0));
      clearTimeout(prefetchTimer); prefetchTimer = setTimeout(prefetch, 50);
    });
  }
  /** Sharp raster for the current (or a given target) transform; drawn when it arrives and still matches. */
  function requestSharp(delay, target) {
    clearTimeout(sharpTimer);
    const t = target || T;
    if (t.k <= 1.0001) { sharp = null; return Promise.resolve(); }
    return new Promise(res => {
      sharpTimer = setTimeout(() => {
        const v = viewFor(t), dk = dataKey(state.season, state.leagues), job = heatJob;
        cache.image(v, dk, teamsFor(state.season, state.leagues), styleKey(), colorOpts(), 0).then(img => {
          if (job === heatJob && t.k === T.k && t.x === T.x && t.y === T.y) { sharp = { k: t.k, x: t.x, y: t.y, img }; drawHeat(); }
          res();
        });
      }, delay);
    });
  }
  function prefetch() {
    const v = viewFor(d3.zoomIdentity), seasons = availableSeasons().slice().sort((a, b) => Math.abs(a - state.season) - Math.abs(b - state.season));
    root.dataset.prefetched = '';
    seasons.forEach((s, i) => cache.field(v, dataKey(s, state.leagues), teamsFor(s, state.leagues), 10 + i));
    const near = seasons.slice(1, 3), sk = styleKey(), co = colorOpts();
    const idle = cb => (window.requestIdleCallback || (f => setTimeout(f, 30)))(cb);
    (function next(k) {
      if (k >= near.length) {
        Promise.all(seasons.map(s => cache.field(v, dataKey(s, state.leagues), teamsFor(s, state.leagues), 20))).then(() => {
          root.dataset.prefetched = '1';
          // then the region zoom views for the current season, so clicking a region finds its raster ready
          const dk = dataKey(state.season, state.leagues), tm = teamsFor(state.season, state.leagues);
          D.regions.forEach((r, i) => idle(() => cache.field(viewFor(regionTransform(r.region_id)), dk, tm, 40 + i)));
        });
        return;
      }
      cache.field(v, dataKey(near[k], state.leagues), teamsFor(near[k], state.leagues), 5).then(() =>
        idle(() => cache.image(v, dataKey(near[k], state.leagues), teamsFor(near[k], state.leagues), sk, co, 5).then(() => next(k + 1))));
    })(0);
  }

  // ---------- legend, banner ----------
  function drawLegend() {
    const L = lut(), stops = L.filter((_, i) => i % 15 === 0 || i === 255).map((c, i, a) => `${c} ${(i / (a.length - 1) * 100).toFixed(1)}%`);
    const shown = [...state.leagues].filter(l => leagueSeasons(l).includes(state.season)).map(l => `${l} ${seasonLabel(l, state.season)}`);
    $('#dm-legend').innerHTML = `
      <div class="ends"><span>Bright future</span><span>Doomed</span></div>
      <span class="ramp" style="display:block;background:linear-gradient(90deg,${stops.join(',')})"></span>
      <div class="row"><span class="sw"><span class="grey" style="background:${greyOf()}"></span>No teams nearby</span>
        <span class="sw"><span class="ring"></span>Too new to score</span></div>
      <div class="note">Colors compare teams within their league, then across leagues.</div>
      <div class="showing">Showing <b>predicted</b> doom${shown.length ? ': ' + esc(shown.join(' · ')) : ''}</div>`;
  }
  function drawBanner() {
    const sel = [...state.leagues], present = sel.filter(l => leagueSeasons(l).includes(state.season)), missing = sel.filter(l => !present.includes(l));
    const b = $('#dm-banner');
    if (!present.length || !missing.length) { b.style.display = 'none'; return; }
    const why = missing.map(l => { const s = leagueSeasons(l); return `${l} predictions cover ${s[0]}–${s[s.length - 1]}`; }).join('; ');
    b.innerHTML = `${esc(present.join(' + '))} only this season <span style="font-weight:400">(${esc(why)})</span>`;
    b.style.display = 'block';
  }

  // ---------- side: ranked list (M29) or team panel (M41) ----------
  function drawSide() { state.team ? drawTeamPanel() : drawList(); }
  function drawList() {
    const host = $('#dm-list'), R = view.ranked, BW = 120, C0 = BW / 2;
    host.classList.remove('dm-panel'); host.setAttribute('aria-label', 'Regions ranked by outlook');
    const ext = Math.max(0.25, ...R.map(s => Math.max(Math.abs(s.rawZ), Math.abs(s.shrunk))));
    const sx = v => C0 + v / ext * (C0 - 5);
    const bar = s => `<svg width="${BW}" height="16" aria-hidden="true">
      <line x1="${C0}" x2="${C0}" y1="0" y2="16" stroke="var(--muted)" stroke-opacity=".6"/>
      <rect x="${Math.min(sx(s.shrunk), C0)}" y="4" width="${Math.max(2, Math.abs(sx(s.shrunk) - C0))}" height="8" rx="1.5" fill="var(--ink)" fill-opacity=".7"/>
      <circle cx="${sx(s.rawZ)}" cy="8" r="4" fill="${colorOf(s.rawZ)}" stroke="var(--ink)" stroke-width="1.2"/></svg>`;
    host.innerHTML = `<h2>Regions ranked by outlook</h2>
      <p class="sub">Brightest first, by a reliability-adjusted average (bar): regions with few teams are pulled toward the
      overall average. Dot = raw average of the region's teams, in its map color. Center line = league average. n = teams scored.
      Click a region to zoom in.</p>
      <p class="sub caption"><b>Most differences between regions are within what chance alone would produce.</b></p>
      <div class="axis"><span></span><span></span><span><i>&larr; brighter</i><i>doomier &rarr;</i></span><span>n</span></div>
      <ol class="dm-rows" id="dm-rows">${R.map(s => `<li tabindex="0" data-region="${s.region.region_id}"
        aria-label="${esc(`${ord(s.rank)}: ${s.region.display_name}, ${words(s.rawZ)}, ${s.n} team${s.n === 1 ? '' : 's'}`)}">
        <span class="rk">${s.rank}</span><span class="nm">${esc(s.region.display_name)}</span>${bar(s)}<span class="n">${s.n}</span></li>`).join('')}</ol>
      ${view.empty.length ? `<h3>No scored teams this season</h3><ul class="dm-rows empty">${view.empty.map(s =>
        `<li><span class="rk">&ndash;</span><span class="nm">${esc(s.region.display_name)}${s.tooNew.length ? ` (${s.tooNew.length} too new)` : ''}</span></li>`).join('')}</ul>` : ''}`;
    for (const li of host.querySelectorAll('#dm-rows li')) {
      const id = li.dataset.region;
      li.addEventListener('mouseenter', () => state.level === 1 && setHover(id, 'list'));
      li.addEventListener('focus', () => state.level === 1 && setHover(id, 'list'));
      li.addEventListener('mouseleave', () => setHover(null));
      li.addEventListener('blur', () => setHover(null));
      li.addEventListener('click', () => zoomToRegion(id));
      li.addEventListener('keydown', e => { if (e.key === 'Enter') zoomToRegion(id); });
    }
    markListFocus();
  }
  const markListFocus = () => { for (const li of document.querySelectorAll('#dm-rows li')) li.classList.toggle('on', li.dataset.region === (state.hover || (state.level === 2 ? state.focus : null))); };

  function teamTrendSvg(t, w = 128, h = 30) {
    const ser = teamSeries(t).filter(x => x.doom != null);
    if (ser.length < 2) return '';
    const x = d3.scaleLinear().domain(d3.extent(ser, d => d.season)).range([3, w - 3]), y = d3.scaleLinear().domain([0, 100]).range([h - 3, 3]);
    const cur = ser.find(d => d.season === t.season);
    return `<svg width="${w}" height="${h}" aria-label="Predicted doom across seasons">
      <line x1="3" x2="${w - 3}" y1="${y(50)}" y2="${y(50)}" stroke="var(--line)" stroke-dasharray="2 2"/>
      <path d="${d3.line().x(d => x(d.season)).y(d => y(d.doom))(ser)}" fill="none" stroke="var(--muted)" stroke-width="1.4"/>
      ${cur ? `<circle cx="${x(cur.season)}" cy="${y(cur.doom)}" r="3.4" fill="${colorOf(cur.z)}" stroke="var(--ink)"/>` : ''}</svg>`;
  }
  const scatterLink = t => `doom_scatter.html#league=${encodeURIComponent(t.league)}&season=${t.season}&y=doom&team=${encodeURIComponent(t.franchise_id)}`;
  function drawTeamPanel() {
    const t = state.team, host = $('#dm-list');
    host.classList.add('dm-panel'); host.setAttribute('aria-label', 'Team details');
    const r = REG.get(t.region_id);
    host.innerHTML = `<button class="backlink" id="dm-panel-back">&larr; All regions list</button>
      <h2>${esc(t.season_team_name)}</h2>
      <div class="k">${esc(t.league)} ${esc(seasonLabel(t.league, t.season))} · ${esc(t.city)} · ${esc(r ? r.display_name : '')}</div>
      ${t.scored ? `<div class="big"><b>${Math.round(t.doom)}</b><span>predicted doom of 100</span></div>
        <span class="chip" style="box-shadow:inset 4px 0 0 ${colorOf(t.z)}">${bandText(t.band)} of a doomed stretch</span>
        <table>
          <tr><td>Likely range (80%)</td><td>${t.lo80 != null ? `${Math.round(t.lo80)}–${Math.round(t.hi80)}` : 'not available'}</td></tr>
          <tr><td>This season</td><td>${t.win_pct != null ? (t.win_pct * 100).toFixed(1) + '% wins' : '–'} (${t.wpp != null ? ord(Math.round(t.wpp)) + ' percentile' : '–'})</td></tr>
          <tr><td>Scatter quadrant</td><td>${esc(t.quadrant || '–')}</td></tr>
          <tr><td>Doom over seasons</td><td>${teamTrendSvg(t, 150, 36)}</td></tr>
        </table>` : `<p>Too new to score: no prediction for this season, so this team is left out of every average.</p>`}
      <p><a href="${scatterLink(t)}">Open in the doom scatter &#8599;</a> <span class="k">(highlights this team)</span></p>`;
    $('#dm-panel-back').addEventListener('click', () => { state.team = null; drawSide(); markLogoOn(); });
  }

  // ---------- hover cards ----------
  function placeCard(card, pt, anchor) {
    card.style.display = 'block';
    let x, y;
    if (pt) { x = pt.clientX + 16; y = pt.clientY + 16; } else { x = anchor[0] + 12; y = anchor[1] + 12; }
    const cw = card.offsetWidth, chh = card.offsetHeight;
    if (x + cw > innerWidth - 8) x = (pt ? pt.clientX - 16 : x - 24) - cw;
    if (y + chh > innerHeight - 8) y = Math.max(8, innerHeight - 8 - chh);
    card.style.left = Math.max(8, x) + 'px'; card.style.top = y + 'px';
  }
  function setHover(id, from, pt) {
    state.hover = id; state.hoverFrom = from;
    drawFocusLayers();
    markListFocus();
    if (from === 'map' && id) { const li = document.querySelector(`#dm-rows li[data-region="${id}"]`); if (li) li.scrollIntoView({ block: 'nearest' }); }
    const card = $('#dm-card');
    if (!id) { card.style.display = 'none'; return; }
    const me = regionsFC.features.find(f => f.properties.region_id === id);
    card.innerHTML = cardHtml(view.byRegion.get(id), pt);
    const r = $('#dm-wrap').getBoundingClientRect(), c = T.apply(path.centroid(me));
    placeCard(card, pt, [r.left + c[0], r.top + c[1]]);
  }
  function spark(region_id) {
    const tr = regionTrend(region_id), pts = tr.filter(p => p.z != null);
    if (pts.length < 2) return '';
    const w = 128, h = 30, x = d3.scaleLinear().domain(d3.extent(X.seasons)).range([3, w - 3]);
    const y = d3.scaleLinear().domain([X.z_lo, X.z_hi]).range([h - 3, 3]).clamp(true);
    const line = d3.line().defined(p => p.z != null).x(p => x(p.season)).y(p => y(p.z))(tr);
    const cur = tr.find(p => p.season === state.season);
    return `<svg width="${w}" height="${h}" aria-label="Trend of the region's average across seasons">
      <line x1="3" x2="${w - 3}" y1="${y(0)}" y2="${y(0)}" stroke="var(--line)" stroke-dasharray="2 2"/>
      <path d="${line}" fill="none" stroke="var(--muted)" stroke-width="1.4"/>
      ${cur && cur.z != null ? `<circle cx="${x(cur.season)}" cy="${y(cur.z)}" r="3.4" fill="${colorOf(cur.z)}" stroke="var(--ink)" stroke-width="1"/>` : ''}</svg>`;
  }
  function spotHtml(pt) {
    if (!pt) return '';
    const r = $('#dm-wrap').getBoundingClientRect(), ll = proj.invert(T.invert([pt.clientX - r.left, pt.clientY - r.top]));
    if (!ll || !prepped.length) return '';
    const ws = H.weightsAt(ll, prepped, X.sigma_mi), tot = ws.reduce((a, b) => a + b.w, 0);
    const near = ws.slice().sort((a, b) => a.d - b.d).slice(0, 3);
    const nearTxt = near.map(n => `${esc(n.team.season_team_name)} <span>${Math.round(n.d)} mi</span>`).join(' · ');
    if (tot < X.opacity_w0) return `<div class="spot">No teams nearby at this spot. Nearest: ${nearTxt}</div>`;
    const k = ws.filter(w => w.w / tot >= 0.05).length;
    return `<div class="spot">At this spot: <b>${k} team${k === 1 ? '' : 's'}</b> shape the color (≥5% each). Nearest: ${nearTxt}</div>`;
  }
  function cardHtml(s, pt) {
    const r = s.region, lg = Object.entries(s.byLeague || {}).map(([l, c]) => `${c} ${l}`).join(', ');
    const tooNew = s.tooNew.length ? `${s.tooNew.length} too new to score (not in the average)` : 'none too new to score';
    if (!s.n) return `<div class="t">${esc(r.display_name)}</div><div class="k">${esc(r.core_metros)}</div>
      <div class="verdict"><span class="chipc" style="background:${greyOf()}"></span><span>No scored ${esc([...state.leagues].join('/'))} teams this season</span></div>
      <div class="k">${tooNew}. Not ranked.</div>${spotHtml(pt)}`;
    const ch = regionChange(r.region_id);
    const chTxt = !ch ? '<span class="k">no comparable previous season</span>'
      : Math.abs(ch.delta) < 0.05 ? `≈ unchanged since ${ch.prev}`
      : ch.delta > 0 ? `<b style="color:${colorOf(1.4)}">▲</b> more doomed than in ${ch.prev}`
      : `<b style="color:${colorOf(-1.4)}">▼</b> brighter than in ${ch.prev}`;
    const team = t => `${esc(t.season_team_name)} <span class="k">${t.league} · doom ${Math.round(t.doom)}</span>`;
    const q = s.quads;
    return `<div class="t">${esc(r.display_name)}</div><div class="k">${esc(r.core_metros)}</div>
      <div class="verdict"><span class="chipc" style="background:${colorOf(s.rawZ)}"></span>
        <span class="big">${words(s.rawZ)}</span><span>average doom <b>${Math.round(s.rawDoom)}</b> <span class="k">of 100</span></span></div>
      <span class="rank">${ord(s.rank)} brightest of ${view.ranked.length}</span>${s.n === 1 ? ' <span class="rank one">based on 1 team</span>' : ''}
      <table>
        <tr><td>Based on</td><td><b>${s.n === 1 ? '1 team' : s.n + ' teams'}</b> (${esc(lg)}); ${tooNew}${s.n === 2 ? '. <i>Few teams: treat with care.</i>' : ''}</td></tr>
        <tr><td>Best hope</td><td>${team(s.best)}</td></tr>
        ${s.n > 1 ? `<tr><td>Biggest worry</td><td>${team(s.worst)}</td></tr>` : ''}
      </table>
      <div class="quad">${['Contender', 'Cliff ahead', 'Rising', 'Stuck'].map(k => `<div><b>${q[k]}</b>${k}</div>`).join('')}</div>
      <div class="trend">${spark(r.region_id)}<span>${chTxt}</span></div>${spotHtml(pt)}
      <div class="k" style="margin-top:6px">Click to zoom in.</div>`;
  }
  function teamCardHtml(t) {
    const r = REG.get(t.region_id);
    if (!t.scored) return `<div class="t">${esc(t.season_team_name)}</div><div class="k">${esc(t.league)} ${esc(seasonLabel(t.league, t.season))} · ${esc(t.city)}</div>
      <p style="margin:6px 0 0">Too new to score: no prediction this season; not in any average.</p>`;
    return `<div class="t">${esc(t.season_team_name)}</div>
      <div class="k">${esc(t.league)} ${esc(seasonLabel(t.league, t.season))} · ${esc(t.city)} · ${esc(r ? r.display_name : '')}</div>
      <div class="verdict"><span class="chipc" style="background:${colorOf(t.z)}"></span>
        <span class="big">${Math.round(t.doom)}</span><span>predicted doom of 100 · <span class="band">${bandText(t.band)}</span></span></div>
      <table>
        <tr><td>This season</td><td>${t.win_pct != null ? (t.win_pct * 100).toFixed(1) + '% wins' : '–'}</td></tr>
        <tr><td>Quadrant</td><td>${esc(t.quadrant || '–')}</td></tr>
      </table>
      <div class="trend">${teamTrendSvg(t)}<span class="k">doom over seasons</span></div>
      <div class="k" style="margin-top:6px">Click for details.</div>`;
  }

  // ---------- region focus layers (hover dim at level 1, focus dim at level 2) ----------
  function drawFocusLayers() {
    const id = state.level === 2 ? state.focus : state.hover;
    const others = { type: 'FeatureCollection', features: regionsFC.features.filter(f => f.properties.region_id !== id) };
    const me = regionsFC.features.find(f => f.properties.region_id === id);
    gDim.attr('d', id ? path(others) : null).attr('fill', 'var(--dim)').attr('pointer-events', 'none');
    gHl.attr('d', me ? path(me) : null).attr('fill', 'none').attr('stroke', 'var(--ink)').attr('stroke-width', 2).attr('pointer-events', 'none');
  }

  svg.on('pointermove', ev => {
    if (state.level === 2) return;
    const t = ev.target.closest && ev.target.closest('[data-region]');
    if (t) setHover(t.getAttribute('data-region'), 'map', ev);
    else if (state.hoverFrom === 'map') setHover(null);
  });
  svg.on('pointerleave', () => { if (state.hoverFrom === 'map') setHover(null); });
  svg.on('click', ev => {
    const t = ev.target.closest && ev.target.closest('[data-region]');
    activate(true);
    if (t && !ev.target.closest('.dm-logo')) zoomToRegion(t.getAttribute('data-region'));
  });

  // ---------- camera: d3.zoom (M37-M39) ----------
  function showHint() { const h = $('#dm-hint'); h.classList.add('on'); clearTimeout(showHint.t); showHint.t = setTimeout(() => h.classList.remove('on'), 1300); }
  function activate(on) { state.active = on; $('#dm-wrap').classList.toggle('active', on); }
  document.addEventListener('pointerdown', e => { if (!$('#dm-wrap').contains(e.target)) activate(false); });
  // wheel: one mouse notch (~100 px) = x1.5; small Ctrl+wheel deltas are trackpad pinches and get d3's usual x10
  const zoom = d3.zoom().scaleExtent([1, 14]).clickDistance(4)
    .wheelDelta(ev => -ev.deltaY * (ev.deltaMode === 1 ? 0.05 : ev.deltaMode ? 1 : 0.002) * Math.min(3, (ev.ctrlKey && Math.abs(ev.deltaY) < 20) ? 10 : 1) * 2.9)
    .filter(ev => {
      if (ev.type === 'wheel') { if (state.active || ev.ctrlKey || ev.metaKey) return true; showHint(); return false; }
      if (ev.type === 'dblclick') return false;
      if (ev.type.startsWith('touch')) return state.active || (ev.touches && ev.touches.length > 1);
      return !ev.button;
    })
    .on('zoom', ev => { T = ev.transform; onCamera(); })
    .on('end', () => { if (!animating) settle(); });
  svg.call(zoom).on('dblclick.zoom', null);
  let animating = false;

  function onCamera() {
    gWorld.attr('transform', T.toString());
    drawHeat();
    if (!animating) {                                                  // free zoom: level follows the zoom amount
      if (state.level === 1 && T.k >= LEVEL_IN) enterLevel2(regionAtCenter(), false);
      else if (state.level === 2 && T.k < LEVEL_OUT) exitLevel2();
      else if (state.level === 2 && T.k >= LEVEL_IN) { const r = regionAtCenter(); if (r && r !== state.focus) { state.focus = r; drawFocusLayers(); drawCrumb(); } }
    }
    positionOverlay();
  }
  function settle() { requestSharp(120); writeHash(); }
  function regionAtCenter() {
    const ll = proj.invert(T.invert([W / 2, Hh / 2]));
    const hit = ll && regionsFC.features.find(f => d3.geoContains(f, ll));
    if (hit) return hit.properties.region_id;
    let best = null, bd = Infinity;                                    // over water: nearest region centroid on screen
    for (const f of regionsFC.features) { const c = T.apply(path.centroid(f)), d = (c[0] - W / 2) ** 2 + (c[1] - Hh / 2) ** 2; if (d < bd) { bd = d; best = f.properties.region_id; } }
    return best;
  }
  /** Camera target for a region: its venues (padded, at least ~22% of the map), else its shape inside the crop. */
  function regionTransform(id) {
    const pts = D.teams.filter(t => t.region_id === id && t.season === state.season && state.leagues.has(t.league)).map(t => proj([t.lon, t.lat]));
    let x0, y0, x1, y1;
    if (pts.length) { [x0, x1] = d3.extent(pts, p => p[0]); [y0, y1] = d3.extent(pts, p => p[1]); }
    else {
      const f = regionsFC.features.find(f => f.properties.region_id === id), [[a, b], [c, d]] = path.bounds(f);
      x0 = Math.max(a, 0); y0 = Math.max(b, 0); x1 = Math.min(c, W); y1 = Math.min(d, Hh);
    }
    const cx = (x0 + x1) / 2, cy = (y0 + y1) / 2;
    const bw = Math.max(x1 - x0 + 160, W * 0.22), bh = Math.max(y1 - y0 + 160, Hh * 0.22);
    const k = Math.max(LEVEL_IN + 0.1, Math.min(8, 0.9 * Math.min(W / bw, Hh / bh)));
    const t = d3.zoomIdentity.translate(W / 2 - k * cx, Hh / 2 - k * cy).scale(k);
    return d3.zoomIdentity.translate(Math.round(t.x), Math.round(t.y)).scale(+k.toFixed(3));
  }

  /** Animated zoom (M39): highlight + dim, camera move (van Wijk: zooms out first on long jumps), staggered reveal. */
  function zoomToRegion(id) {
    if (!id || !REG.has(id)) return;
    setHover(null);
    const target = regionTransform(id), t0 = performance.now();
    state.focus = id; state.level = 2; state.team = null;
    $('#dm-wrap').classList.add('level2'); drawFocusLayers(); drawCrumb(); drawSide(); hideLogos();
    requestSharp(0, target);                                           // raster for the destination starts now
    animating = true;
    const run = () => {
      const tr = svg.transition('camera').duration(ms(Math.min(600, Math.max(380, 600 * dist(T, target)))))
        .ease(d3.easeCubicInOut).call(zoom.transform, target);
      tr.on('end interrupt', () => {
        animating = false; settle(); revealLogos(); writeHash();
        root.dataset.zoomMs = String(Math.round(performance.now() - t0));
      });
    };
    ms(100) ? setTimeout(run, ms(100)) : run();
  }
  const dist = (a, b) => Math.min(1, (Math.hypot((a.x - b.x) / W, (a.y - b.y) / Hh) + Math.abs(Math.log(a.k / b.k)) / 3));
  function zoomOut() {
    state.team = null;
    animating = true; exitLevel2();
    svg.transition('camera').duration(ms(550)).ease(d3.easeCubicInOut).call(zoom.transform, d3.zoomIdentity)
      .on('end interrupt', () => { animating = false; settle(); });
  }
  function enterLevel2(id, animated) {
    state.level = 2; state.focus = id;
    $('#dm-wrap').classList.add('level2'); drawFocusLayers(); drawCrumb(); drawSide();
    if (!animated) revealLogos(true);
  }
  function exitLevel2() {
    state.level = 1; state.focus = null;
    $('#dm-wrap').classList.remove('level2'); hideLogos(); drawFocusLayers(); drawCrumb(); drawSide(); writeHash();
  }
  document.addEventListener('keydown', e => {
    if (e.key !== 'Escape') return;
    if (state.team) { state.team = null; drawSide(); markLogoOn(); }
    else if (state.level === 2) zoomOut();
    else activate(false);
  });

  function drawCrumb() {
    const c = $('#dm-crumb');
    if (state.level === 1) { c.innerHTML = `<button disabled>All regions</button>`; return; }
    c.innerHTML = `<button class="back" id="dm-back" aria-label="Zoom out to all regions">&larr; Back</button>
      <button id="dm-all">All regions</button><span class="sep">›</span><button disabled>${esc(REG.get(state.focus)?.display_name || '')}</button>`;
    $('#dm-back').addEventListener('click', zoomOut); $('#dm-all').addEventListener('click', zoomOut);
  }

  // ---------- logos (Level 2, M40) ----------
  const preload = Promise.all(Object.values(D.logos).filter(l => l.uri).map(l => { const im = new Image(); im.src = l.uri; return im.decode().catch(() => null); }));
  let logoNodes = [];
  function buildLogos() {
    const teams = view.all;
    logoNodes = teams.map(t => ({ t, key: t.franchise_id + '|' + t.league }));
    const g = gLogos.selectAll('g.dm-logo').data(logoNodes, d => d.key).join(enter => {
      const e = enter.append('g').attr('class', 'dm-logo').attr('tabindex', 0).attr('role', 'button');
      e.append('circle').attr('class', 'halo').attr('r', LOGO_R + RING_W / 2 + 1.5);
      e.append('circle').attr('class', 'ring').attr('r', LOGO_R).attr('fill', 'none').attr('stroke-width', RING_W);
      e.append('circle').attr('class', 'plate').attr('r', LOGO_R - RING_W / 2);
      e.append('image').attr('x', -12.5).attr('y', -12.5).attr('width', 25).attr('height', 25).attr('preserveAspectRatio', 'xMidYMid meet');
      e.append('text').attr('class', 'mono');
      return e;
    });
    g.attr('aria-label', d => `${d.t.season_team_name}: ${d.t.scored ? `predicted doom ${Math.round(d.t.doom)}, ${bandText(d.t.band)}` : 'too new to score'}`);
    g.select('.ring').attr('stroke', d => d.t.scored ? colorOf(d.t.z) : '#8a909c').attr('stroke-dasharray', d => d.t.scored ? null : '4 3');
    g.each(function (d) {
      const lg = logoOf(d.t), useImg = lg.uri && !state.monograms;
      const im = d3.select(this).select('image').attr('href', useImg ? lg.uri : null).style('display', useImg ? null : 'none')
        .on('error', function () { d3.select(this).style('display', 'none'); d3.select(this.parentNode).select('.mono').style('display', null); });
      d3.select(this).select('.mono').text(lg.mono).style('display', useImg ? 'none' : null).attr('font-size', lg.mono.length > 3 ? 9 : 11);
      void im;
    });
    g.on('pointerenter', (ev, d) => { const c = $('#dm-card'); c.innerHTML = teamCardHtml(d.t); placeCard(c, ev); })
      .on('pointermove', (ev) => placeCard($('#dm-card'), ev))
      .on('pointerleave', () => { $('#dm-card').style.display = 'none'; })
      .on('focus', function (ev, d) { const c = $('#dm-card'), b = this.getBoundingClientRect(); c.innerHTML = teamCardHtml(d.t); placeCard(c, null, [b.right, b.top]); })
      .on('blur', () => { $('#dm-card').style.display = 'none'; })
      .on('click', (ev, d) => { ev.stopPropagation(); openTeam(d.t); })
      .on('keydown', (ev, d) => { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); openTeam(d.t); } });
    gLogos.style('display', state.level === 2 ? null : 'none');
    markLogoOn();
  }
  function openTeam(t) { state.team = t; drawSide(); markLogoOn(); $('#dm-card').style.display = 'none'; }
  const markLogoOn = () => gLogos.selectAll('g.dm-logo').classed('on', d => state.team && d.t.franchise_id === state.team.franchise_id && d.t.league === state.team.league);

  /** Screen-space layout: each metro is a rigid ring cluster; clusters are pushed apart as discs (no overlaps). */
  function layoutLogos() {
    const STEP = 2 * LOGO_R + RING_W + 3;                              // centre spacing of touching badges
    const metros = d3.groups(logoNodes, d => d.t.metro_id).map(([id, nodes]) => {
      nodes.sort((a, b) => (a.t.league + a.t.season_team_name).localeCompare(b.t.league + b.t.season_team_name));
      const anchors = nodes.map(d => T.apply(proj([d.t.lon, d.t.lat])));
      const c = [d3.mean(anchors, a => a[0]), d3.mean(anchors, a => a[1])], n = nodes.length;
      const r = n === 1 ? 0 : n === 2 ? STEP / 2 : STEP / (2 * Math.sin(Math.PI / n));
      nodes.forEach((d, i) => { d.anchor = anchors[i]; const a = -Math.PI / 2 + (2 * Math.PI * i) / n + (n === 2 ? Math.PI / 2 : 0); d.off = [r * Math.cos(a), r * Math.sin(a)]; });
      return { id, nodes, home: c, c: c.slice(), R: r + LOGO_R + RING_W / 2 + 2, name: nodes[0].t.metro };
    });
    for (let it = 0; it < 60; it++) {                                  // disc relaxation between metro clusters
      let moved = false;
      for (let i = 0; i < metros.length; i++) for (let j = i + 1; j < metros.length; j++) {
        const a = metros[i], b = metros[j], dx = b.c[0] - a.c[0], dy = b.c[1] - a.c[1], d = Math.hypot(dx, dy) || 0.01, need = a.R + b.R + 18;   // + room for the metro label under each cluster
        if (d < need) { const push = (need - d) / 2, ux = dx / d, uy = dy / d; a.c[0] -= ux * push; a.c[1] -= uy * push; b.c[0] += ux * push; b.c[1] += uy * push; moved = true; }
      }
      for (const m of metros) { m.c[0] += (m.home[0] - m.c[0]) * 0.02; m.c[1] += (m.home[1] - m.c[1]) * 0.02; }
      if (!moved) break;
    }
    for (const m of metros) for (const d of m.nodes) d.pos = [m.c[0] + d.off[0], m.c[1] + d.off[1]];
    return metros;
  }
  let metrosLaid = [];
  function positionOverlay() {
    // level-1 venue dots (screen space)
    gDots.style('display', state.level === 1 ? null : 'none');
    if (state.level === 1) {
      gDots.selectAll('circle').data(view.all, d => d.franchise_id + d.league).join('circle')
        .attr('cx', d => T.apply(proj([d.lon, d.lat]))[0]).attr('cy', d => T.apply(proj([d.lon, d.lat]))[1])
        .attr('r', d => d.scored ? 2.2 : 5).attr('fill', d => d.scored ? 'var(--ink)' : 'none')
        .attr('stroke', d => d.scored ? 'none' : '#8a909c').attr('stroke-width', 2.5).attr('opacity', d => d.scored ? .55 : 1).attr('pointer-events', 'none');
      gLeaders.selectAll('*').remove(); gLabels.selectAll('*').remove();
      return;
    }
    metrosLaid = layoutLogos();
    gLogos.selectAll('g.dm-logo').attr('transform', d => `translate(${d.pos[0]},${d.pos[1]})`)
      .classed('other', d => state.focus && d.t.region_id !== state.focus);
    gLabels.selectAll('text').classed('other', d => state.focus && d.nodes[0].t.region_id !== state.focus);
    const far = logoNodes.filter(d => Math.hypot(d.pos[0] - d.anchor[0], d.pos[1] - d.anchor[1]) > LOGO_R + 4);
    gLeaders.selectAll('g').data(far, d => d.key).join(e => { const g = e.append('g'); g.append('line').attr('class', 'dm-leader'); g.append('circle').attr('class', 'dm-venue').attr('r', 2.5); return g; })
      .each(function (d) { d3.select(this).select('line').attr('x1', d.anchor[0]).attr('y1', d.anchor[1]).attr('x2', d.pos[0]).attr('y2', d.pos[1]);
        d3.select(this).select('circle').attr('cx', d.anchor[0]).attr('cy', d.anchor[1]); });
    gLabels.selectAll('text').data(metrosLaid, d => d.id).join('text').attr('class', 'dm-metro')
      .classed('other', d => state.focus && d.nodes[0].t.region_id !== state.focus)
      .attr('x', d => d.c[0]).attr('y', d => d.c[1] + d.R + 13).text(d => d.name);
  }
  function hideLogos() { gLogos.style('display', 'none'); gLabels.style('display', 'none'); gLeaders.style('display', 'none'); }
  function revealLogos(instant) {
    preload.then(() => {
      if (state.level !== 2) return;
      positionOverlay();
      gLogos.style('display', null); gLabels.style('display', null); gLeaders.style('display', null);
      const c = [W / 2, Hh / 2], order = logoNodes.slice().sort((a, b) => Math.hypot(a.pos[0] - c[0], a.pos[1] - c[1]) - Math.hypot(b.pos[0] - c[0], b.pos[1] - c[1]));
      const rank = new Map(order.map((d, i) => [d.key, i])), step = Math.min(10, 150 / Math.max(1, order.length));
      const sel = gLogos.selectAll('g.dm-logo').interrupt();
      if (instant || !ms(1)) { sel.style('opacity', 1); return; }
      sel.style('opacity', 0).transition().delay(d => ms(rank.get(d.key) * step)).duration(ms(140)).style('opacity', 1);
      gLabels.style('opacity', 0).transition().delay(ms(120)).duration(ms(200)).style('opacity', 1);
    });
  }

  // ---------- update cycle ----------
  function update(opts = {}) {
    document.documentElement.dataset.theme = state.theme === 'auto' ? '' : state.theme;
    if (state.theme === 'auto') document.documentElement.removeAttribute('data-theme');
    view = regionStats(state.season, state.leagues);
    prepped = H.prepTeams(view.scored.map(t => ({ ...t })));
    if (state.team) state.team = view.all.find(t => t.franchise_id === state.team.franchise_id && t.league === state.team.league) || null;
    $('#dm-empty').style.display = state.leagues.size ? 'none' : 'flex';
    if (opts.layout) layout();
    gWorld.attr('transform', T.toString());
    drawControls(); drawLegend(); drawBanner(); drawSide(); drawCrumb(); drawFocusLayers(); buildLogos(); positionOverlay(); paintHeat();
    if (state.level === 2) revealLogos(true);
    if (state.hover && state.level === 1) setHover(state.hover, state.hoverFrom);
    writeHash();
  }
  matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => { if (state.theme === 'auto') update(); });
  let rt; new ResizeObserver(() => { clearTimeout(rt); rt = setTimeout(() => {
    cache.clearViews(); update({ layout: true });
    if (state.level === 2 && state.focus) { const t = regionTransform(state.focus); svg.call(zoom.transform, t); }
  }, 120); }).observe($('#dm-wrap'));
  snapSeason();
  update({ layout: true });
  if (pendingRegion) { const t = regionTransform(pendingRegion); state.focus = pendingRegion; animating = true; svg.call(zoom.transform, t); animating = false; enterLevel2(pendingRegion, true); settle(); revealLogos(true); }
  window.DoomMap = { state, update, setHover, regionStats, view: () => view, cache, zoomToRegion, zoomOut, transform: () => T, preload };
})();
