/* Doom dashboard: Doom Map (Level 1 continent, Level 2 region with team badges), projected-standing scatter and one
 * shared team panel, on one shared state (view, region, season, leagues, mode, team), all mirrored in the URL.
 * Reads window.DOOM_MAP_DATA (map/build/build_page.mjs). Leagues, seasons, regions and teams come from the data;
 * nothing here names a league. Heat surface: heat.js + heat_cache.js. Decisions: docs/MAP_DECISIONS.md.
 */
(function () {
  'use strict';
  const D = window.DOOM_MAP_DATA, X = D.derived, H = window.DoomHeat;
  const LEAGUES = X.leagues.slice().sort((a, b) => (D.leagues[a]?.order ?? 99) - (D.leagues[b]?.order ?? 99));
  const REG = new Map(D.regions.map(r => [r.region_id, r]));
  const V_LO = X.verdict_lo, V_HI = X.verdict_hi;            // M28
  const LEVEL_IN = 1.8, LEVEL_OUT = 1.4;                       // M38
  const LOGO_R = 20, RING_W = 5, PAD_MI = 150;                 // M40, M38 (frame padding)
  const REDUCED = matchMedia('(prefers-reduced-motion: reduce)');
  const SYMBOLS = [d3.symbolCircle, d3.symbolSquare, d3.symbolTriangle, d3.symbolDiamond, d3.symbolStar, d3.symbolWye];
  const SYM = new Map(LEAGUES.map((l, i) => [l, SYMBOLS[i % SYMBOLS.length]]));
  const state = { season: X.default_season, leagues: new Set(LEAGUES), palette: 'default', theme: 'auto', mode: 'predicted',
    view: 'both', hover: null, hoverFrom: null, level: 1, focus: null, monograms: false, active: false, team: null, timeScale: 1 };

  // ---------- URL state (M43) ----------
  let pendingRegion = null;
  (function readHash() {
    const p = new URLSearchParams(location.hash.slice(1));
    if (p.has('season') && X.seasons.includes(+p.get('season'))) state.season = +p.get('season');
    if (p.has('leagues')) state.leagues = new Set(p.get('leagues').split(',').filter(x => LEAGUES.includes(x)));
    if (p.has('palette') && D.palette.palettes[p.get('palette')]) state.palette = p.get('palette');
    if (['auto', 'light', 'dark'].includes(p.get('theme'))) state.theme = p.get('theme');
    if (['predicted', 'actual'].includes(p.get('mode'))) state.mode = p.get('mode');
    if (['both', 'map', 'scatter'].includes(p.get('view'))) state.view = p.get('view');
    if (p.get('logos') === 'monograms') state.monograms = true;
    if (p.has('region') && REG.has(p.get('region'))) pendingRegion = p.get('region');
    if (p.has('team')) { const [league, franchise_id] = p.get('team').split(':'); if (LEAGUES.includes(league) && franchise_id) state.team = { league, franchise_id }; }
  })();
  function writeHash() {
    const p = new URLSearchParams({ view: state.view, season: state.season, leagues: [...state.leagues].join(','), mode: state.mode });
    if (state.level === 2 && state.focus) p.set('region', state.focus);
    if (state.team) p.set('team', `${state.team.league}:${state.team.franchise_id}`);
    p.set('palette', state.palette); p.set('theme', state.theme);
    if (state.monograms) p.set('logos', 'monograms');
    history.replaceState(null, '', '#' + p.toString());
  }

  // ---------- helpers ----------
  const $ = s => document.querySelector(s);
  const el = (tag, attrs = {}, html) => { const e = document.createElement(tag); for (const k in attrs) e.setAttribute(k, attrs[k]); if (html != null) e.innerHTML = html; return e; };
  const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
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
  const actualSeasons = lg => X.actual_seasons[lg] || [];
  const ms = d => (REDUCED.matches ? 0 : d * state.timeScale);
  const logoOf = t => D.logos[`${t.league}|${t.franchise_id}|${t.season_team_name}`] || { mono: t.season_team_name.slice(0, 3).toUpperCase(), uri: null };
  const BAND_TXT = { 'Low': 'Low risk', 'Moderate': 'Moderate risk', 'High': 'High risk', 'Very high': 'Very high risk' };
  const bandText = b => BAND_TXT[b] || 'Risk band not available';
  const sameTeam = (a, b) => !!(a && b && a.league === b.league && a.franchise_id === b.franchise_id);
  let lastPointer = 'mouse';
  document.addEventListener('pointerdown', e => { lastPointer = e.pointerType || 'mouse'; }, true);
  const touchy = () => lastPointer === 'touch' || lastPointer === 'pen';

  // ---------- predicted vs actual (M44) ----------
  const actualLeaguesNow = () => [...state.leagues].filter(l => actualSeasons(l).includes(state.season));
  const isActual = () => state.mode === 'actual' && actualLeaguesNow().length > 0;
  const zOf = t => isActual() ? t.z_actual : t.z;
  const doomOf = t => isActual() ? t.actual_doom : t.doom;
  const hasVal = t => zOf(t) != null;
  const quadOf = t => { if (!hasVal(t) || t.wpp == null) return ''; const x = t.wpp >= 50, y = 100 - doomOf(t) >= 50;
    return x && y ? 'Contender' : x ? 'Cliff ahead' : y ? 'Rising' : 'Stuck'; };
  const modeWord = () => isActual() ? 'actual' : 'predicted';

  // ---------- optional score columns, per league (M51) ----------
  // X.league_features[lg] lists what that league's scores provide (map/build/scores.py FEATURES); anything that needs a
  // missing column is hidden for that league. Colour, averages, ranks and the region/team cards need only doom_pred.
  const FEAT = X.league_features || {};
  const has = (lg, f) => (FEAT[lg] || []).includes(f);
  const shownLeagues = () => [...state.leagues].filter(l => leagueSeasons(l).includes(state.season));
  const scatterLeagues = () => shownLeagues().filter(l => has(l, 'standing'));
  const scatterOk = () => scatterLeagues().length > 0;

  // ---------- demo data labels (M59) ----------
  const DEMO = X.demo_leagues || [];
  const isDemo = lg => DEMO.includes(lg);
  const listWords = a => a.length > 1 ? a.slice(0, -1).join(', ') + ' and ' + a[a.length - 1] : a.join('');
  const demoTag = lg => isDemo(lg) ? ' <span class="dm-demo-tag" title="Fake demo scores, not a model output">Demo</span>' : '';
  function demoNote(teams) {
    const d = teams.filter(t => isDemo(t.league));
    if (!d.length) return '';
    const lg = [...new Set(d.map(t => t.league))];
    return `<div class="dm-demo-note">Includes ${d.length} demo team${d.length === 1 ? '' : 's'} (${esc(lg.join(', '))}): fake scores</div>`;
  }

  // ---------- data views ----------
  const inView = (season, leagues) => D.teams.filter(t => t.season === season && leagues.has(t.league));
  function regionStats(season, leagues) {
    const ts = inView(season, leagues), scored = ts.filter(hasVal);
    const mu = mean(scored.map(zOf)) ?? 0;
    const out = new Map();
    for (const r of D.regions) out.set(r.region_id, { region: r, teams: [], tooNew: [], pending: [], n: 0 });
    for (const t of ts) { const s = out.get(t.region_id); hasVal(t) ? s.teams.push(t) : !t.scored ? s.tooNew.push(t) : s.pending.push(t); }
    for (const s of out.values()) {
      s.n = s.teams.length;
      if (!s.n) continue;
      s.rawZ = mean(s.teams.map(zOf)); s.rawDoom = mean(s.teams.map(doomOf));
      const B = X.eb_tau2 / (X.eb_tau2 + X.eb_s2_within / s.n);
      s.shrunk = mu + B * (s.rawZ - mu);
      s.best = s.teams.reduce((a, b) => (zOf(b) < zOf(a) ? b : a)); s.worst = s.teams.reduce((a, b) => (zOf(b) > zOf(a) ? b : a));
      s.quads = { 'Contender': 0, 'Cliff ahead': 0, 'Rising': 0, 'Stuck': 0 };
      s.quadN = 0;
      for (const t of s.teams) { const q = quadOf(t); if (q) { s.quads[q]++; s.quadN++; } }
      s.byLeague = {}; for (const t of s.teams) s.byLeague[t.league] = (s.byLeague[t.league] || 0) + 1;
    }
    const ranked = [...out.values()].filter(s => s.n).sort((a, b) => a.shrunk - b.shrunk || a.region.display_name.localeCompare(b.region.display_name));
    ranked.forEach((s, i) => { s.rank = i + 1; });
    return { byRegion: out, ranked, empty: [...out.values()].filter(s => !s.n), mu, scored, all: ts };
  }
  function regionTrend(region_id) {
    return X.seasons.map(s => {
      const ls = new Set([...state.leagues].filter(l => (isActual() ? actualSeasons(l) : leagueSeasons(l)).includes(s)));
      const z = D.teams.filter(t => t.season === s && ls.has(t.league) && t.region_id === region_id).map(t => isActual() ? t.z_actual : t.z).filter(v => v != null);
      return { season: s, z: mean(z) };
    });
  }
  function regionChange(region_id) {
    const prev = state.season - 1;
    if (!X.seasons.includes(prev)) return null;
    const ok = l => (isActual() ? actualSeasons(l) : leagueSeasons(l));
    const both = new Set([...state.leagues].filter(l => ok(l).includes(prev) && ok(l).includes(state.season)));
    const zs = s => mean(D.teams.filter(t => t.season === s && both.has(t.league) && t.region_id === region_id).map(zOf).filter(v => v != null));
    const a = zs(prev), b = zs(state.season);
    return a == null || b == null ? null : { prev, delta: b - a };
  }
  const teamSeries = t => D.teams.filter(x => x.franchise_id === t.franchise_id && x.league === t.league).sort((a, b) => a.season - b.season);
  const selTeam = () => state.team && view ? view.all.find(t => sameTeam(t, state.team)) || null : null;

  // ---------- DOM ----------
  const root = $('#doom-map');
  root.innerHTML = `
  <div class="dm-demo-banner" id="dm-demo" role="status"${DEMO.length ? '' : ' hidden'}>DEMO DATA: ${esc(listWords(DEMO))} scores are fake</div>
  <header class="dm-head"><h1>Doom Dashboard</h1>
    <p>How doomed is your part of the country, and your team? Doom predicts how bad a franchise will be over its next three
    seasons, from 0 (top of the league) to 100 (bottom). The map blends nearby ${LEAGUES.length > 1 ? LEAGUES.slice(0, -1).join(', ') + ' and ' + LEAGUES[LEAGUES.length - 1] : LEAGUES.join('')} teams; the scatter
    puts this season's standing against the projected one. Select a team in either view to see it in both.</p></header>
  <div class="dm-controls" role="toolbar" aria-label="Dashboard controls">
    <span class="dm-searchbox"><label class="sr-only" for="dm-search">Search teams, cities and regions</label>
      <input id="dm-search" type="search" placeholder="Search team, city or region" autocomplete="off" role="combobox"
        aria-expanded="false" aria-controls="dm-results" aria-autocomplete="list">
      <ul id="dm-results" role="listbox" class="dm-results" hidden></ul></span>
    <span><span class="lbl" id="vw-l">View</span><span class="dm-seg" id="dm-view" role="group" aria-labelledby="vw-l"></span></span>
    <span><span class="lbl" id="lg-l">Leagues</span><span class="dm-seg" id="dm-leagues" role="group" aria-labelledby="lg-l"></span></span>
    <span class="dm-season"><span class="lbl" id="se-l">Season</span>
      <button id="dm-prev" aria-label="Previous season">&#9664;</button><select id="dm-season" aria-labelledby="se-l"></select>
      <button id="dm-next" aria-label="Next season">&#9654;</button></span>
    <span><span class="lbl" id="mo-l">Doom</span><span class="dm-seg" id="dm-mode" role="group" aria-labelledby="mo-l"></span></span>
    <span><span class="lbl" id="pa-l">Colors</span><span class="dm-seg" id="dm-palette" role="group" aria-labelledby="pa-l"></span></span>
    <span><span class="lbl" id="th-l">Theme</span><span class="dm-seg" id="dm-theme" role="group" aria-labelledby="th-l"></span></span>
    <span><span class="lbl" id="lo-l">Badges</span><span class="dm-seg" id="dm-logos" role="group" aria-labelledby="lo-l"></span></span>
    <span class="dm-tag dm-showing" id="dm-showing" role="status"></span>
  </div>
  <div class="dm-main">
    <div class="dm-left">
      <section class="dm-mapcol" id="dm-mapcol" aria-label="Doom map">
        <div class="dm-mapwrap" id="dm-wrap">
          <nav class="dm-crumb" id="dm-crumb" aria-label="Map level"></nav>
          <canvas id="dm-heat" aria-hidden="true"></canvas>
          <svg id="dm-svg" role="img" aria-label="Doom map of the US and southern Canada"></svg>
          <div class="dm-banner" id="dm-banner" role="status"></div>
          <div class="dm-hint" id="dm-hint">Click the map or hold Ctrl / ⌘ to zoom with the wheel</div>
          <div class="dm-empty" id="dm-empty">Pick at least one league to see the map.</div>
        </div>
        <div class="dm-legend" id="dm-legend"></div>
      </section>
      <section class="dm-scatter" id="dm-scatter" aria-label="Projected-standing scatter">
        <div class="dm-sc-head"><h2 id="dm-sc-title"></h2><div class="dm-sc-key" id="dm-sc-key"></div></div>
        <div class="dm-sc-box" id="dm-sc-box"><svg id="dm-sc-svg" role="img"></svg></div>
      </section>
    </div>
    <aside class="dm-list" id="dm-list" aria-label="Regions ranked by outlook"></aside>
  </div>
  <div class="dm-card" id="dm-card" role="tooltip"></div>`;

  const segButtons = (host, items, isOn, onClick, isDisabled) => {
    host.innerHTML = '';
    for (const it of items) {
      const b = el('button', { type: 'button', 'aria-pressed': String(isOn(it.key)) }, esc(it.label));
      if (it.title) b.title = it.title;
      if (isDisabled && isDisabled(it.key)) b.disabled = true;
      b.addEventListener('click', () => onClick(it.key)); host.appendChild(b);
    }
  };
  function drawControls() {
    segButtons($('#dm-view'), [['both', 'Map + scatter'], ['map', 'Map'], ['scatter', 'Scatter']].map(([key, label]) => ({ key, label })),
      k => state.view === k, k => { state.view = k; applyView(); update({ layout: true }); }, k => k !== 'map' && !scatterOk());
    $('#dm-mode').parentElement.style.display = [...state.leagues].some(l => has(l, 'actual')) ? '' : 'none';
    segButtons($('#dm-leagues'), LEAGUES.map(l => ({ key: l, label: l })), k => state.leagues.has(k), k => {
      state.leagues.has(k) ? state.leagues.delete(k) : state.leagues.add(k); snapSeason(); update();
    });
    const actOk = actualLeaguesNow().length > 0;
    const known = LEAGUES.filter(l => actualSeasons(l).length).map(l => `${l} through ${actualSeasons(l).slice(-1)[0]}`).join(', ');
    segButtons($('#dm-mode'), [{ key: 'predicted', label: 'Predicted' }, { key: 'actual', label: 'Actual', title: `Actual outcomes are known ${known}` }],
      k => (k === 'actual') === isActual(), k => { state.mode = k; update(); }, k => k === 'actual' && !actOk);
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
    const shown = [...state.leagues].filter(l => leagueSeasons(l).includes(state.season)).map(l => `${l} ${seasonLabel(l, state.season)}`).join(' · ');
    $('#dm-showing').innerHTML = isActual() ? `Showing <b>actual</b> doom: what happened next` : `Showing <b>predicted</b> doom${state.mode === 'actual' ? ' (no actual outcomes yet for this season)' : ''}`;
    $('#dm-showing').title = shown;
  }
  const availableSeasons = () => X.seasons.filter(s => [...state.leagues].some(l => leagueSeasons(l).includes(s)));
  function snapSeason() {
    const av = availableSeasons();
    if (av.length && !av.includes(state.season)) state.season = av.reduce((a, b) => Math.abs(b - state.season) < Math.abs(a - state.season) ? b : a);
  }
  $('#dm-season').addEventListener('change', e => { state.season = +e.target.value; update(); });
  $('#dm-prev').addEventListener('click', () => { const av = availableSeasons(), i = av.indexOf(state.season); if (i > 0) { state.season = av[i - 1]; update(); } });
  $('#dm-next').addEventListener('click', () => { const av = availableSeasons(), i = av.indexOf(state.season); if (i < av.length - 1) { state.season = av[i + 1]; update(); } });
  function applyView() {
    const sOk = scatterOk();                    // the scatter needs this season's standing (optional column, M51)
    $('#dm-mapcol').style.display = state.view === 'scatter' && sOk ? 'none' : '';
    $('#dm-scatter').style.display = state.view === 'map' || !sOk ? 'none' : '';
  }

  // ---------- map geometry and layers ----------
  const regionsFC = topojson.feature(D.topo, D.topo.objects.regions);
  const contextFC = topojson.feature(D.topo, D.topo.objects.context);
  const meshInner = topojson.mesh(D.topo, D.topo.objects.regions, (a, b) => a !== b && a.properties.region_id !== b.properties.region_id);
  const CROP = { type: 'Polygon', coordinates: [[[-127, 24], [-128, 56], [-60, 56], [-52, 47], [-66, 24], [-127, 24]]] };
  const makeProj = (w, h, k = 1) => d3.geoConicConformal().parallels([30, 52]).rotate([96, 0]).fitExtent([[8 * k, 8 * k], [w * k - 8 * k, h * k - 8 * k]], CROP);
  let W = 0, Hh = 0, proj, path, prepped = [], view = null, T = d3.zoomIdentity;
  const svg = d3.select('#dm-svg');
  const gWorld = svg.append('g').attr('class', 'dm-world');
  const gContext = gWorld.append('g'), gOutline = gWorld.append('path'), gDim = gWorld.append('path'),
        gHl = gWorld.append('path'), gHit = gWorld.append('g');
  const gOver = svg.append('g');
  const gDots = gOver.append('g'), gLeaders = gOver.append('g'), gLogos = gOver.append('g'), gLabels = gOver.append('g'), gSel = gOver.append('g');

  function layout() {
    const wrap = $('#dm-wrap');
    W = wrap.clientWidth || 600; Hh = Math.round(Math.min(780, W * (W < 640 ? 0.8 : 0.62)));
    wrap.style.height = Hh + 'px';
    proj = makeProj(W, Hh); path = d3.geoPath(proj);
    svg.attr('width', W).attr('height', Hh).attr('viewBox', `0 0 ${W} ${Hh}`);
    gContext.selectAll('path').data(contextFC.features).join('path').attr('d', path)
      .attr('fill', 'var(--context)').attr('stroke', 'var(--context-line)').attr('stroke-width', .5);
    gOutline.attr('d', path(meshInner)).attr('fill', 'none').attr('stroke', 'var(--outline)').attr('stroke-width', .8);
    gHit.selectAll('path').data(regionsFC.features, d => d.properties.region_id).join('path').attr('d', path)
      .attr('fill', 'transparent').attr('data-region', d => d.properties.region_id).style('cursor', 'pointer');
    zoom.extent([[0, 0], [W, Hh]]).translateExtent([[-W * 0.1, -Hh * 0.1], [W * 1.1, Hh * 1.1]]);
    layoutScatter();
  }

  // ---------- heat (cached, M35) ----------
  const cache = window.DoomHeatCache({ sigma: X.sigma_mi, smooth: 2.5, workerSource: document.getElementById('dm-heat-src').textContent });
  const dprNow = () => Math.min(window.devicePixelRatio || 1, 2);
  const dataKey = (season, leagues) => season + '|' + [...leagues].sort().join(',') + '|' + modeWord();
  const styleKey = () => state.palette + '|' + themeNow();
  const tables = new Map();
  const tableFor = k => tables.get(k) || (tables.set(k, H.colorTable(lut(), greyOf())), tables.get(k));
  const colorOpts = () => ({ w0: X.opacity_w0, w1: X.opacity_w1, zlo: X.z_lo, zhi: X.z_hi, table: tableFor(styleKey()) });
  const teamsFor = (season, leagues) => D.teams.filter(t => t.season === season && leagues.has(t.league))
    .map(t => ({ lat: t.lat, lon: t.lon, z: isActual() ? t.z_actual : t.z })).filter(t => t.z != null);
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
  function rememberZoomView(key) {
    const i = zoomViews.indexOf(key); if (i >= 0) zoomViews.splice(i, 1); zoomViews.push(key);
    if (zoomViews.length > 30) { const keep = new Set(zoomViews.slice(-30)); zoomViews.splice(0, zoomViews.length - 30);
      cache.clearViews(k => !k.startsWith('z:') || keep.has(k)); }
  }
  let baseImg = null, sharp = null, heatJob = 0, prefetchTimer = 0, sharpTimer = 0;
  function drawHeat() {
    const cv = $('#dm-heat'), dpr = dprNow(), cw = Math.round(W * dpr), ch = Math.round(Hh * dpr);
    if (cv.width !== cw || cv.height !== ch) { cv.width = cw; cv.height = ch; cv.style.width = W + 'px'; cv.style.height = Hh + 'px'; }
    const ctx = cv.getContext('2d'); ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.clearRect(0, 0, cw, ch);
    if (sharp && sharp.k === T.k && sharp.x === T.x && sharp.y === T.y) { ctx.drawImage(sharp.img, 0, 0); return; }
    if (!baseImg) return;
    ctx.imageSmoothingEnabled = true; ctx.imageSmoothingQuality = 'high';
    ctx.drawImage(baseImg, T.x * dpr, T.y * dpr, baseImg.width * T.k, baseImg.height * T.k);
  }
  function paintHeat() {
    if (state.view === 'scatter') { root.dataset.painted = String(++heatJob); return; }
    const job = ++heatJob, dk = dataKey(state.season, state.leagues), teams = teamsFor(state.season, state.leagues), t0 = performance.now();
    cache.image(viewFor(d3.zoomIdentity), dk, teams, styleKey(), colorOpts(), 0).then(img => {
      if (job !== heatJob) return;
      baseImg = img; sharp = null; drawHeat(); requestSharp(0);
      root.dataset.painted = String(job); root.dataset.paintMs = String(Math.round(performance.now() - t0));
      clearTimeout(prefetchTimer); prefetchTimer = setTimeout(prefetch, 50);
    });
  }
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
    const idle = cb => (window.requestIdleCallback || (f => setTimeout(f, 30)))(cb);
    const tf = s => D.teams.filter(t => t.season === s && state.leagues.has(t.league)).map(t => ({ lat: t.lat, lon: t.lon, z: isActual() ? t.z_actual : t.z })).filter(t => t.z != null);
    const dks = s => s + '|' + [...state.leagues].sort().join(',') + '|' + modeWord();
    seasons.forEach((s, i) => cache.field(v, dks(s), tf(s), 10 + i));
    const near = seasons.slice(1, 3), sk = styleKey(), co = colorOpts();
    (function next(k) {
      if (k >= near.length) {
        Promise.all(seasons.map(s => cache.field(v, dks(s), tf(s), 20))).then(() => {
          root.dataset.prefetched = '1';
          const dk = dataKey(state.season, state.leagues), tm = teamsFor(state.season, state.leagues);
          D.regions.forEach((r, i) => idle(() => cache.field(viewFor(regionTransform(r.region_id)), dk, tm, 40 + i)));
        });
        return;
      }
      cache.field(v, dks(near[k]), tf(near[k]), 5).then(() => idle(() => cache.image(v, dks(near[k]), tf(near[k]), sk, co, 5).then(() => next(k + 1))));
    })(0);
  }

  // ---------- legend, banner ----------
  function drawLegend() {
    const L = lut(), stops = L.filter((_, i) => i % 15 === 0 || i === 255).map((c, i, a) => `${c} ${(i / (a.length - 1) * 100).toFixed(1)}%`);
    const shown = [...state.leagues].filter(l => leagueSeasons(l).includes(state.season)).map(l => `${l} ${seasonLabel(l, state.season)}`);
    const line = D.palette.modes[themeNow()].swatch_line;
    $('#dm-legend').innerHTML = `
      <div class="ends"><span>Bright future</span><span>Doomed</span></div>
      <span class="ramp" style="display:block;background:linear-gradient(90deg,${stops.join(',')})"></span>
      <div class="row"><span class="sw"><span class="grey" style="background:${greyOf()};box-shadow:inset 0 0 0 1.5px ${line}"></span>No teams nearby</span>
        <span class="sw"><span class="ring"></span>Too new to score</span></div>
      <div class="note">Colors compare teams within their league, then across leagues.</div>
      <div class="showing">Showing <b>${modeWord()}</b> doom${shown.length ? ': ' + esc(shown.join(' · ')) : ''}</div>`;
  }
  function drawBanner() {
    const sel = [...state.leagues], present = sel.filter(l => leagueSeasons(l).includes(state.season)), missing = sel.filter(l => !present.includes(l));
    const msgs = [];
    $('#dm-banner').title = '';
    if (missing.length) {                     // M58: any selected league with no scores this season
      const why = missing.map(l => { const s = leagueSeasons(l); return `${l} scores cover ${s[0]}–${s[s.length - 1]}`; }).join('; ');
      const b = document.getElementById('dm-banner');
      if (b) b.title = why;
      msgs.push(`This season shows: ${esc(present.join(', ') || 'no league')} <span style="font-weight:400">(no ${esc(missing.join(', '))})</span>`);
    }
    if (isActual()) {
      const act = actualLeaguesNow(), noAct = present.filter(l => !act.includes(l));
      msgs.push(noAct.length ? `Actual outcomes: ${esc(act.join(' + '))} only <span style="font-weight:400">(${esc(noAct.map(l => `${l} known through ${actualSeasons(l).slice(-1)[0]}`).join('; '))})</span>`
        : `Actual outcomes: what happened over the next three seasons`);
    }
    const b = $('#dm-banner');
    b.innerHTML = msgs.join('<br>'); b.style.display = msgs.length ? 'block' : 'none';
  }

  // ---------- side: region list or team panel ----------
  function drawSide() { state.team ? drawTeamPanel() : drawList(); }
  function drawList() {
    const host = $('#dm-list'), R = view.ranked, BW = 120, C0 = BW / 2;
    host.classList.remove('dm-panel'); host.setAttribute('aria-label', 'Regions ranked by outlook');
    const ext = Math.max(0.25, ...R.map(s => Math.max(Math.abs(s.rawZ), Math.abs(s.shrunk))));
    const bx = v => C0 + v / ext * (C0 - 5);
    const bar = s => `<svg width="${BW}" height="16" aria-hidden="true">
      <line x1="${C0}" x2="${C0}" y1="0" y2="16" stroke="var(--muted)" stroke-opacity=".6"/>
      <rect x="${Math.min(bx(s.shrunk), C0)}" y="4" width="${Math.max(2, Math.abs(bx(s.shrunk) - C0))}" height="8" rx="1.5" fill="var(--ink)" fill-opacity=".7"/>
      <circle cx="${bx(s.rawZ)}" cy="8" r="4" fill="${colorOf(s.rawZ)}" stroke="var(--ink)" stroke-width="1.2"/></svg>`;
    host.innerHTML = `<h2>Regions ranked by outlook</h2>
      <p class="sub">Brightest first, by a reliability-adjusted average (bar): regions with few teams are pulled toward the
      overall average. Dot = raw average of the region's teams, in its map color. Center line = league average. n = teams with
      ${modeWord()} doom. Click (or Enter) to zoom in.</p>
      <p class="sub caption"><b>Most differences between regions are within what chance alone would produce.</b></p>
      <div class="axis"><span></span><span></span><span><i>&larr; brighter</i><i>doomier &rarr;</i></span><span>n</span></div>
      <ol class="dm-rows" id="dm-rows">${R.map(s => `<li tabindex="0" data-region="${s.region.region_id}"
        aria-label="${esc(`${ord(s.rank)}: ${s.region.display_name}, ${words(s.rawZ)}, ${s.n} team${s.n === 1 ? '' : 's'}`)}">
        <span class="rk">${s.rank}</span><span class="nm">${esc(s.region.display_name)}</span>${bar(s)}<span class="n">${s.n}</span></li>`).join('')}</ol>
      ${view.empty.length ? `<h3>No teams with ${modeWord()} doom this season</h3><ul class="dm-rows empty">${view.empty.map(s =>
        `<li><span class="rk">&ndash;</span><span class="nm">${esc(s.region.display_name)}${s.tooNew.length ? ` (${s.tooNew.length} too new)` : ''}</span></li>`).join('')}</ul>` : ''}`;
    for (const li of host.querySelectorAll('#dm-rows li')) {
      const id = li.dataset.region;
      li.addEventListener('mouseenter', () => state.level === 1 && !touchy() && setHover(id, 'list'));
      li.addEventListener('focus', () => state.level === 1 && setHover(id, 'list'));
      li.addEventListener('mouseleave', () => { if (!pinned) setHover(null); });
      li.addEventListener('blur', () => { if (!pinned) setHover(null); });
      li.addEventListener('click', () => {
        if (touchy() && state.level === 1 && pinned !== 'region:' + id) { pinRegionCard(id, li.getBoundingClientRect()); return; }
        unpin(); zoomToRegion(id);
      });
      li.addEventListener('keydown', e => { if (e.key === 'Enter') zoomToRegion(id); });
    }
    markListFocus();
  }
  const markListFocus = () => { for (const li of document.querySelectorAll('#dm-rows li')) li.classList.toggle('on', li.dataset.region === (state.hover || (state.level === 2 ? state.focus : null))); };

  function trendSvg(t, w, h, axes) {
    const ser = teamSeries(t);
    const pred = ser.filter(x => x.doom != null), act = ser.filter(x => x.actual_doom != null);
    if (pred.length < 2) return '';
    const x = d3.scaleLinear().domain(d3.extent(ser, d => d.season)).range([axes ? 26 : 3, w - 4]), y = d3.scaleLinear().domain([0, 100]).range([h - (axes ? 14 : 3), 4]);
    const cur = ser.find(d => d.season === t.season);
    return `<svg width="${w}" height="${h}" aria-label="Doom across seasons: line = predicted, dots = actual">
      ${axes ? `<text x="0" y="${y(100) + 4}" class="ax">100</text><text x="6" y="${y(0)}" class="ax">0</text>
        <text x="${x.range()[0]}" y="${h - 2}" class="ax">${ser[0].season}</text><text x="${w - 4}" y="${h - 2}" class="ax" text-anchor="end">${ser[ser.length - 1].season}</text>` : ''}
      <line x1="${x.range()[0]}" x2="${w - 4}" y1="${y(50)}" y2="${y(50)}" stroke="var(--line)" stroke-dasharray="2 2"/>
      <path d="${d3.line().x(d => x(d.season)).y(d => y(d.doom))(pred)}" fill="none" stroke="var(--muted)" stroke-width="1.5"/>
      ${axes ? act.map(d => `<circle cx="${x(d.season)}" cy="${y(d.actual_doom)}" r="2.2" fill="var(--ink)"/>`).join('') : ''}
      ${cur && cur.doom != null ? `<circle cx="${x(cur.season)}" cy="${y(cur.doom)}" r="3.6" fill="${colorOf(cur.z)}" stroke="var(--ink)"/>` : ''}</svg>`;
  }
  function seasonText(t) {               // e.g. "50.6% wins (82-80), 48th percentile": the parts the league provides
    const a = [];
    if (has(t.league, 'win_pct') && t.win_pct != null) a.push((t.win_pct * 100).toFixed(1) + '% wins');
    if (has(t.league, 'record') && t.record) a.push(a.length ? `(${esc(t.record)})` : esc(t.record));
    let out = a.join(' ');
    if (has(t.league, 'standing') && t.wpp != null) out += (out ? ', ' : '') + ord(Math.round(t.wpp)) + ' percentile';
    return out;
  }
  const hasSeason = t => ['win_pct', 'record', 'standing'].some(f => has(t.league, f));
  function chipHtml(t) {
    const p = has(t.league, 'p_doom75') && t.p75 != null ? Math.round(t.p75 * 100) : null;
    const box = `class="chip" style="box-shadow:inset 4px 0 0 ${colorOf(t.z)}"`;
    if (has(t.league, 'band')) return `<span ${box}>${bandText(t.band)} of a doomed stretch${p != null ? ` (${p}% chance of doom ≥ 75)` : ''}</span>`;
    return p != null ? `<span ${box}>${p}% chance of a doom ≥ 75 stretch</span>` : '';
  }
  function panelTable(t) {
    const rows = [];
    if (has(t.league, 'range80')) rows.push(`<tr><td>Likely range (80%)</td><td>${t.lo80 != null ? `${Math.round(t.lo80)}–${Math.round(t.hi80)}` : 'not available'}</td></tr>`);
    if (hasSeason(t)) rows.push(`<tr><td>This season</td><td>${seasonText(t) || '–'}</td></tr>`);
    if (has(t.league, 'standing')) rows.push(`<tr><td>Quadrant (${modeWord()})</td><td>${esc(quadOf(t) || '–')}</td></tr>`);
    if (has(t.league, 'projection') && t.proj) rows.push(`<tr><td>Projected finish</td><td>${t.proj.map(v => v == null ? '–' : ord(Math.round(v))).join(', ')} <span class="k">percentile, next 3 seasons</span></td></tr>`);
    return rows.length ? `<table>${rows.join('')}</table>` : '';
  }
  function modelNote(lg) {
    const m = D.leagues[lg];
    if (!m || !m.model_note) return '';
    return `<p class="k dm-model-note">About the ${esc(lg)} score${m.backtested ? '' : ' (not backtested)'}: ${esc(m.model_note)}</p>`;
  }
  function drawTeamPanel() {
    const t = selTeam(), host = $('#dm-list');
    host.classList.add('dm-panel'); host.setAttribute('aria-label', 'Team details');
    if (!t) {
      host.innerHTML = `<button class="backlink" id="dm-panel-back">&larr; All regions list</button>
        <h2>${esc(state.team.franchise_id.replace(/-/g, ' '))}</h2><p>Not in the selected leagues or season (${state.season}).</p>`;
      $('#dm-panel-back').addEventListener('click', () => select(null)); return;
    }
    const r = REG.get(t.region_id), dv = t.drivers;
    const drivers = dv && (dv.up.length || dv.down.length) ? `<h3>What moves this prediction</h3>
      ${dv.up.length ? `<div class="k">Toward doom</div><ul class="drv">${dv.up.map(d => `<li>${esc(d)}</li>`).join('')}</ul>` : ''}
      ${dv.down.length ? `<div class="k">Away from doom</div><ul class="drv">${dv.down.map(d => `<li>${esc(d)}</li>`).join('')}</ul>` : ''}
      ${dv.note ? `<p class="k">${esc(dv.note)}</p>` : ''}` : (dv && dv.note ? `<h3>What moves this prediction</h3><p class="k">${esc(dv.note)}</p>` : '');
    host.innerHTML = `<button class="backlink" id="dm-panel-back">&larr; All regions list</button>
      <h2>${esc(t.season_team_name)}${demoTag(t.league)}</h2>
      <div class="k">${esc(t.league)} ${esc(seasonLabel(t.league, t.season))} · ${esc(t.city)} · ${esc(r ? r.display_name : '')}</div>
      ${t.scored ? `<div class="big"><b>${Math.round(t.doom)}</b><span>predicted doom of 100</span></div>
        ${chipHtml(t)}
        ${!has(t.league, 'actual') ? '' : t.actual_doom != null ? `<div class="act">Actual doom: <b>${Math.round(t.actual_doom)}</b> <span class="k">(what happened over the next three seasons)</span></div>`
          : `<div class="act k">Actual outcome not known yet.</div>`}
        ${panelTable(t)}
        <div class="k">Doom by season (line = predicted${has(t.league, 'actual') ? ', dots = actual' : ''})</div>${trendSvg(t, 290, 92, true)}
        ${drivers}` : `<p>Too new to score: no prediction for this season, so this team is left out of every average.</p>`}
      ${modelNote(t.league)}
      <div class="dm-panel-actions">
        <button type="button" id="dm-show-map">Show on map</button>
        <button type="button" disabled aria-disabled="true" title="Coming soon">Full diagnostics (coming soon)</button>
      </div>`;
    $('#dm-panel-back').addEventListener('click', () => select(null));
    $('#dm-show-map').addEventListener('click', () => { if (state.view === 'scatter') { state.view = 'both'; applyView(); update({ layout: true }); } zoomToRegion(t.region_id); });
  }

  // ---------- cards (hover; pinned on touch, M46) ----------
  let pinned = null;
  function placeCard(card, pt, anchor) {
    card.style.display = 'block';
    let x, y;
    if (pt && pt.clientX != null) { x = pt.clientX + 16; y = pt.clientY + 16; } else { x = anchor[0] + 12; y = anchor[1] + 12; }
    const cw = card.offsetWidth, chh = card.offsetHeight;
    if (x + cw > innerWidth - 8) x = (pt && pt.clientX != null ? pt.clientX - 16 : x - 24) - cw;
    if (y + chh > innerHeight - 8) y = Math.max(8, innerHeight - 8 - chh);
    card.style.left = Math.max(8, x) + 'px'; card.style.top = y + 'px';
  }
  function unpin() { pinned = null; const c = $('#dm-card'); c.classList.remove('pinned'); c.style.display = 'none'; }
  function pinRegionCard(id, rect, pt) {
    pinned = null; setHover(id, 'pin', pt || null);
    const c = $('#dm-card');
    c.insertAdjacentHTML('beforeend', `<div class="pinbar"><button type="button" id="dm-pin-zoom">Zoom in</button><button type="button" id="dm-pin-close">Close</button></div>`);
    c.classList.add('pinned'); pinned = 'region:' + id;
    if (!pt && rect) placeCard(c, null, [rect.left, rect.top]);
    $('#dm-pin-zoom').addEventListener('click', () => { unpin(); zoomToRegion(id); });
    $('#dm-pin-close').addEventListener('click', () => { unpin(); setHover(null); });
  }
  function pinTeamCard(t, pt) {
    const c = $('#dm-card');
    c.innerHTML = teamCardHtml(t) + `<div class="pinbar"><button type="button" id="dm-pin-details">Details</button><button type="button" id="dm-pin-close">Close</button></div>`;
    c.classList.add('pinned'); pinned = 'team:' + t.franchise_id; placeCard(c, pt);
    $('#dm-pin-details').addEventListener('click', () => { unpin(); select(t); });
    $('#dm-pin-close').addEventListener('click', unpin);
  }
  document.addEventListener('pointerdown', e => {
    if (pinned && !$('#dm-card').contains(e.target) && !$('#dm-wrap').contains(e.target) && !$('#dm-sc-box').contains(e.target) && !$('#dm-list').contains(e.target)) { unpin(); setHover(null); }
  });

  function setHover(id, from, pt) {
    if (pinned && from !== 'pin') return;
    state.hover = id; state.hoverFrom = from;
    drawFocusLayers(); markListFocus(); drawScatterFocus();
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
    if (!pt || pt.clientX == null) return '';
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
    const pend = s.pending.length ? `; ${s.pending.length} without an actual outcome yet` : '';
    if (!s.n) return `<div class="t">${esc(r.display_name)}</div><div class="k">${esc(r.core_metros)}</div>${demoNote([...s.tooNew, ...s.pending])}
      <div class="verdict"><span class="chipc" style="background:${greyOf()}"></span><span>No ${esc([...state.leagues].join('/'))} teams with ${modeWord()} doom this season</span></div>
      <div class="k">${tooNew}${pend}. Not ranked.</div>${spotHtml(pt)}`;
    const ch = regionChange(r.region_id);
    const chTxt = !ch ? '<span class="k">no comparable previous season</span>'
      : Math.abs(ch.delta) < 0.05 ? `≈ unchanged since ${ch.prev}`
      : ch.delta > 0 ? `<b style="color:${colorOf(1.4)}">▲</b> more doomed than in ${ch.prev}`
      : `<b style="color:${colorOf(-1.4)}">▼</b> brighter than in ${ch.prev}`;
    const team = t => `${esc(t.season_team_name)} <span class="k">${t.league} · doom ${Math.round(doomOf(t))}</span>`;
    return `<div class="t">${esc(r.display_name)}</div><div class="k">${esc(r.core_metros)}</div>${demoNote([...s.teams, ...s.tooNew, ...s.pending])}
      <div class="verdict"><span class="chipc" style="background:${colorOf(s.rawZ)}"></span>
        <span class="big">${words(s.rawZ)}</span><span>average ${modeWord()} doom <b>${Math.round(s.rawDoom)}</b> <span class="k">of 100</span></span></div>
      <span class="rank">${ord(s.rank)} brightest of ${view.ranked.length}</span>${s.n === 1 ? ' <span class="rank one">based on 1 team</span>' : ''}
      <table>
        <tr><td>Based on</td><td><b>${s.n === 1 ? '1 team' : s.n + ' teams'}</b> (${esc(lg)}); ${tooNew}${pend}${s.n === 2 ? '. <i>Few teams: treat with care.</i>' : ''}</td></tr>
        <tr><td>Best hope</td><td>${team(s.best)}</td></tr>
        ${s.n > 1 ? `<tr><td>Biggest worry</td><td>${team(s.worst)}</td></tr>` : ''}
      </table>
      ${quadHtml(s)}
      <div class="trend">${spark(r.region_id)}<span>${chTxt}</span></div>${spotHtml(pt)}
      ${touchy() ? '' : '<div class="k" style="margin-top:6px">Click to zoom in.</div>'}`;
  }
  function quadHtml(s) {                // quadrant counts need the standing: only teams whose league provides it
    if (!s.quadN) return '';
    const q = s.quads, out = [...new Set(s.teams.filter(t => !has(t.league, 'standing')).map(t => t.league))];
    return `<div class="quad">${['Contender', 'Cliff ahead', 'Rising', 'Stuck'].map(k => `<div><b>${q[k]}</b>${k}</div>`).join('')}</div>` +
      (s.quadN < s.n ? `<div class="k">Quadrants count ${s.quadN} of ${s.n} teams${out.length ? ` (${esc(out.join(', '))} scores have no standing)` : ''}</div>` : '');
  }
  function teamCardHtml(t) {
    const r = REG.get(t.region_id);
    if (!t.scored) return `<div class="t">${esc(t.season_team_name)}${demoTag(t.league)}</div><div class="k">${esc(t.league)} ${esc(seasonLabel(t.league, t.season))} · ${esc(t.city)}</div>
      <p style="margin:6px 0 0">Too new to score: no prediction this season; not in any average.</p>`;
    const act = t.actual_doom != null ? `<tr><td>Actual doom</td><td><b>${Math.round(t.actual_doom)}</b> (what happened)</td></tr>` : '';
    return `<div class="t">${esc(t.season_team_name)}${demoTag(t.league)}</div>
      <div class="k">${esc(t.league)} ${esc(seasonLabel(t.league, t.season))} · ${esc(t.city)} · ${esc(r ? r.display_name : '')}</div>
      <div class="verdict"><span class="chipc" style="background:${colorOf(t.z)}"></span>
        <span class="big">${Math.round(t.doom)}</span><span>predicted doom of 100${has(t.league, 'band') ? ` · <span class="band">${bandText(t.band)}</span>` : ''}</span></div>
      ${act || hasSeason(t) || has(t.league, 'standing') ? `<table>
        ${act}
        ${hasSeason(t) ? `<tr><td>This season</td><td>${seasonText(t) || '–'}</td></tr>` : ''}
        ${has(t.league, 'standing') ? `<tr><td>Quadrant</td><td>${esc(quadOf(t) || '–')} <span class="k">(${modeWord()})</span></td></tr>` : ''}
      </table>` : ''}
      <div class="trend">${trendSvg(t, 128, 30, false)}<span class="k">doom over seasons</span></div>
      ${touchy() ? '' : '<div class="k" style="margin-top:6px">Click for details.</div>'}`;
  }

  function drawFocusLayers() {
    const id = state.level === 2 ? state.focus : state.hover;
    const others = { type: 'FeatureCollection', features: regionsFC.features.filter(f => f.properties.region_id !== id) };
    const me = regionsFC.features.find(f => f.properties.region_id === id);
    gDim.attr('d', id ? path(others) : null).attr('fill', 'var(--dim)').attr('pointer-events', 'none');
    gHl.attr('d', me ? path(me) : null).attr('fill', 'none').attr('stroke', 'var(--ink)').attr('stroke-width', 2).attr('pointer-events', 'none');
  }
  svg.on('pointermove', ev => {
    if (state.level === 2 || ev.pointerType === 'touch' || pinned) return;
    const t = ev.target.closest && ev.target.closest('[data-region]');
    if (t) setHover(t.getAttribute('data-region'), 'map', ev);
    else if (state.hoverFrom === 'map') setHover(null);
  });
  svg.on('pointerleave', () => { if (state.hoverFrom === 'map' && !pinned) setHover(null); });
  svg.on('click', ev => {
    const t = ev.target.closest && ev.target.closest('[data-region]');
    activate(true);
    if (!t || ev.target.closest('.dm-logo')) return;
    const id = t.getAttribute('data-region');
    if (touchy() && state.level === 1 && pinned !== 'region:' + id) { pinRegionCard(id, null, ev); return; }
    unpin(); zoomToRegion(id);
  });

  // ---------- camera (M37-M39, M42) ----------
  function showHint() { const h = $('#dm-hint'); h.classList.add('on'); clearTimeout(showHint.t); showHint.t = setTimeout(() => h.classList.remove('on'), 1300); }
  function activate(on) { state.active = on; $('#dm-wrap').classList.toggle('active', on); }
  document.addEventListener('pointerdown', e => { if (!$('#dm-wrap').contains(e.target)) activate(false); });
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
  let animating = false, frameLog = null;

  function onCamera() {
    if (frameLog) frameLog.push(performance.now());
    gWorld.attr('transform', T.toString());
    drawHeat();
    if (!animating) {
      if (state.level === 1 && T.k >= LEVEL_IN) enterLevel2(regionAtCenter(), false);
      else if (state.level === 2 && T.k < LEVEL_OUT) exitLevel2();
      else if (state.level === 2 && T.k >= LEVEL_IN) { const r = regionAtCenter(); if (r && r !== state.focus) { state.focus = r; drawFocusLayers(); drawCrumb(); drawScatterFocus(); } }
    }
    positionOverlay();
  }
  function settle() { requestSharp(120); writeHash(); }
  function regionAtCenter() {
    const ll = proj.invert(T.invert([W / 2, Hh / 2]));
    const hit = ll && regionsFC.features.find(f => d3.geoContains(f, ll));
    if (hit) return hit.properties.region_id;
    let best = null, bd = Infinity;
    for (const f of regionsFC.features) { const c = T.apply(path.centroid(f)), d = (c[0] - W / 2) ** 2 + (c[1] - Hh / 2) ** 2; if (d < bd) { bd = d; best = f.properties.region_id; } }
    return best;
  }
  /** Camera target (M38 revised): the region's venues padded ~150 mi on every side, so the region outline and dimmed
   *  neighbours stay in view; regions without venues frame their shape inside the crop. */
  function regionTransform(id) {
    const venues = D.teams.filter(t => t.region_id === id && t.season === state.season && state.leagues.has(t.league));
    let x0, y0, x1, y1;
    if (venues.length) {
      const pts = [];
      for (const t of venues) {
        const dLat = PAD_MI / 69.05, dLon = PAD_MI / (69.17 * Math.cos(t.lat * Math.PI / 180));
        for (const [a, b] of [[0, 0], [dLon, 0], [-dLon, 0], [0, dLat], [0, -dLat]]) pts.push(proj([t.lon + a, t.lat + b]));
      }
      [x0, x1] = d3.extent(pts, p => p[0]); [y0, y1] = d3.extent(pts, p => p[1]);
    } else {
      const f = regionsFC.features.find(f => f.properties.region_id === id), [[a, b], [c, d]] = path.bounds(f);
      x0 = Math.max(a, 0); y0 = Math.max(b, 0); x1 = Math.min(c, W); y1 = Math.min(d, Hh);
    }
    const cx = (x0 + x1) / 2, cy = (y0 + y1) / 2;
    const bw = Math.max(x1 - x0, W * 0.22), bh = Math.max(y1 - y0, Hh * 0.22);
    const k = Math.max(LEVEL_IN + 0.05, Math.min(8, 0.96 * Math.min(W / bw, Hh / bh)));
    const t = d3.zoomIdentity.translate(W / 2 - k * cx, Hh / 2 - k * cy).scale(k);
    return d3.zoomIdentity.translate(Math.round(t.x), Math.round(t.y)).scale(+k.toFixed(3));
  }
  function zoomToRegion(id) {
    if (!id || !REG.has(id) || state.view === 'scatter') return;
    pinned = null; setHover(null);
    const target = regionTransform(id), t0 = performance.now();
    state.focus = id; state.level = 2;
    $('#dm-wrap').classList.add('level2'); drawFocusLayers(); drawCrumb(); drawScatterFocus(); hideLogos(); markListFocus();
    // M62: on a phone the list sits below the map; bring the map into view so the zoom is not off-screen
    const wr = $('#dm-wrap').getBoundingClientRect();
    if (wr.bottom < 80 || wr.top > innerHeight - 80) $('#dm-wrap').scrollIntoView({ block: 'start', behavior: REDUCED.matches ? 'auto' : 'smooth' });
    requestSharp(0, target);
    animating = true; root.dataset.zoomMs = '';
    const run = () => {
      const tr = svg.transition('camera').duration(ms(Math.min(600, Math.max(380, 600 * dist(T, target)))))
        .ease(d3.easeCubicInOut).call(zoom.transform, target);
      tr.on('end interrupt', () => { animating = false; settle(); revealLogos(); writeHash(); root.dataset.zoomMs = String(Math.round(performance.now() - t0)); });
    };
    ms(100) ? setTimeout(run, ms(100)) : run();
  }
  const dist = (a, b) => Math.min(1, (Math.hypot((a.x - b.x) / W, (a.y - b.y) / Hh) + Math.abs(Math.log(a.k / b.k)) / 3));
  function zoomOut() {
    animating = true; exitLevel2();
    svg.transition('camera').duration(ms(550)).ease(d3.easeCubicInOut).call(zoom.transform, d3.zoomIdentity)
      .on('end interrupt', () => { animating = false; settle(); positionOverlay(); });
  }
  function enterLevel2(id, animated) {
    state.level = 2; state.focus = id;
    $('#dm-wrap').classList.add('level2'); drawFocusLayers(); drawCrumb(); drawScatterFocus(); markListFocus();
    if (!animated) revealLogos(true);
  }
  function exitLevel2() {
    state.level = 1; state.focus = null;
    $('#dm-wrap').classList.remove('level2'); hideLogos(); drawFocusLayers(); drawCrumb(); drawScatterFocus(); markListFocus(); positionOverlay(); writeHash();
  }
  document.addEventListener('keydown', e => {                          // M47: Esc goes up one level
    if (e.key !== 'Escape') return;
    if (document.activeElement === $('#dm-search') && !$('#dm-results').hidden) { closeResults(); return; }
    if (pinned) { unpin(); setHover(null); }
    else if (state.team) select(null);
    else if (state.level === 2) zoomOut();
    else activate(false);
  });
  // M62: only the badges of the zoomed-in region take keyboard focus (the rest are off-screen)
  const setBadgeTabs = () => gLogos.selectAll('g.dm-logo').attr('tabindex', d => state.level === 2 && d.t.region_id === state.focus ? 0 : -1);
  function drawCrumb() {
    setBadgeTabs();
    const c = $('#dm-crumb');
    if (state.level === 1) { c.innerHTML = `<button disabled>All regions</button>`; return; }
    c.innerHTML = `<button class="back" id="dm-back" aria-label="Zoom out to all regions">&larr; Back</button>
      <button id="dm-all">All regions</button><span class="sep">›</span><button disabled>${esc(REG.get(state.focus)?.display_name || '')}</button>`;
    $('#dm-back').addEventListener('click', zoomOut); $('#dm-all').addEventListener('click', zoomOut);
  }

  // ---------- badges (M40) ----------
  const preload = Promise.all(Object.values(D.logos).filter(l => l.uri).map(l => { const im = new Image(); im.src = l.uri; return im.decode().catch(() => null); }));
  let logoNodes = [];
  function badge(g, sizeR) {
    g.append('circle').attr('class', 'halo').attr('r', sizeR + RING_W / 2 + 1.5);
    g.append('circle').attr('class', 'ring').attr('r', sizeR).attr('fill', 'none').attr('stroke-width', RING_W);
    g.append('circle').attr('class', 'plate').attr('r', sizeR - RING_W / 2);
    const s = (sizeR - RING_W / 2) * 1.43;
    g.append('image').attr('x', -s / 2).attr('y', -s / 2).attr('width', s).attr('height', s).attr('preserveAspectRatio', 'xMidYMid meet');
    g.append('text').attr('class', 'mono');
  }
  function fillBadge(sel) {
    sel.select('.ring').attr('stroke', d => d.t.scored && zOf(d.t) != null ? colorOf(zOf(d.t)) : '#8a909c').attr('stroke-dasharray', d => d.t.scored && zOf(d.t) != null ? null : '4 3');
    sel.each(function (d) {
      const lg = logoOf(d.t), useImg = lg.uri && !state.monograms;
      d3.select(this).select('image').attr('href', useImg ? lg.uri : null).style('display', useImg ? null : 'none')
        .on('error', function () { d3.select(this).style('display', 'none'); d3.select(this.parentNode).select('.mono').style('display', null); });
      d3.select(this).select('.mono').text(lg.mono).style('display', useImg ? 'none' : null).attr('font-size', lg.mono.length > 3 ? 9 : 11);
    });
  }
  function buildLogos() {
    logoNodes = view.all.map(t => ({ t, key: t.franchise_id + '|' + t.league }));
    const g = gLogos.selectAll('g.dm-logo').data(logoNodes, d => d.key).join(enter => {
      const e = enter.append('g').attr('class', 'dm-logo').attr('tabindex', -1).attr('role', 'button'); badge(e, LOGO_R); return e; });
    g.attr('aria-label', d => `${d.t.season_team_name}${isDemo(d.t.league) ? ' (demo data)' : ''}: ${d.t.scored ? `predicted doom ${Math.round(d.t.doom)}, ${bandText(d.t.band)}` : 'too new to score'}. Press Enter for details.`);
    fillBadge(g);
    g.on('pointerenter', (ev, d) => { if (ev.pointerType === 'touch' || pinned) return; const c = $('#dm-card'); c.innerHTML = teamCardHtml(d.t); placeCard(c, ev); hoverTeam(d.t); })
      .on('pointermove', ev => { if (ev.pointerType !== 'touch' && !pinned) placeCard($('#dm-card'), ev); })
      .on('pointerleave', () => { if (!pinned) { $('#dm-card').style.display = 'none'; hoverTeam(null); } })
      .on('focus', function (ev, d) { const c = $('#dm-card'), b = this.getBoundingClientRect(); c.innerHTML = teamCardHtml(d.t); placeCard(c, null, [b.right, b.top]); hoverTeam(d.t); })
      .on('blur', () => { if (!pinned) $('#dm-card').style.display = 'none'; hoverTeam(null); })
      .on('click', (ev, d) => { ev.stopPropagation(); if (touchy() && pinned !== 'team:' + d.t.franchise_id) { pinTeamCard(d.t, ev); return; } unpin(); select(d.t); })
      .on('keydown', (ev, d) => { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); select(d.t); } });
    gLogos.style('display', state.level === 2 ? null : 'none');
    setBadgeTabs();
  }
  function layoutLogos() {
    const STEP = 2 * LOGO_R + RING_W + 3;
    const metros = d3.groups(logoNodes, d => d.t.metro_id).map(([id, nodes]) => {
      nodes.sort((a, b) => (a.t.league + a.t.season_team_name).localeCompare(b.t.league + b.t.season_team_name));
      const anchors = nodes.map(d => T.apply(proj([d.t.lon, d.t.lat])));
      const c = [d3.mean(anchors, a => a[0]), d3.mean(anchors, a => a[1])], n = nodes.length;
      const r = n === 1 ? 0 : n === 2 ? STEP / 2 : STEP / (2 * Math.sin(Math.PI / n));
      nodes.forEach((d, i) => { d.anchor = anchors[i]; const a = -Math.PI / 2 + (2 * Math.PI * i) / n + (n === 2 ? Math.PI / 2 : 0); d.off = [r * Math.cos(a), r * Math.sin(a)]; });
      return { id, nodes, home: c, c: c.slice(), R: r + LOGO_R + RING_W / 2 + 2, name: nodes[0].t.metro };
    });
    for (let it = 0; it < 60; it++) {
      let moved = false;
      for (let i = 0; i < metros.length; i++) for (let j = i + 1; j < metros.length; j++) {
        const a = metros[i], b = metros[j], dx = b.c[0] - a.c[0], dy = b.c[1] - a.c[1], d = Math.hypot(dx, dy) || 0.01, need = a.R + b.R + 18;
        if (d < need) { const push = (need - d) / 2, ux = dx / d, uy = dy / d; a.c[0] -= ux * push; a.c[1] -= uy * push; b.c[0] += ux * push; b.c[1] += uy * push; moved = true; }
      }
      for (const m of metros) { m.c[0] += (m.home[0] - m.c[0]) * 0.02; m.c[1] += (m.home[1] - m.c[1]) * 0.02; }
      if (!moved) break;
    }
    for (const m of metros) for (const d of m.nodes) d.pos = [m.c[0] + d.off[0], m.c[1] + d.off[1]];
    return metros;
  }
  function positionOverlay() {
    if (!view) return;
    gDots.style('display', state.level === 1 ? null : 'none');
    if (state.level === 1) {
      gDots.selectAll('circle').data(view.all, d => d.franchise_id + d.league).join('circle')
        .attr('cx', d => T.apply(proj([d.lon, d.lat]))[0]).attr('cy', d => T.apply(proj([d.lon, d.lat]))[1])
        .attr('r', d => d.scored ? 2.2 : 5).attr('fill', d => d.scored ? 'var(--ink)' : 'none')
        .attr('stroke', d => d.scored ? 'none' : '#8a909c').attr('stroke-width', 2.5).attr('opacity', d => d.scored ? .55 : 1).attr('pointer-events', 'none');
      gLeaders.selectAll('*').remove(); gLabels.selectAll('*').remove();
      drawSelMarker(); return;
    }
    const metros = layoutLogos();
    gLogos.selectAll('g.dm-logo').attr('transform', d => `translate(${d.pos[0]},${d.pos[1]})`)
      .classed('other', d => state.focus && d.t.region_id !== state.focus)
      .classed('on', d => sameTeam(d.t, state.team));
    const far = logoNodes.filter(d => Math.hypot(d.pos[0] - d.anchor[0], d.pos[1] - d.anchor[1]) > LOGO_R + 4);
    gLeaders.selectAll('g').data(far, d => d.key).join(e => { const g = e.append('g'); g.append('line').attr('class', 'dm-leader'); g.append('circle').attr('class', 'dm-venue').attr('r', 2.5); return g; })
      .each(function (d) { d3.select(this).select('line').attr('x1', d.anchor[0]).attr('y1', d.anchor[1]).attr('x2', d.pos[0]).attr('y2', d.pos[1]);
        d3.select(this).select('circle').attr('cx', d.anchor[0]).attr('cy', d.anchor[1]); });
    gLabels.selectAll('text').data(metros, d => d.id).join('text').attr('class', 'dm-metro')
      .classed('other', d => state.focus && d.nodes[0].t.region_id !== state.focus)
      .attr('x', d => d.c[0]).attr('y', d => d.c[1] + d.R + 13).text(d => d.name);
    drawSelMarker();
  }
  /** Level 1: the selected team as a small badge with its name at its venue (M45). */
  function drawSelMarker() {
    const t = selTeam(), show = !!t && state.level === 1 && state.view !== 'scatter';
    const data = show ? [{ t, key: 'sel' }] : [];
    const g = gSel.selectAll('g.dm-selmark').data(data, d => d.key).join(e => { const g = e.append('g').attr('class', 'dm-selmark dm-logo on'); badge(g, 15); g.append('text').attr('class', 'dm-metro selname'); return g; });
    if (!show) return;
    const p = T.apply(proj([t.lon, t.lat]));
    g.attr('transform', `translate(${p[0]},${p[1]})`).attr('pointer-events', 'none');
    fillBadge(g); g.select('.selname').attr('y', 32).text(t.season_team_name);
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
      if (instant || !ms(1)) { sel.style('opacity', 1); gLabels.style('opacity', 1); return; }
      sel.style('opacity', 0).transition().delay(d => ms(rank.get(d.key) * step)).duration(ms(140)).style('opacity', 1);
      gLabels.style('opacity', 0).transition().delay(ms(120)).duration(ms(200)).style('opacity', 1);
    });
  }

  // ---------- scatter (M45) ----------
  const sc = { svg: d3.select('#dm-sc-svg'), W: 0, H: 0, m: { l: 52, r: 16, t: 12, b: 44 } };
  sc.g = sc.svg.append('g'); sc.gGrid = sc.g.append('g'); sc.gPts = sc.g.append('g'); sc.gSel = sc.g.append('g');
  const sxs = () => d3.scaleLinear().domain([0, 100]).range([sc.m.l, sc.W - sc.m.r]);
  const sys = () => d3.scaleLinear().domain([0, 100]).range([sc.H - sc.m.b, sc.m.t]);
  function layoutScatter() {
    const box = $('#dm-sc-box'); sc.W = box.clientWidth || 600; sc.H = Math.round(Math.max(300, Math.min(470, sc.W * 0.48)));
    sc.svg.attr('width', sc.W).attr('height', sc.H).attr('viewBox', `0 0 ${sc.W} ${sc.H}`);
  }
  function drawScatter() {
    if (state.view === 'map') return;
    const x = sxs(), y = sys(), act = isActual();
    const scL = scatterLeagues(), noSt = shownLeagues().filter(l => !has(l, 'standing'));
    $('#dm-sc-title').innerHTML = `This season vs. the next three <span class="k">(${act ? 'actual' : 'projected'} standing; ${esc(scL.map(l => l + ' ' + seasonLabel(l, state.season)).join(' · '))})</span>`;
    $('#dm-sc-key').innerHTML = LEAGUES.filter(l => scL.includes(l)).map(l =>
      `<span><svg width="14" height="14" aria-hidden="true"><path transform="translate(7,7)" d="${d3.symbol(SYM.get(l), 70)()}" fill="var(--muted)"/></svg>${esc(l)}</span>`).join('') +
      `<span class="k">Color = ${modeWord()} doom</span>` + (noSt.length ? `<span class="k">Not shown: ${esc(noSt.join(', '))} (no standing in the scores)</span>` : '');
    sc.svg.attr('aria-label', `Scatter of ${view.all.length} teams: this season's standing against the ${act ? 'actual' : 'projected'} standing over the next three seasons`);
    const g = sc.gGrid; g.selectAll('*').remove();
    g.append('rect').attr('x', x(50)).attr('y', y(100)).attr('width', x(100) - x(50)).attr('height', y(50) - y(100)).attr('class', 'quadbg');
    g.append('rect').attr('x', x(0)).attr('y', y(50)).attr('width', x(50) - x(0)).attr('height', y(0) - y(50)).attr('class', 'quadbg');
    g.append('g').attr('transform', `translate(0,${y(0)})`).call(d3.axisBottom(x).ticks(5).tickSize(-(y(0) - y(100)))).attr('class', 'scaxis');
    g.append('g').attr('transform', `translate(${x(0)},0)`).call(d3.axisLeft(y).ticks(5).tickSize(-(x(100) - x(0)))).attr('class', 'scaxis');
    g.append('line').attr('x1', x(50)).attr('x2', x(50)).attr('y1', y(0)).attr('y2', y(100)).attr('class', 'midline');
    g.append('line').attr('x1', x(0)).attr('x2', x(100)).attr('y1', y(50)).attr('y2', y(50)).attr('class', 'midline');
    for (const [lx, ly, t, a] of [[98, 97, 'Contender', 'end'], [2, 97, 'Rising', 'start'], [98, 3, 'Cliff ahead', 'end'], [2, 3, 'Stuck', 'start']])
      g.append('text').attr('x', x(lx)).attr('y', y(ly) + (ly > 50 ? 12 : -4)).attr('text-anchor', a).attr('class', 'quadlbl').text(t);
    g.append('text').attr('x', (x(0) + x(100)) / 2).attr('y', sc.H - 8).attr('text-anchor', 'middle').attr('class', 'axlbl').text('Standing this season (league percentile) →');
    g.append('text').attr('transform', `translate(14,${(y(0) + y(100)) / 2}) rotate(-90)`).attr('text-anchor', 'middle').attr('class', 'axlbl')
      .text(act ? 'Actual standing, next 3 seasons (100 − actual doom) →' : 'Projected standing, next 3 seasons (100 − doom) →');
    const pts = view.all.filter(t => hasVal(t) && t.wpp != null);
    sc.gPts.selectAll('path.pt').data(pts, d => d.league + d.franchise_id).join('path').attr('class', 'pt')
      .attr('d', d => d3.symbol(SYM.get(d.league), 95)())
      .attr('transform', d => `translate(${x(d.wpp)},${y(100 - doomOf(d))})`)
      .attr('fill', d => colorOf(zOf(d))).attr('stroke', 'var(--ink)').attr('stroke-width', .8)
      .on('pointerenter', function (ev, d) { d3.select(this).raise(); if (ev.pointerType === 'touch' || pinned) return; const c = $('#dm-card'); c.innerHTML = teamCardHtml(d); placeCard(c, ev); hoverTeam(d); })
      .on('pointermove', ev => { if (ev.pointerType !== 'touch' && !pinned) placeCard($('#dm-card'), ev); })
      .on('pointerleave', () => { if (!pinned) { $('#dm-card').style.display = 'none'; hoverTeam(null); } })
      .on('click', (ev, d) => { if (touchy() && pinned !== 'team:' + d.franchise_id) { pinTeamCard(d, ev); return; } unpin(); select(d); });
    drawScatterFocus();
  }
  let hoveredTeam = null;
  function hoverTeam(t) { hoveredTeam = t; drawScatterFocus(); }
  function drawScatterFocus() {
    if (state.view === 'map' || !view) return;
    const rid = state.level === 2 ? state.focus : state.hover;
    sc.gPts.selectAll('path.pt').classed('faded', d => !!rid && d.region_id !== rid).classed('hot', d => sameTeam(d, hoveredTeam));
    const t = selTeam(), x = sxs(), y = sys();
    const data = t && hasVal(t) && t.wpp != null ? [{ t, key: 'sel' }] : [];
    const g = sc.gSel.selectAll('g.dm-logo').data(data, d => d.key).join(e => { const g = e.append('g').attr('class', 'dm-logo on'); badge(g, 15);
      g.append('text').attr('class', 'dm-metro selname'); return g; });
    if (!data.length) return;
    const px = x(t.wpp), py = y(100 - doomOf(t));
    g.attr('transform', `translate(${px},${py})`).attr('pointer-events', 'none');
    fillBadge(g);
    g.select('.selname').attr('y', py < sc.m.t + 40 ? 34 : -24).attr('text-anchor', px > sc.W - 90 ? 'end' : px < 90 ? 'start' : 'middle').text(t.season_team_name);
  }

  // ---------- selection, shared both ways (M45) ----------
  function select(t) {
    state.team = t ? { league: t.league, franchise_id: t.franchise_id } : null;
    drawSide(); positionOverlay(); drawScatterFocus(); writeHash();
    $('#dm-card').style.display = 'none';
    root.dataset.selected = t ? t.franchise_id : '';
  }

  // ---------- search (M46) ----------
  const sInput = $('#dm-search'), sList = $('#dm-results');
  let results = [], activeOpt = -1;
  function searchIndex() {
    const items = [];
    for (const t of view.all) items.push({ kind: 'Team', label: t.season_team_name, sub: `${t.league} · ${t.city}`, keys: [t.season_team_name, t.team, t.franchise_id.replace(/-/g, ' ')], go: () => { select(t); zoomToRegion(t.region_id); } });
    for (const [m, ts] of d3.groups(view.all, t => t.metro)) items.push({ kind: 'City', label: m, sub: `${ts.length} team${ts.length > 1 ? 's' : ''} · ${REG.get(ts[0].region_id)?.display_name}`,
      keys: [m, ...ts.map(t => t.city.replace(/ [A-Z]{2}$/, ''))], go: () => zoomToRegion(ts[0].region_id) });
    for (const r of D.regions) items.push({ kind: 'Region', label: r.display_name, sub: r.core_metros, keys: [r.display_name, r.core_metros, r.short_id], go: () => zoomToRegion(r.region_id) });
    return items;
  }
  const norm = s => String(s).normalize('NFKD').replace(/[̀-ͯ]/g, '').toLowerCase();
  function runSearch() {
    const q = norm(sInput.value.trim());
    if (!q) { closeResults(); return; }
    results = searchIndex().map(it => { const ks = it.keys.map(norm); const best = Math.min(...ks.map(k => k.startsWith(q) ? 0 : k.split(/[\s,–-]+/).some(w => w.startsWith(q)) ? 1 : k.includes(q) ? 2 : 9)); return { it, best }; })
      .filter(r => r.best < 9).sort((a, b) => a.best - b.best || a.it.label.localeCompare(b.it.label)).slice(0, 8).map(r => r.it);
    activeOpt = results.length ? 0 : -1;
    sList.innerHTML = results.length ? results.map((r, i) => `<li role="option" id="dm-opt-${i}" aria-selected="${i === activeOpt}"><b>${esc(r.label)}</b> <span class="k">${esc(r.kind)} · ${esc(r.sub)}</span></li>`).join('')
      : `<li class="k" role="option" aria-disabled="true">No team, city or region matches</li>`;
    sList.hidden = false; sInput.setAttribute('aria-expanded', 'true');
    sInput.setAttribute('aria-activedescendant', activeOpt >= 0 ? 'dm-opt-0' : '');
    sList.querySelectorAll('li[id]').forEach((li, i) => li.addEventListener('pointerdown', e => { e.preventDefault(); choose(i); }));
  }
  function closeResults() { sList.hidden = true; sInput.setAttribute('aria-expanded', 'false'); }
  function choose(i) { const r = results[i]; if (!r) return; closeResults(); sInput.value = r.label; r.go(); }
  sInput.addEventListener('input', runSearch);
  sInput.addEventListener('keydown', e => {
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault(); if (!results.length) return;
      activeOpt = (activeOpt + (e.key === 'ArrowDown' ? 1 : results.length - 1)) % results.length;
      sList.querySelectorAll('li[id]').forEach((li, i) => li.setAttribute('aria-selected', String(i === activeOpt)));
      sInput.setAttribute('aria-activedescendant', 'dm-opt-' + activeOpt);
    } else if (e.key === 'Enter') { e.preventDefault(); choose(Math.max(0, activeOpt)); }
  });
  sInput.addEventListener('blur', () => setTimeout(closeResults, 120));

  // ---------- update cycle ----------
  function update(opts = {}) {
    document.documentElement.dataset.theme = state.theme === 'auto' ? '' : state.theme;
    if (state.theme === 'auto') document.documentElement.removeAttribute('data-theme');
    view = regionStats(state.season, state.leagues);
    prepped = H.prepTeams(view.scored.map(t => ({ ...t, z: zOf(t) })));
    $('#dm-empty').style.display = state.leagues.size ? 'none' : 'flex';
    applyView();
    if (opts.layout) layout();
    gWorld.attr('transform', T.toString());
    drawControls(); drawLegend(); drawBanner(); drawSide(); drawCrumb(); drawFocusLayers(); buildLogos(); positionOverlay(); drawScatter(); paintHeat();
    if (state.level === 2) revealLogos(true);
    if (state.hover && state.level === 1 && !pinned) setHover(state.hover, state.hoverFrom);
    writeHash();
  }
  matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => { if (state.theme === 'auto') update(); });
  let rt; const ro = new ResizeObserver(() => { clearTimeout(rt); rt = setTimeout(() => {
    cache.clearViews(); update({ layout: true });
    if (state.level === 2 && state.focus) svg.call(zoom.transform, regionTransform(state.focus));
  }, 120); });
  ro.observe($('#dm-wrap')); ro.observe($('#dm-sc-box'));
  applyView(); snapSeason();
  update({ layout: true });
  if (pendingRegion && state.view !== 'scatter') { const t = regionTransform(pendingRegion); animating = true; svg.call(zoom.transform, t); animating = false; enterLevel2(pendingRegion, true); settle(); revealLogos(true); }
  window.DoomMap = { state, update, setHover, regionStats, view: () => view, cache, zoomToRegion, zoomOut, transform: () => T, preload, select,
    startFrameLog: () => { frameLog = []; }, stopFrameLog: () => { const f = frameLog; frameLog = null; return f; } };
})();
