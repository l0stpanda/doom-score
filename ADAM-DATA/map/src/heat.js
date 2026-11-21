/* Doom Map heat surface (shared by the map component, its Web Worker and the Phase-1 test renders).
 *
 * Local outlook at a point = sum(w_i z_i) / sum(w_i), w_i = exp(-d_i^2 / 2 sigma^2), d = great-circle miles.
 * Opacity = smootherstep of (W - w0) / (w1 - w0): 0 at w0, 1 at w1, flat at both ends so the full-opacity contour does
 * not show as an edge (decision M26); colour = palette LUT at the scale position of the outlook; the two are mixed in
 * OKLab over the "no teams nearby" grey.
 * Render-time smoothing (M26): S = sum(w z) and W = sum(w) are evaluated on a coarse grid of nodes, both blurred with a
 * small Gaussian (so the result is still a weighted average), bilinearly upsampled, and an ordered dither removes
 * 8-bit banding. The land mask is filled and stroked in one colour so hairline gaps between regions never show.
 * Pipeline (M35): nodeGrid (needs the projection, main thread) -> field (pure maths, runs in a Worker) -> colorize.
 */
(function (root) {
  const RAD = Math.PI / 180, EARTH_MI = 3958.8;
  const toLin = c => c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  const toSrgb = c => c <= 0.0031308 ? 12.92 * c : 1.055 * Math.pow(Math.max(c, 0), 1 / 2.4) - 0.055;
  const hex = h => [1, 3, 5].map(i => parseInt(h.slice(i, i + 2), 16) / 255);
  function oklab([r, g, b]) {
    r = toLin(r); g = toLin(g); b = toLin(b);
    const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b);
    const m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b);
    const s = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b);
    return [0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s, 1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
            0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s];
  }
  function srgb8([L, a, b]) {
    const l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3, m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3,
          s = (L - 0.0894841775 * a - 1.2914855480 * b) ** 3;
    return [4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s, -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
            -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s].map(v => Math.round(Math.min(1, Math.max(0, toSrgb(v))) * 255));
  }

  /** Scale position t in [0, 1] of a z value: 0 = bright future (z_lo), 0.5 = league average, 1 = doomed (z_hi). */
  const position = (z, zlo, zhi) => z < 0 ? 0.5 * (1 - Math.max(z, zlo) / zlo) : 0.5 + 0.5 * Math.min(z, zhi) / zhi;

  /** Colour table: 256 positions x 33 opacity levels, OKLab mix over grey, as packed RGB bytes. */
  function colorTable(lutHex, greyHex) {
    const grey = oklab(hex(greyHex)), lut = lutHex.map(h => oklab(hex(h)));
    const T = new Uint8ClampedArray(256 * 33 * 3);
    for (let i = 0; i < 256; i++) for (let a = 0; a <= 32; a++) {
      const u = a / 32, c = srgb8(lut[i].map((v, k) => grey[k] + (v - grey[k]) * u));
      T.set(c, (i * 33 + a) * 3);
    }
    return T;
  }

  function prepTeams(teams) {
    return teams.map(t => ({ phi: t.lat * RAD, lam: t.lon * RAD, cos: Math.cos(t.lat * RAD), z: t.z, t }));
  }
  function miles(phi, lam, cphi, t) {
    const a = Math.sin((t.phi - phi) / 2) ** 2 + cphi * t.cos * Math.sin((t.lam - lam) / 2) ** 2;
    return 2 * EARTH_MI * Math.asin(Math.min(1, Math.sqrt(a)));
  }
  /** Weights of every team at one lon/lat (for hover read-outs). */
  function weightsAt(lonlat, prepped, sigma) {
    const phi = lonlat[1] * RAD, lam = lonlat[0] * RAD, cphi = Math.cos(phi), two = 2 * sigma * sigma;
    return prepped.map(t => { const d = miles(phi, lam, cphi, t); return { team: t.t, d, w: Math.exp(-d * d / two) }; });
  }

  function blur(arr, gw, gh, sigmaCells) {
    if (!(sigmaCells > 0)) return arr;
    const r = Math.ceil(sigmaCells * 2.5), k = [];
    let s = 0;
    for (let i = -r; i <= r; i++) { const v = Math.exp(-i * i / (2 * sigmaCells * sigmaCells)); k.push(v); s += v; }
    for (let i = 0; i < k.length; i++) k[i] /= s;
    const tmp = new Float32Array(arr.length), out = new Float32Array(arr.length);
    for (let j = 0; j < gh; j++) for (let i = 0; i < gw; i++) {           // rows
      let acc = 0;
      for (let q = -r; q <= r; q++) acc += k[q + r] * arr[j * gw + Math.min(gw - 1, Math.max(0, i + q))];
      tmp[j * gw + i] = acc;
    }
    for (let j = 0; j < gh; j++) for (let i = 0; i < gw; i++) {           // columns
      let acc = 0;
      for (let q = -r; q <= r; q++) acc += k[q + r] * tmp[Math.min(gh - 1, Math.max(0, j + q)) * gw + i];
      out[j * gw + i] = acc;
    }
    return out;
  }

  /** Grid nodes every `step` canvas px, as lon/lat pairs (NaN where the projection has no inverse). */
  function nodeGrid(invert, width, height, step) {
    const gw = Math.ceil(width / step) + 1, gh = Math.ceil(height / step) + 1, nodes = new Float32Array(gw * gh * 2);
    for (let j = 0; j < gh; j++) for (let i = 0; i < gw; i++) {
      const ll = invert([i * step, j * step]), k = (j * gw + i) * 2;
      nodes[k] = ll && isFinite(ll[0]) ? ll[0] : NaN; nodes[k + 1] = ll && isFinite(ll[1]) ? ll[1] : NaN;
    }
    return { nodes, gw, gh, step };
  }

  /** Blurred S and W on the node grid. Pure maths: safe to run in a Worker. teams: [{lat, lon, z}]. */
  function field(grid, teams, sigma, smooth) {
    const { nodes, gw, gh } = grid, P = prepTeams(teams), two = 2 * sigma * sigma;
    const S = new Float32Array(gw * gh), W = new Float32Array(gw * gh);
    for (let n = 0; n < gw * gh; n++) {
      const lon = nodes[2 * n], lat = nodes[2 * n + 1];
      if (lon !== lon) continue;
      const phi = lat * RAD, lam = lon * RAD, cphi = Math.cos(phi);
      let w = 0, s = 0;
      for (const t of P) { const d = miles(phi, lam, cphi, t), x = Math.exp(-d * d / two); w += x; s += x * t.z; }
      S[n] = s; W[n] = w;
    }
    const sm = smooth == null ? 2.5 : smooth;
    return { S: blur(S, gw, gh, sm), W: blur(W, gw, gh, sm), gw, gh, step: grid.step };
  }

  const BAYER = [0, 8, 2, 10, 12, 4, 14, 6, 3, 11, 1, 9, 15, 7, 13, 5].map(v => (v + 0.5) / 16 - 0.5);

  /** Colour a field into ctx (width x height canvas px). opts: { w0, w1, zlo, zhi, table, mask } */
  function colorize(ctx, width, height, f, opts) {
    const { S, W, gw, gh, step } = f;
    const img = ctx.createImageData(width, height), px = img.data, T = opts.table, mask = opts.mask;
    const { w0, w1, zlo, zhi } = opts;
    for (let y = 0; y < height; y++) {
      const gy = y / step, j0 = Math.min(gh - 2, Math.floor(gy)), fy = gy - j0;
      for (let x = 0; x < width; x++) {
        const k = y * width + x, ma = mask ? mask[k] : 255;
        if (ma === 0) continue;
        const gx = x / step, i0 = Math.min(gw - 2, Math.floor(gx)), fx = gx - i0, a = j0 * gw + i0;
        const s = (S[a] * (1 - fx) + S[a + 1] * fx) * (1 - fy) + (S[a + gw] * (1 - fx) + S[a + gw + 1] * fx) * fy;
        const w = (W[a] * (1 - fx) + W[a + 1] * fx) * (1 - fy) + (W[a + gw] * (1 - fx) + W[a + gw + 1] * fx) * fy;
        const d = BAYER[(y & 3) * 4 + (x & 3)];
        const tPos = position(w > 1e-9 ? s / w : 0, zlo, zhi);
        const ti = Math.min(255, Math.max(0, Math.round(tPos * 255 + d)));
        const u = Math.min(1, Math.max(0, (w - w0) / (w1 - w0))), al = u * u * u * (u * (6 * u - 15) + 10);
        const ai = Math.min(32, Math.max(0, Math.round(al * 32 + d)));
        const o = (ti * 33 + ai) * 3, p = k * 4;
        px[p] = T[o]; px[p + 1] = T[o + 1]; px[p + 2] = T[o + 2]; px[p + 3] = ma;
      }
    }
    ctx.putImageData(img, 0, 0);
  }

  /** One-shot paint (test renders): nodeGrid -> field -> colorize. opts as colorize plus proj, teams, sigma, step, smooth. */
  function paint(ctx, width, height, opts) {
    const grid = nodeGrid(p => opts.proj.invert(p), width, height, opts.step || 3);
    colorize(ctx, width, height, field(grid, opts.teams, opts.sigma, opts.smooth), opts);
  }

  /** Land mask from a d3 path generator bound to an offscreen context. */
  function landMask(width, height, drawLand) {
    const c = document.createElement('canvas'); c.width = width; c.height = height;
    const g = c.getContext('2d'); g.fillStyle = '#000'; g.strokeStyle = '#000'; g.lineWidth = 1.5; g.lineJoin = 'round';
    g.beginPath(); drawLand(g); g.fill(); g.stroke();
    const d = g.getImageData(0, 0, width, height).data, m = new Uint8ClampedArray(width * height);
    for (let i = 0; i < m.length; i++) m[i] = d[i * 4 + 3];
    return m;
  }

  root.DoomHeat = { paint, nodeGrid, field, colorize, landMask, colorTable, position, weightsAt, prepTeams, oklab, srgb8, hex };

  // Worker entry: { id, grid, teams, sigma, smooth } -> { id, S, W, gw, gh, step } (buffers transferred)
  if (typeof document === 'undefined' && typeof self !== 'undefined' && typeof postMessage === 'function') {
    self.onmessage = e => {
      const m = e.data, f = field(m.grid, m.teams, m.sigma, m.smooth);
      self.postMessage({ id: m.id, ...f }, [f.S.buffer, f.W.buffer]);
    };
  }
})(typeof window !== 'undefined' ? window : globalThis);
