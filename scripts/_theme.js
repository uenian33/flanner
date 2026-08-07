/* ── the scheme, in the browser ─────────────────────────
   The planners are one design drawn in one green, and each festival turns that
   green to its own. Until now the turning happened in Python: `theme_css` read
   every tone the design had chosen and re-emitted it at the festival's hue, and
   the answer was baked into that festival's page. That works, and it costs a
   page per festival.

   This is the same arithmetic, in JavaScript, so a planner can be handed an
   accent and theme itself. `scripts/m3color.py` is the reference implementation
   and this is checked against it token for token — see `tools/theme_parity.py`,
   which fails the build if the two ever disagree.

   Only the hue moves. Every token keeps the lightness and the chroma the design
   gave it, so every contrast pair the design was drawn against still holds: the
   page changes colour without changing tone. That is what makes this safe to do
   at runtime for a festival nobody has audited by hand. */
(() => {
  'use strict';

  const WHITE = [0.95047, 1.0, 1.08883];
  const E = 216 / 24389, K = 24389 / 27;

  const toLinear = (c) => (c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4));
  /* Negative and above-one values keep the linear branch, which is what stops
     a fractional power of a negative appearing here at all — the same reason
     the Python has no special case for it. */
  const toSrgb = (c) => (c <= 0.0031308 ? 12.92 * c : 1.055 * Math.pow(c, 1 / 2.4) - 0.055);

  function hexToLab(hex) {
    const h = hex.replace('#', '');
    const r = toLinear(parseInt(h.slice(0, 2), 16) / 255);
    const g = toLinear(parseInt(h.slice(2, 4), 16) / 255);
    const b = toLinear(parseInt(h.slice(4, 6), 16) / 255);
    const x = (0.4124564 * r + 0.3575761 * g + 0.1804375 * b) / WHITE[0];
    const y = (0.2126729 * r + 0.7151522 * g + 0.0721750 * b) / WHITE[1];
    const z = (0.0193339 * r + 0.1191920 * g + 0.9503041 * b) / WHITE[2];
    const f = (t) => (t > E ? Math.cbrt(t) : (K * t + 16) / 116);
    const fx = f(x), fy = f(y), fz = f(z);
    return [116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)];
  }

  function labToRgb(L, a, b) {
    const fy = (L + 16) / 116, fx = fy + a / 500, fz = fy - b / 200;
    const g = (t) => (t * t * t > E ? t * t * t : (116 * t - 16) / K);
    const x = g(fx) * WHITE[0], y = g(fy) * WHITE[1], z = g(fz) * WHITE[2];
    return [
      toSrgb(3.2404542 * x - 1.5371385 * y - 0.4985314 * z),
      toSrgb(-0.9692660 * x + 1.8760108 * y + 0.0415560 * z),
      toSrgb(0.0556434 * x - 0.2040259 * y + 1.0572252 * z),
    ];
  }

  const inGamut = (rgb) => rgb.every((c) => c >= -1e-4 && c <= 1 + 1e-4);

  /* Python rounds half to even and JavaScript rounds half up, which is one
     value in 255 and therefore a different hex on the boundary. The reference
     is Python's, so this is Python's. */
  function roundHalfEven(x) {
    const f = Math.floor(x), d = x - f;
    if (d > 0.5) return f + 1;
    if (d < 0.5) return f;
    return f % 2 === 0 ? f : f + 1;
  }

  const hex2 = (c) => {
    const v = Math.max(0, Math.min(255, roundHalfEven(c * 255)));
    return v.toString(16).padStart(2, '0');
  };

  /* One tone of a palette: this lightness, this hue, and as much of the chroma
     asked for as the sRGB gamut will take — found by bisection, twenty-four
     times, which is the same number of steps the Python takes so the two land
     on the same value rather than merely near it. */
  function tone(hueDeg, chroma, t) {
    const h = (hueDeg * Math.PI) / 180, cos = Math.cos(h), sin = Math.sin(h);
    let lo = 0, hi = chroma;
    for (let i = 0; i < 24; i++) {
      const mid = (lo + hi) / 2;
      if (inGamut(labToRgb(t, mid * cos, mid * sin))) lo = mid; else hi = mid;
    }
    const rgb = labToRgb(t, lo * cos, lo * sin);
    return '#' + hex2(rgb[0]) + hex2(rgb[1]) + hex2(rgb[2]);
  }

  /* A recipe entry is what the build worked out once and no page needs to work
     out again: the lightness and chroma the design chose, and the alpha where
     the value was an rgba(). Applying a hue to it is the whole of theming. */
  function fromRecipe(e, hue) {
    if (e.v !== undefined) return e.v;          // left as the design had it
    const t = tone(hue, e.c, e.l);
    if (e.a === undefined) return t;
    const r = parseInt(t.slice(1, 3), 16), g = parseInt(t.slice(3, 5), 16), b = parseInt(t.slice(5, 7), 16);
    return 'rgba(' + r + ',' + g + ',' + b + ',' + e.a + ')';
  }

  const decls = (list, hue) =>
    list.map((e) => e.n + ':' + fromRecipe(e, hue)).join(';');

  /* The stages, spaced by the golden angle from the festival's own hue: ten
     stages in equal steps are 36 degrees apart, which at these tones is one
     green beside another. */
  function stageDecls(roles, n, hue, dark) {
    const out = [];
    for (let i = 0; i < n; i++) {
      const h = (hue + i * 137.507) % 360;
      for (const r of roles) {
        const pair = dark || r.always ? r.d : r.l;
        out.push('--st' + i + '-' + r.k.toLowerCase() + ':' + tone(h, pair[0], pair[1]));
      }
    }
    return out.join(';');
  }

  /* The whole scheme for one accent, as the two blocks the page already
     expects — so what this writes is what the build used to write. */
  function schemeCss(recipe, accent, stages) {
    const lab = hexToLab(accent);
    const hue = ((Math.atan2(lab[2], lab[1]) * 180) / Math.PI + 360) % 360;
    return [
      ':root:not([data-theme="dark"]){' + decls(recipe.light, hue) + '}',
      '[data-theme="dark"]{' + decls(recipe.dark, hue) + '}',
      '.fest{--hero-tint:' + tone(hue, recipe.tint.c, recipe.tint.l) +
        ';--hero-duo:' + tone(hue, recipe.duo.c, recipe.duo.l) + '}',
      ':root{' + stageDecls(recipe.stages, stages, hue, false) + '}',
      '[data-theme="dark"]{' + stageDecls(recipe.stages, stages, hue, true) + '}',
    ].join('\n');
  }

  window.FlannerTheme = { tone, hexToLab, labToRgb, schemeCss, stageDecls, fromRecipe };
})();
