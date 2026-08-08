/* ============================================================================
   Flanner — festival artwork generator
   ----------------------------------------------------------------------------
   Turns a festival name into a unique variant of the category artwork, the way
   an identicon turns a username into an avatar — but constrained so every
   result still belongs to the same design system.

   THE IDEA
   Two independent inputs, deliberately separated:

     1. SHAPE comes from the first letter.
        The letter is rasterised once and read column by column. Each column's
        ink density becomes one amplitude — treat the glyph as a spectrum and
        the ink as loudness. "F" has a solid stem then thin arms, so it falls
        away to the right. "O" is loud at both edges and quiet in the middle.
        This is what ties the artwork to the name: the silhouette of the bars
        is the letter's own density profile.

     2. RHYTHM comes from the whole name.
        An FNV-1a hash seeds a mulberry32 PRNG. Every remaining parameter —
        band count, contrast, per-band jitter, peak-cap offsets, and the
        background composition — is drawn from that stream, in a fixed order,
        so the same name always produces the same artwork.

   WHAT IS *NOT* RANDOMISED
   Colour. Every fill is a CSS variable from the category palette, so artwork
   stays green for music, amber for art, purple for film, and follows the
   theme. Randomising hue is what makes identicon systems look like noise;
   here only geometry varies, inside clamped ranges, so no name can produce
   an off-brand result.

   ONE SIGNAL, THREE RENDERERS
   The same amplitudes drive all three category motifs: bars for music, a
   spline for art, lit frames for film.

   USAGE
     await FlannerArt.ready();                       // waits for the webfont
     const { svg, meta } = FlannerArt.artFor('Vive Latino', { category:'music' });
     el.innerHTML = svg;

   DETERMINISM NOTE
   The hash half is deterministic everywhere. The profile half depends on how
   the browser rasterises the glyph, so a machine without Inter can differ
   slightly. Call FlannerArt.bakeProfiles() once, paste the result into
   BAKED_PROFILES below, and the generator becomes fully deterministic and
   works server-side without a canvas.
   ========================================================================== */

var __root = typeof window !== 'undefined' ? window : globalThis;
__root.FlannerArt = (function () {
  'use strict';

  /* ---- geometry constants (the 400×250 artwork box) ---- */
  const W = 400, H = 250;
  const CX = 200, CY = 128;        // centre of the signal block
  const BLOCK = 178;               // its total width
  const GAP = 11;
  const MIN_H = 34, MAX_H = 128;   // amplitude range, clamped so nothing degenerates

  const FONT = '700 %spx Inter, "Segoe UI", system-ui, sans-serif';

  /* Paste the output of bakeProfiles() here for full determinism. */
  /* Baked in a browser with Inter loaded, by FlannerArt.bakeProfiles(). With
     these the generator needs no canvas and no webfont, so the build can run
     it in Node and every machine produces byte-identical artwork. */
  const BAKED_PROFILES = {"0":[0.497,0.816,0.981,0.765,0.421,0.342,0.336,0.406,0.675,1,0.846,0.521],"1":[0.208,0.212,0.209,0.204,0.184,0.153,0.71,1,1,1,1,1],"2":[0.399,0.637,0.777,0.795,0.753,0.759,0.759,0.804,1,0.975,0.827,0.507],"3":[0.211,0.436,0.543,0.515,0.518,0.513,0.52,0.627,0.963,1,0.816,0.403],"4":[0.237,0.349,0.461,0.537,0.539,0.531,0.445,0.896,1,1,0.324,0.185],"5":[0.269,0.906,1,0.949,0.604,0.597,0.61,0.68,0.882,0.942,0.801,0.375],"6":[0.452,0.818,1,0.95,0.623,0.532,0.529,0.59,0.827,0.958,0.789,0.419],"7":[0.2,0.26,0.473,0.68,0.88,0.98,0.984,1,0.947,0.74,0.54,0.32],"8":[0.275,0.75,0.983,0.995,0.63,0.493,0.486,0.591,0.953,1,0.801,0.336],"9":[0.371,0.744,0.929,0.843,0.605,0.522,0.517,0.583,0.886,1,0.842,0.479],"A":[0.181,0.519,0.84,0.965,0.986,0.632,0.674,1,0.947,0.829,0.507,0.183],"B":[1,1,1,0.639,0.459,0.459,0.473,0.575,0.864,0.939,0.792,0.384],"C":[0.506,0.834,1,0.641,0.454,0.395,0.371,0.408,0.499,0.68,0.578,0.327],"D":[1,1,1,0.32,0.318,0.329,0.345,0.394,0.546,0.88,0.747,0.479],"E":[1,1,1,0.899,0.494,0.494,0.494,0.494,0.494,0.494,0.494,0.4],"F":[1,1,1,0.866,0.294,0.294,0.294,0.294,0.294,0.294,0.294,0.153],"G":[0.465,0.834,1,0.656,0.471,0.402,0.481,0.609,0.728,0.907,0.781,0.45],"H":[1,1,1,0.19,0.19,0.19,0.19,0.19,0.19,0.865,1,1],"I":[1,1,1,1,1,1,1,1,1,1,1,1],"J":[0.21,0.305,0.356,0.359,0.217,0.188,0.188,0.217,0.873,1,0.951,0.851],"K":[1,1,1,0.264,0.28,0.43,0.644,0.702,0.632,0.455,0.25,0.067],"L":[1,1,1,1,0.188,0.188,0.188,0.188,0.188,0.188,0.188,0.188],"M":[1,1,0.562,0.563,0.607,0.463,0.438,0.604,0.576,0.539,1,1],"N":[0.998,1,1,0.411,0.371,0.373,0.373,0.373,0.363,0.878,1,1],"O":[0.495,0.855,1,0.631,0.473,0.412,0.407,0.455,0.61,0.998,0.896,0.541],"P":[1,1,1,0.576,0.294,0.294,0.304,0.361,0.551,0.602,0.522,0.284],"Q":[0.452,0.749,0.876,0.564,0.437,0.433,0.53,0.572,0.575,1,0.938,0.541],"R":[1,1,1,0.537,0.306,0.31,0.425,0.622,0.959,0.896,0.651,0.202],"S":[0.359,0.776,0.985,0.927,0.718,0.663,0.656,0.701,0.883,1,0.832,0.42],"T":[0.118,0.118,0.118,0.118,0.559,1,1,0.561,0.118,0.118,0.118,0.118],"U":[0.826,0.936,0.994,0.4,0.227,0.209,0.209,0.223,0.275,1,0.943,0.826],"V":[0.144,0.461,0.801,0.985,0.896,0.527,0.442,0.828,1,0.869,0.527,0.18],"W":[0.254,0.784,1,0.51,0.854,0.74,0.688,0.913,0.507,0.933,0.878,0.309],"X":[0.102,0.387,0.717,0.97,0.991,0.666,0.647,0.988,1,0.738,0.399,0.109],"Y":[0.105,0.291,0.479,0.614,0.79,1,0.963,0.91,0.631,0.498,0.309,0.119],"Z":[0.441,0.579,0.731,0.884,0.982,1,0.999,0.991,0.907,0.758,0.603,0.433]};

  /* ------------------------------------------------------------------
     1. Hashing and the PRNG
     ------------------------------------------------------------------ */
  function fnv1a(str) {
    let h = 0x811c9dc5;
    for (let i = 0; i < str.length; i++) {
      h ^= str.charCodeAt(i);
      h = Math.imul(h, 0x01000193);
    }
    return h >>> 0;
  }

  function mulberry32(a) {
    return function () {
      a = a + 0x6D2B79F5 | 0;
      let t = Math.imul(a ^ a >>> 15, 1 | a);
      t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t;
      return ((t ^ t >>> 14) >>> 0) / 4294967296;
    };
  }

  const normalise = s => String(s || '').trim().toLowerCase().replace(/\s+/g, ' ');

  function firstLetter(name) {
    const m = String(name || '').trim().match(/\p{L}|\p{N}/u);
    return m ? m[0].toUpperCase() : '';
  }

  /* ------------------------------------------------------------------
     2. The letter profile — ink density per column
     ------------------------------------------------------------------ */
  const profileCache = new Map();

  function measureProfile(ch, bands) {
    const key = ch + '|' + bands;
    if (profileCache.has(key)) return profileCache.get(key);
    if (BAKED_PROFILES && BAKED_PROFILES[ch]) {
      const p = resample(BAKED_PROFILES[ch], bands);
      profileCache.set(key, p);
      return p;
    }

    let out;
    try {
      out = rasterise(ch, bands);
    } catch (err) {
      out = null;
    }
    if (!out) out = flat(bands);
    profileCache.set(key, out);
    return out;
  }

  function rasterise(ch, bands) {
    const S = 96;
    const cv = document.createElement('canvas');
    cv.width = cv.height = S;
    const cx = cv.getContext('2d', { willReadFrequently: true });
    if (!cx) return null;

    cx.fillStyle = '#fff';
    cx.fillRect(0, 0, S, S);
    cx.fillStyle = '#000';
    cx.textAlign = 'center';
    cx.textBaseline = 'middle';

    // fit the glyph to the box so every letter is measured at the same scale
    let size = 64;
    cx.font = FONT.replace('%s', size);
    const m = cx.measureText(ch);
    const gw = m.width || size * 0.6;
    const gh = (m.actualBoundingBoxAscent + m.actualBoundingBoxDescent) || size * 0.72;
    size = Math.floor(size * Math.min((S * 0.94) / gw, (S * 0.94) / gh));
    cx.font = FONT.replace('%s', size);
    cx.fillText(ch, S / 2, S / 2);

    const data = cx.getImageData(0, 0, S, S).data;
    const isInk = (x, y) => data[(y * S + x) * 4] < 128;

    // crop to the glyph's own horizontal extent so narrow letters
    // still fill the whole signal block
    let x0 = S, x1 = -1;
    for (let x = 0; x < S; x++) {
      for (let y = 0; y < S; y++) {
        if (isInk(x, y)) { if (x < x0) x0 = x; if (x > x1) x1 = x; break; }
      }
    }
    if (x1 < x0) return null;                       // no ink (a space, say)

    const span = x1 - x0 + 1;
    const cov = [];
    for (let b = 0; b < bands; b++) {
      const xa = Math.floor(x0 + (span * b) / bands);
      const xb = Math.max(xa + 1, Math.floor(x0 + (span * (b + 1)) / bands));
      let ink = 0;
      for (let x = xa; x < xb; x++) for (let y = 0; y < S; y++) if (isInk(x, y)) ink++;
      cov.push(ink / ((xb - xa) * S));
    }
    const max = Math.max(...cov) || 1;
    return cov.map(v => v / max);
  }

  const flat = bands => Array.from({ length: bands }, (_, i) =>
    0.45 + 0.35 * Math.abs(Math.sin((i + 1) * 1.7)));

  function resample(src, bands) {
    if (src.length === bands) return src.slice();
    const out = [];
    for (let i = 0; i < bands; i++) {
      const t = (i / (bands - 1 || 1)) * (src.length - 1);
      const a = Math.floor(t), b = Math.min(src.length - 1, a + 1);
      out.push(src[a] + (src[b] - src[a]) * (t - a));
    }
    const max = Math.max(...out) || 1;
    return out.map(v => v / max);
  }

  /* ------------------------------------------------------------------
     3. Parameters — drawn in a fixed order so the stream is stable
     ------------------------------------------------------------------ */
  function paramsFor(name) {
    const hash = fnv1a(normalise(name));
    const rnd = mulberry32(hash);
    const r = (lo, hi) => lo + rnd() * (hi - lo);

    const p = {
      hash,
      bands:    5 + Math.floor(rnd() * 4),   // 5–8
      gamma:    r(0.75, 1.30),               // contrast of the profile
      circleR:  r(104, 130),
      circleCx: r(312, 352),
      circleCy: r(18, 62),
      quarterR: r(100, 144),
      ringGap:  r(26, 42),
      ringOp:   r(0.20, 0.34),
      dotOn:    rnd() < 0.62,
      dotSpot:  Math.floor(rnd() * 3),
      dotR:     r(14, 22),
      monoOp:   r(0.11, 0.17)
    };
    p.jitter = Array.from({ length: p.bands }, () => r(-0.14, 0.14));
    p.peak   = Array.from({ length: p.bands }, () => r(8, 20));
    return p;
  }

  const DOT_SPOTS = [[52, 52], [64, 206], [348, 208]];
  const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));

  /* Amplitudes: the letter's profile, shaped by gamma and nudged per band. */
  function amplitudes(profile, p) {
    return profile.map((v, i) => {
      const shaped = Math.pow(clamp(v, 0, 1), p.gamma) * (1 + p.jitter[i]);
      return clamp(MIN_H + (MAX_H - MIN_H) * shaped, MIN_H, MAX_H);
    });
  }

  function bandGeometry(p) {
    const bw = (BLOCK - (p.bands - 1) * GAP) / p.bands;
    const x0 = CX - BLOCK / 2;
    return { bw, x: i => x0 + i * (bw + GAP) };
  }

  /* ------------------------------------------------------------------
     4. Renderers — one signal, three motifs
     ------------------------------------------------------------------ */
  const n = v => Math.round(v * 10) / 10;

  function motifMusic(amps, p) {
    const { bw, x } = bandGeometry(p);
    const bars = amps.map((h, i) =>
      `<rect x="${n(x(i))}" y="${n(CY - h / 2)}" width="${n(bw)}" height="${n(h)}" rx="${n(bw / 2)}"/>`
    ).join('');
    // peak-hold caps, the way a level meter holds the last maximum
    const caps = amps.map((h, i) =>
      `<rect x="${n(x(i))}" y="${n(CY - h / 2 - p.peak[i] - 6)}" width="${n(bw)}" height="6" rx="3"/>`
    ).join('');
    return `<g fill="var(--art-ink)">${bars}</g>` +
           `<g fill="var(--art-2)" opacity=".5">${caps}</g>`;
  }

  function motifArt(amps, p) {
    const { bw, x } = bandGeometry(p);
    const pts = amps.map((h, i) => [x(i) + bw / 2, CY - (h - MIN_H) / 2 + 18]);
    let d = `M${n(pts[0][0])} ${n(pts[0][1])}`;
    for (let i = 1; i < pts.length; i++) {
      const [px, py] = pts[i - 1], [qx, qy] = pts[i];
      const mx = (px + qx) / 2;
      d += `C${n(mx)} ${n(py)} ${n(mx)} ${n(qy)} ${n(qx)} ${n(qy)}`;
    }
    const dots = pts.filter((_, i) => i % 2 === 0)
      .map(([px, py]) => `<circle cx="${n(px)}" cy="${n(py)}" r="7"/>`).join('');
    return `<path d="${d}" fill="none" stroke="var(--art-ink)" stroke-width="18" ` +
           `stroke-linecap="round" stroke-linejoin="round"/>` +
           `<g fill="var(--art-2)" opacity=".55">${dots}</g>`;
  }

  function motifFilm(amps, p) {
    const { bw, x } = bandGeometry(p);
    const sx = x(0) - 12, sw = BLOCK + 24;
    const frames = amps.map((h, i) => {
      const fh = clamp(h * 0.46, 18, 58);
      return `<rect x="${n(x(i))}" y="${n(CY - fh / 2)}" width="${n(bw)}" height="${n(fh)}" rx="5"/>`;
    }).join('');
    const holes = amps.map((_, i) =>
      `<rect x="${n(x(i))}" y="${n(CY - 46)}" width="${n(bw)}" height="10" rx="3"/>` +
      `<rect x="${n(x(i))}" y="${n(CY + 36)}" width="${n(bw)}" height="10" rx="3"/>`
    ).join('');
    return `<rect x="${n(sx)}" y="${n(CY - 60)}" width="${n(sw)}" height="120" rx="16" fill="var(--art-ink)"/>` +
           `<g fill="var(--art-1)">${holes}${frames}</g>`;
  }

  const MOTIFS = { music: motifMusic, art: motifArt, film: motifFilm };

  /* ------------------------------------------------------------------
     5. Compose
     ------------------------------------------------------------------ */
  function artFor(name, opts) {
    const o = Object.assign({ category: 'music', monogram: true, title: '' }, opts);
    const p = paramsFor(name);
    const letter = firstLetter(name);
    const profile = letter ? measureProfile(letter, p.bands) : flat(p.bands);
    const amps = amplitudes(profile, p);

    const dot = p.dotOn
      ? `<circle cx="${DOT_SPOTS[p.dotSpot][0]}" cy="${DOT_SPOTS[p.dotSpot][1]}" r="${n(p.dotR)}" fill="var(--art-2)" opacity=".45"/>`
      : '';

    // The letter itself, held far back. Convert to outlines before shipping
    // so it never depends on Inter being installed.
    const mono = (o.monogram && letter)
      ? `<text x="${CX}" y="${CY}" text-anchor="middle" dominant-baseline="central"
              font-family="Inter, 'Segoe UI', system-ui, sans-serif" font-weight="700"
              font-size="196" fill="var(--art-2)" opacity="${n(p.monoOp)}">${escapeXml(letter)}</text>`
      : '';

    const render = MOTIFS[o.category] || motifMusic;

    const svg =
`<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMid slice" role="img" xmlns="http://www.w3.org/2000/svg"
     aria-label="${escapeXml(o.title || name)} artwork">
  <rect width="${W}" height="${H}" fill="var(--art-bg)"/>
  <circle cx="${n(p.circleCx)}" cy="${n(p.circleCy)}" r="${n(p.circleR)}" fill="var(--art-1)"/>
  <path d="M0 ${H}V${n(H - p.quarterR)}a${n(p.quarterR)} ${n(p.quarterR)} 0 0 1 ${n(p.quarterR)} ${n(p.quarterR)}z" fill="var(--art-3)"/>
  <circle cx="${n(p.circleCx)}" cy="${n(p.circleCy)}" r="${n(p.circleR + p.ringGap)}" fill="none"
          stroke="var(--art-2)" stroke-width="6" opacity="${n(p.ringOp)}"/>
  ${dot}
  ${mono}
  ${render(amps, p)}
</svg>`;

    return {
      svg,
      meta: {
        name, letter,
        hash: p.hash,
        hashHex: p.hash.toString(16).padStart(8, '0'),
        bands: p.bands,
        gamma: Math.round(p.gamma * 100) / 100,
        profile: profile.map(v => Math.round(v * 100) / 100),
        amplitudes: amps.map(v => Math.round(v))
      }
    };
  }

  function escapeXml(s) {
    return String(s).replace(/[<>&"']/g, c =>
      ({ '<': '&lt;', '>': '&gt;', '&': '&amp;', '"': '&quot;', "'": '&apos;' }[c]));
  }

  /* Wait for the webfont, or glyphs get measured in a fallback face. */
  function ready() {
    if (!document.fonts || !document.fonts.load) return Promise.resolve();
    return document.fonts.load('700 64px Inter').catch(() => {}).then(() => document.fonts.ready);
  }

  /* Measure A–Z and 0–9 at high resolution so the table can be baked in. */
  function bakeProfiles(bands) {
    const b = bands || 12;
    const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'.split('');
    const out = {};
    chars.forEach(c => { out[c] = (rasterise(c, b) || flat(b)).map(v => Math.round(v * 1000) / 1000); });
    return out;
  }

  return { artFor, paramsFor, measureProfile, fnv1a, ready, bakeProfiles, firstLetter };
})();

if (typeof module !== 'undefined' && module.exports) module.exports = __root.FlannerArt;
