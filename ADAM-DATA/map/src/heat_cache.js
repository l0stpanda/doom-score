/* Doom Map heat cache (decision M35): precomputes and caches heat rasters so season changes and zoom animations do
 * not redraw from scratch.
 *   view  = one camera framing (continent, or a zoomed region): its node grid and land mask, computed once.
 *   field = blurred S/W on a view's grid for one data key (season + leagues): computed in Web Workers, cached.
 *   image = a field coloured for one style key (palette + theme): an offscreen canvas, LRU-cached.
 * Requests are prioritised (what is on screen first, then prefetches nearest-first); duplicate requests share one job.
 * Falls back to the main thread if workers are unavailable.
 */
(function (root) {
  const H = root.DoomHeat;

  function HeatCache({ sigma, smooth, workerSource, imageLimit = 24 }) {
    const views = new Map(), fields = new Map(), inflight = new Map(), images = new Map();
    const queue = [];
    let seq = 0, workers = [], idle = [];
    const stats = { fieldsComputed: 0, fieldHits: 0, imageHits: 0, imagesColored: 0, workerMs: 0 };
    try {
      const url = URL.createObjectURL(new Blob([workerSource], { type: 'text/javascript' }));
      const n = Math.max(1, Math.min(3, (navigator.hardwareConcurrency || 2) - 1));
      for (let i = 0; i < n; i++) {
        const w = new Worker(url);
        w.onmessage = e => done(w, e.data);
        workers.push(w); idle.push(w);
      }
    } catch (err) { workers = []; idle = []; }
    const pending = new Map();   // job id -> {resolve, t0, key}

    function done(w, msg) {
      const p = pending.get(msg.id); pending.delete(msg.id);
      stats.workerMs += performance.now() - p.t0; stats.fieldsComputed++;
      const f = { S: msg.S, W: msg.W, gw: msg.gw, gh: msg.gh, step: msg.step };
      fields.set(p.key, f); inflight.delete(p.key); p.resolve(f);
      idle.push(w); pump();
    }
    function pump() {
      queue.sort((a, b) => a.priority - b.priority);
      while (idle.length && queue.length) {
        const job = queue.shift(), w = idle.pop(), id = ++seq;
        pending.set(id, { resolve: job.resolve, t0: performance.now(), key: job.key });
        const grid = job.view.grid();
        w.postMessage({ id, grid: { nodes: grid.nodes, gw: grid.gw, gh: grid.gh, step: grid.step }, teams: job.teams, sigma, smooth });
      }
    }

    /** Register (or reuse) a view. invert: canvas px -> [lon, lat]; drawLand(ctx2d) draws the land path. */
    function view(key, width, height, step, invert, drawLand) {
      if (!views.has(key)) {
        let grid = null, mask = null;
        views.set(key, { key, width, height,
          grid: () => grid || (grid = H.nodeGrid(invert, width, height, step)),
          mask: () => mask || (mask = H.landMask(width, height, drawLand)) });
      }
      return views.get(key);
    }

    /** Field for (view, dataKey). priority: 0 = needed now, larger = later. */
    function field(v, dataKey, teams, priority = 0) {
      const key = v.key + '|' + dataKey;
      if (fields.has(key)) { stats.fieldHits++; return Promise.resolve(fields.get(key)); }
      if (inflight.has(key)) {
        const j = queue.find(q => q.key === key); if (j) j.priority = Math.min(j.priority, priority);
        return inflight.get(key);
      }
      const pr = new Promise(resolve => {
        if (!workers.length) {                      // main-thread fallback
          const t0 = performance.now(), f = H.field(v.grid(), teams, sigma, smooth);
          stats.workerMs += performance.now() - t0; stats.fieldsComputed++;
          fields.set(key, f); resolve(f); return;
        }
        queue.push({ key, view: v, teams, priority, resolve }); pump();
      });
      inflight.set(key, pr); pr.then(() => inflight.delete(key));
      return pr;
    }

    /** Coloured image (offscreen canvas) for (view, dataKey, styleKey). */
    async function image(v, dataKey, teams, styleKey, colorOpts, priority = 0) {
      const key = v.key + '|' + dataKey + '|' + styleKey;
      if (images.has(key)) { const c = images.get(key); images.delete(key); images.set(key, c); stats.imageHits++; return c; }
      const f = await field(v, dataKey, teams, priority);
      if (images.has(key)) return images.get(key);
      const c = document.createElement('canvas'); c.width = v.width; c.height = v.height;
      H.colorize(c.getContext('2d'), v.width, v.height, f, { ...colorOpts, mask: v.mask() });
      stats.imagesColored++;
      images.set(key, c);
      while (images.size > imageLimit) images.delete(images.keys().next().value);
      return c;
    }
    const hasImage = (v, dataKey, styleKey) => images.has(v.key + '|' + dataKey + '|' + styleKey);
    const hasField = (v, dataKey) => fields.has(v.key + '|' + dataKey);
    function clearViews(except) {                    // drop views (and their fields/images) after a resize
      for (const k of [...views.keys()]) if (!except || !except(k)) {
        views.delete(k);
        for (const fk of [...fields.keys()]) if (fk.startsWith(k + '|')) fields.delete(fk);
        for (const ik of [...images.keys()]) if (ik.startsWith(k + '|')) images.delete(ik);
      }
      for (let i = queue.length - 1; i >= 0; i--) if (!views.has(queue[i].view.key)) queue.splice(i, 1);
    }
    return { view, field, image, hasImage, hasField, clearViews, stats, workers: () => workers.length };
  }
  root.DoomHeatCache = HeatCache;
})(window);
