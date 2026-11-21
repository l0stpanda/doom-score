/* Doom Map, Level 1 (continent overview).
 * Reads window.DOOM_MAP_DATA (built by map/build/build_page.mjs). Leagues, seasons, regions and teams all come from
 * the data; nothing here names a league. Heat surface: map/src/heat.js. Decisions: docs/MAP_DECISIONS.md.
 */
(function () {
  'use strict';
  const D = window.DOOM_MAP_DATA, X = D.derived, H = window.DoomHeat;
  const LEAGUES = X.leagues.slice().sort((a, b) => (D.leagues[a]?.order ?? 99) - (D.leagues[b]?.order ?? 99));
  const REG = new Map(D.regions.map(r => [r.region_id, r]));
  const V_LO = X.verdict_lo, V_HI = X.verdict_hi;            // M28 (revised): tertiles of pooled raw region averages
  const state = { season: X.default_season, leagues: new Set(LEAGUES), palette: 'default', theme: 'auto', hover: null, hoverFrom: null };

  // ---------- URL hash (season, leagues, palette, theme) ----------
  (function readHash() {
    const p = new URLSearchParams(location.hash.slice(1));
    if (p.has('season') && X.seasons.includes(+p.get('season'))) state.season = +p.get('season');
    if (p.has('leagues')) { const l = p.get('leagues').split(',').filter(x => LEAGUES.includes(x)); state.leagues = new Set(l); }
    if (p.has('palette') && D.palette.palettes[p.get('palette')]) state.palette = p.get('palette');
    if (['auto', 'light', 'dark'].includes(p.get('theme'))) state.theme = p.get('theme');
  })();
  function writeHash() {
    const p = new URLSearchParams({ season: state.season, leagues: [...state.leagues].join(','), palette: state.palette, theme: state.theme });
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
  const leaguesPresent = season => LEAGUES.filter(l => leagueSeasons(l).includes(season));
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
    return { prev, delta: b - a, leagues: [...both] };
  }

  // ---------- DOM ----------
  const root = $('#doom-map');
  root.innerHTML = `
  <header class="dm-head"><h1>Doom Map</h1>
    <p>How doomed is your part of the country? Color shows the outlook for the next three seasons, blended from nearby
    ${LEAGUES.join(' and ')} teams. Hover a region for its story; the list ranks every region.</p></header>
  <div class="dm-controls" role="toolbar" aria-label="Map controls">
    <span><span class="lbl" id="lg-l">Leagues</span><span class="dm-seg" id="dm-leagues" role="group" aria-labelledby="lg-l"></span></span>
    <span class="dm-season"><span class="lbl" id="se-l">Season</span>
      <button id="dm-prev" aria-label="Previous season">&#9664;</button><select id="dm-season" aria-labelledby="se-l"></select>
      <button id="dm-next" aria-label="Next season">&#9654;</button></span>
    <span><span class="lbl" id="pa-l">Colors</span><span class="dm-seg" id="dm-palette" role="group" aria-labelledby="pa-l"></span></span>
    <span><span class="lbl" id="th-l">Theme</span><span class="dm-seg" id="dm-theme" role="group" aria-labelledby="th-l"></span></span>
    <span class="dm-tag" id="dm-mode">Predicted doom</span>
  </div>
  <div class="dm-main">
    <div class="dm-mapcol">
      <div class="dm-mapwrap" id="dm-wrap">
        <canvas id="dm-heat" aria-hidden="true"></canvas>
        <svg id="dm-svg" role="img" aria-label="Doom map of the US and southern Canada"></svg>
        <div class="dm-banner" id="dm-banner" role="status"></div>
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

  // ---------- map geometry ----------
  const regionsFC = topojson.feature(D.topo, D.topo.objects.regions);
  const contextFC = topojson.feature(D.topo, D.topo.objects.context);
  const meshInner = topojson.mesh(D.topo, D.topo.objects.regions, (a, b) => a !== b && a.properties.region_id !== b.properties.region_id);
  const CROP = { type: 'Polygon', coordinates: [[[-127, 24], [-128, 56], [-60, 56], [-52, 47], [-66, 24], [-127, 24]]] };
  const makeProj = (w, h, k = 1) => d3.geoConicConformal().parallels([30, 52]).rotate([96, 0]).fitExtent([[8 * k, 8 * k], [w * k - 8 * k, h * k - 8 * k]], CROP);
  let W = 0, Hh = 0, proj, path, prepped = [], view = null;
  const svg = d3.select('#dm-svg');
  const gContext = svg.append('g'), gOutline = svg.append('path').attr('class', 'outline'), gDim = svg.append('path'),
        gHl = svg.append('path'), gDots = svg.append('g'), gHit = svg.append('g');

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
  }

  // ---------- heat (cached, M35) ----------
  const cache = window.DoomHeatCache({ sigma: X.sigma_mi, smooth: 2.5,
    workerSource: document.getElementById('dm-heat-src').textContent });
  const dprNow = () => Math.min(window.devicePixelRatio || 1, 2);
  const dataKey = (season, leagues) => season + '|' + [...leagues].sort().join(',');
  const styleKey = () => state.palette + '|' + themeNow();
  const tables = new Map();
  const tableFor = k => tables.get(k) || (tables.set(k, H.colorTable(lut(), greyOf())), tables.get(k));
  const colorOpts = () => ({ w0: X.opacity_w0, w1: X.opacity_w1, zlo: X.z_lo, zhi: X.z_hi, table: tableFor(styleKey()) });
  const teamsFor = (season, leagues) => D.teams.filter(t => t.season === season && leagues.has(t.league) && t.scored)
    .map(t => ({ lat: t.lat, lon: t.lon, z: t.z }));
  function baseView() {
    const dpr = dprNow(), cw = Math.round(W * dpr), ch = Math.round(Hh * dpr), pc = makeProj(W, Hh, dpr);
    return cache.view(`base:${cw}x${ch}`, cw, ch, Math.round(3 * dpr), p => pc.invert(p), g => d3.geoPath(pc, g)(regionsFC));
  }
  let heatJob = 0, prefetchTimer = 0;
  function paintHeat() {
    const job = ++heatJob, v = baseView(), dk = dataKey(state.season, state.leagues), t0 = performance.now();
    cache.image(v, dk, teamsFor(state.season, state.leagues), styleKey(), colorOpts(), 0).then(img => {
      if (job !== heatJob) return;
      const cv = $('#dm-heat'); cv.width = v.width; cv.height = v.height; cv.style.width = W + 'px'; cv.style.height = Hh + 'px';
      cv.getContext('2d').drawImage(img, 0, 0);
      root.dataset.painted = String(job); root.dataset.paintMs = String(Math.round(performance.now() - t0));
      clearTimeout(prefetchTimer); prefetchTimer = setTimeout(prefetch, 50);
    });
  }
  /** Background work: fields for every season of the current leagues (nearest first), then images for the
   *  neighbouring seasons so stepping through seasons is instant. */
  function prefetch() {
    const v = baseView(), seasons = availableSeasons().slice().sort((a, b) => Math.abs(a - state.season) - Math.abs(b - state.season));
    root.dataset.prefetched = '';
    seasons.forEach((s, i) => cache.field(v, dataKey(s, state.leagues), teamsFor(s, state.leagues), 10 + i));
    const near = seasons.slice(1, 3), sk = styleKey(), co = colorOpts();
    const idle = cb => (window.requestIdleCallback || (f => setTimeout(f, 30)))(cb);
    (function next(k) {
      if (k >= near.length) {
        Promise.all(seasons.map(s => cache.field(v, dataKey(s, state.leagues), teamsFor(s, state.leagues), 20)))
          .then(() => { root.dataset.prefetched = '1'; });
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

  // ---------- ranked list (M29 revised) ----------
  function drawList() {
    const host = $('#dm-list'), R = view.ranked, BW = 120, C0 = BW / 2;
    const ext = Math.max(0.25, ...R.map(s => Math.max(Math.abs(s.rawZ), Math.abs(s.shrunk))));
    const sx = v => C0 + v / ext * (C0 - 5);
    const bar = s => `<svg width="${BW}" height="16" aria-hidden="true">
      <line x1="${C0}" x2="${C0}" y1="0" y2="16" stroke="var(--muted)" stroke-opacity=".6"/>
      <rect x="${Math.min(sx(s.shrunk), C0)}" y="4" width="${Math.max(2, Math.abs(sx(s.shrunk) - C0))}" height="8" rx="1.5" fill="var(--ink)" fill-opacity=".7"/>
      <circle cx="${sx(s.rawZ)}" cy="8" r="4" fill="${colorOf(s.rawZ)}" stroke="var(--ink)" stroke-width="1.2"/></svg>`;
    host.innerHTML = `<h2>Regions ranked by outlook</h2>
      <p class="sub">Brightest first, by a reliability-adjusted average (bar): regions with few teams are pulled toward the
      overall average. Dot = raw average of the region's teams, in its map color. Center line = league average. n = teams scored.</p>
      <p class="sub caption"><b>Most differences between regions are within what chance alone would produce.</b></p>
      <div class="axis"><span></span><span></span><span><i>&larr; brighter</i><i>doomier &rarr;</i></span><span>n</span></div>
      <ol class="dm-rows" id="dm-rows">${R.map(s => `<li tabindex="0" data-region="${s.region.region_id}"
        aria-label="${esc(`${ord(s.rank)}: ${s.region.display_name}, ${words(s.rawZ)}, ${s.n} team${s.n === 1 ? '' : 's'}`)}">
        <span class="rk">${s.rank}</span><span class="nm">${esc(s.region.display_name)}</span>${bar(s)}<span class="n">${s.n}</span></li>`).join('')}</ol>
      ${view.empty.length ? `<h3>No scored teams this season</h3><ul class="dm-rows empty">${view.empty.map(s =>
        `<li><span class="rk">&ndash;</span><span class="nm">${esc(s.region.display_name)}${s.tooNew.length ? ` (${s.tooNew.length} too new)` : ''}</span></li>`).join('')}</ul>` : ''}`;
    for (const li of host.querySelectorAll('#dm-rows li')) {
      const id = li.dataset.region;
      li.addEventListener('mouseenter', () => setHover(id, 'list'));
      li.addEventListener('focus', () => setHover(id, 'list'));
      li.addEventListener('mouseleave', () => setHover(null));
      li.addEventListener('blur', () => setHover(null));
    }
  }

  // ---------- hover: highlight + card ----------
  function setHover(id, from, pt) {
    state.hover = id; state.hoverFrom = from;
    const others = { type: 'FeatureCollection', features: regionsFC.features.filter(f => f.properties.region_id !== id) };
    const me = regionsFC.features.find(f => f.properties.region_id === id);
    gDim.attr('d', id ? path(others) : null).attr('fill', 'var(--dim)').attr('pointer-events', 'none');
    gHl.attr('d', me ? path(me) : null).attr('fill', 'none').attr('stroke', 'var(--ink)').attr('stroke-width', 2).attr('pointer-events', 'none');
    for (const li of document.querySelectorAll('#dm-rows li')) li.classList.toggle('on', li.dataset.region === id);
    if (from === 'map') { const li = document.querySelector(`#dm-rows li[data-region="${id}"]`); if (li) li.scrollIntoView({ block: 'nearest' }); }
    const card = $('#dm-card');
    if (!id) { card.style.display = 'none'; return; }
    card.innerHTML = cardHtml(view.byRegion.get(id), pt);
    card.style.display = 'block';
    let x, y;
    if (pt) { x = pt.clientX + 16; y = pt.clientY + 16; }
    else { const r = $('#dm-wrap').getBoundingClientRect(), c = path.centroid(me); x = r.left + c[0] + 12; y = r.top + c[1] + 12; }
    const cw = card.offsetWidth, chh = card.offsetHeight;
    if (x + cw > innerWidth - 8) x = (pt ? pt.clientX - 16 : x - 24) - cw;
    if (y + chh > innerHeight - 8) y = Math.max(8, innerHeight - 8 - chh);
    card.style.left = Math.max(8, x) + 'px'; card.style.top = y + 'px';
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
    const r = $('#dm-wrap').getBoundingClientRect(), ll = proj.invert([pt.clientX - r.left, pt.clientY - r.top]);
    if (!ll || !prepped.length) return '';
    const ws = H.weightsAt(ll, prepped, X.sigma_mi), tot = ws.reduce((a, b) => a + b.w, 0);
    const near = ws.slice().sort((a, b) => a.d - b.d).slice(0, 3);
    const nm = t => esc(t.season_team_name);
    const nearTxt = near.map(n => `${nm(n.team)} <span>${Math.round(n.d)} mi</span>`).join(' · ');
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
      <div class="trend">${spark(r.region_id)}<span>${chTxt}</span></div>${spotHtml(pt)}`;
  }

  svg.on('pointermove', ev => {
    const t = ev.target.closest && ev.target.closest('[data-region]');
    if (t) setHover(t.getAttribute('data-region'), 'map', ev);
    else if (state.hoverFrom === 'map') setHover(null);
  });
  svg.on('pointerleave', () => { if (state.hoverFrom === 'map') setHover(null); });

  // ---------- dots (venues) ----------
  function drawDots() {
    gDots.selectAll('circle').data(view.all, d => d.franchise_id).join('circle')
      .attr('cx', d => proj([d.lon, d.lat])[0]).attr('cy', d => proj([d.lon, d.lat])[1])
      .attr('r', d => d.scored ? 2.2 : 5).attr('fill', d => d.scored ? 'var(--ink)' : 'none')
      .attr('stroke', d => d.scored ? 'none' : '#8a909c').attr('stroke-width', 2.5).attr('opacity', d => d.scored ? .55 : 1)
      .attr('pointer-events', 'none');
  }

  // ---------- update cycle ----------
  function update(opts = {}) {
    document.documentElement.dataset.theme = state.theme === 'auto' ? '' : state.theme;
    if (state.theme === 'auto') document.documentElement.removeAttribute('data-theme');
    view = regionStats(state.season, state.leagues);
    prepped = H.prepTeams(view.scored.map(t => ({ ...t, z: t.z })));
    $('#dm-empty').style.display = state.leagues.size ? 'none' : 'flex';
    if (opts.layout) layout();
    drawControls(); drawLegend(); drawBanner(); drawList(); drawDots(); paintHeat();
    if (state.hover) setHover(state.hover, state.hoverFrom);
    writeHash();
  }
  matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => { if (state.theme === 'auto') update(); });
  let rt; new ResizeObserver(() => { clearTimeout(rt); rt = setTimeout(() => { cache.clearViews(); update({ layout: true }); }, 120); }).observe($('#dm-wrap'));
  snapSeason();
  update({ layout: true });
  window.DoomMap = { state, update, setHover, regionStats, view: () => view, cache };   // for tests / screenshots
})();
