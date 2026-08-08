#!/usr/bin/env python3
"""HCT — the colour space Material 3 actually measures colour in.

Hue and Chroma come from CAM16, a colour appearance model that knows what the
eye is adapted to; Tone is CIE L*, the same lightness the rest of this project
already uses. Material's own generator works here rather than in Lab because
Lab's hue lines bend: two colours Lab calls the same hue can look like
different hues, and clustering an image in Lab therefore merges colours a
reader would call distinct. That matters for `palette.py`, which clusters the
pixels of a festival's poster and has to come back with the colours somebody
would name.

This is a port of the forward half of material-color-utilities (Google,
Apache-2.0): `hct/viewing_conditions.ts` and `hct/cam16.ts`. Forward only —
sRGB in, HCT out. Going the other way needs their gamut solver, and nothing
here asks for it: `m3color.py` builds tones in CIE LCh, and what this module
feeds it is a source colour that came out of an image and is already sRGB.

    python3 scripts/hct.py '#4C662B'
"""
from __future__ import annotations

import math

# ── sRGB, XYZ and L* ───────────────────────────────────
# Material works on a 0–100 scale rather than 0–1, and the constants below are
# theirs; keeping the scale keeps every intermediate comparable with the
# reference implementation when checking a value by hand.
_E = 216 / 24389
_KAPPA = 24389 / 27
WHITE_POINT_D65 = (95.047, 100.0, 108.883)


def linearized(byte: int) -> float:
    """One sRGB byte to linear light, 0–100."""
    n = byte / 255.0
    return (n / 12.92) * 100.0 if n <= 0.040449936 else \
        ((n + 0.055) / 1.055) ** 2.4 * 100.0


def _lab_f(t: float) -> float:
    return t ** (1 / 3) if t > _E else (_KAPPA * t + 16) / 116


def y_from_lstar(lstar: float) -> float:
    ft = (lstar + 16.0) / 116.0
    ft3 = ft * ft * ft
    return 100.0 * (ft3 if ft3 > _E else (116 * ft - 16) / _KAPPA)


def lstar_from_y(y: float) -> float:
    return _lab_f(y / 100.0) * 116.0 - 16.0


# ── viewing conditions ─────────────────────────────────
class ViewingConditions:
    """What the eye is adapted to. The defaults are Material's: a display in a
    room at about 200 lux, against a mid-grey surround, with the eye not
    discounting the illuminant — which is the right assumption for something
    self-luminous like a screen."""

    def __init__(self, n, aw, nbb, ncb, c, nc, rgb_d, fl, fl_root, z):
        self.n, self.aw, self.nbb, self.ncb = n, aw, nbb, ncb
        self.c, self.nc, self.rgb_d = c, nc, rgb_d
        self.fl, self.fl_root, self.z = fl, fl_root, z

    @staticmethod
    def make(white_point=WHITE_POINT_D65, adapting_luminance=-1.0,
             background_lstar=50.0, surround=2.0,
             discounting_illuminant=False) -> "ViewingConditions":
        if adapting_luminance < 0:
            adapting_luminance = (200.0 / math.pi) * y_from_lstar(50.0) / 100.0
        x, y, z_ = white_point
        r_w = x * 0.401288 + y * 0.650173 + z_ * -0.051461
        g_w = x * -0.250268 + y * 1.204414 + z_ * 0.045854
        b_w = x * -0.002079 + y * 0.048952 + z_ * 0.953127
        f = 0.8 + surround / 10.0
        lerp = lambda a, b, t: a + (b - a) * t
        c = lerp(0.59, 0.69, (f - 0.9) * 10.0) if f >= 0.9 \
            else lerp(0.525, 0.59, (f - 0.8) * 10.0)
        d = 1.0 if discounting_illuminant else \
            f * (1.0 - (1.0 / 3.6) * math.exp((-adapting_luminance - 42.0) / 92.0))
        d = min(1.0, max(0.0, d))
        rgb_d = [d * (100.0 / r_w) + 1.0 - d,
                 d * (100.0 / g_w) + 1.0 - d,
                 d * (100.0 / b_w) + 1.0 - d]
        k = 1.0 / (5.0 * adapting_luminance + 1.0)
        k4 = k ** 4
        k4f = 1.0 - k4
        fl = k4 * adapting_luminance + \
            0.1 * k4f * k4f * (5.0 * adapting_luminance) ** (1 / 3)
        n = y_from_lstar(background_lstar) / white_point[1]
        z = 1.48 + math.sqrt(n)
        nbb = 0.725 / n ** 0.2
        factors = [((fl * rgb_d[i] * w) / 100.0) ** 0.42
                   for i, w in enumerate((r_w, g_w, b_w))]
        rgb_a = [(400.0 * fa) / (fa + 27.13) for fa in factors]
        aw = (2.0 * rgb_a[0] + rgb_a[1] + 0.05 * rgb_a[2]) * nbb
        return ViewingConditions(n, aw, nbb, nbb, c, f, rgb_d, fl,
                                 fl ** 0.25, z)


DEFAULT = ViewingConditions.make()


# ── CAM16, forward ─────────────────────────────────────
def cam16(rgb: tuple[int, int, int], vc: ViewingConditions = DEFAULT
          ) -> tuple[float, float, float]:
    """(hue in degrees, chroma, J lightness) for one sRGB triple."""
    r_l, g_l, b_l = (linearized(v) for v in rgb)
    x = 0.41233895 * r_l + 0.35762064 * g_l + 0.18051042 * b_l
    y = 0.2126 * r_l + 0.7152 * g_l + 0.0722 * b_l
    z = 0.01932141 * r_l + 0.11916382 * g_l + 0.95034478 * b_l

    r_c = 0.401288 * x + 0.650173 * y - 0.051461 * z
    g_c = -0.250268 * x + 1.204414 * y + 0.045854 * z
    b_c = -0.002079 * x + 0.048952 * y + 0.953127 * z

    sign = lambda v: (v > 0) - (v < 0)
    adapt = []
    for chan, d in zip((r_c, g_c, b_c), vc.rgb_d):
        v = d * chan
        af = ((vc.fl * abs(v)) / 100.0) ** 0.42
        adapt.append((sign(v) * 400.0 * af) / (af + 27.13))
    r_a, g_a, b_a = adapt

    a = (11.0 * r_a + -12.0 * g_a + b_a) / 11.0
    b = (r_a + g_a - 2.0 * b_a) / 9.0
    u = (20.0 * r_a + 20.0 * g_a + 21.0 * b_a) / 20.0
    p2 = (40.0 * r_a + 20.0 * g_a + b_a) / 20.0

    hue = math.degrees(math.atan2(b, a)) % 360.0
    j = 100.0 * (p2 * vc.nbb / vc.aw) ** (vc.c * vc.z)
    # The eccentricity of the hue, which is what stops chroma from being a
    # plain distance: the eye does not find every direction equally colourful.
    hue_prime = hue + 360.0 if hue < 20.14 else hue
    e_hue = 0.25 * (math.cos(math.radians(hue_prime) + 2.0) + 3.8)
    p1 = (50000.0 / 13.0) * e_hue * vc.nc * vc.ncb
    t = (p1 * math.hypot(a, b)) / (u + 0.305)
    alpha = t ** 0.9 * (1.64 - 0.29 ** vc.n) ** 0.73
    chroma = alpha * math.sqrt(j / 100.0)
    return hue, chroma, j


def from_rgb(rgb: tuple[int, int, int]) -> tuple[float, float, float]:
    """(hue, chroma, tone) — HCT. Tone is L*, not CAM16's J."""
    hue, chroma, _ = cam16(rgb)
    r_l, g_l, b_l = (linearized(v) for v in rgb)
    y = 0.2126 * r_l + 0.7152 * g_l + 0.0722 * b_l
    return hue, chroma, lstar_from_y(y)


def from_hex(h: str) -> tuple[float, float, float]:
    h = h.lstrip("#")
    return from_rgb(tuple(int(h[i:i + 2], 16) for i in (0, 2, 4)))


def from_argb(argb: int) -> tuple[float, float, float]:
    return from_rgb(((argb >> 16) & 0xff, (argb >> 8) & 0xff, argb & 0xff))


def to_hex(rgb: tuple[int, int, int]) -> str:
    return "#%02x%02x%02x" % rgb


def difference_degrees(a: float, b: float) -> float:
    """The shorter way round the hue circle."""
    return 180.0 - abs(abs(a - b) - 180.0)


if __name__ == "__main__":
    import sys
    for arg in sys.argv[1:] or ["#4C662B", "#ff0000", "#ffffff", "#000000"]:
        h, c, t = from_hex(arg)
        print(f"{arg:>9}  hue {h:6.1f}  chroma {c:6.1f}  tone {t:5.1f}")
