#!/usr/bin/env python3
"""Generate the Material 3 colour scheme from one source colour.

M3 builds every colour in a product from a source: five tonal palettes are
derived from it (primary, secondary, tertiary, neutral, neutral-variant, plus a
fixed error palette), each holding thirteen tones, and the 26 colour roles are
then read off those palettes at fixed tones. See DESIGN.md §1.

Material's own generator works in HCT — CAM16 hue and chroma over CIE L* tone.
Implementing CAM16 here would be a lot of code for a difference nobody can see
at these chroma levels, so this uses CIE LCh (D65) with the same idea: tone is
L*, hue is held, and chroma is pushed as high as the sRGB gamut allows at that
lightness. The result differs from Material's generator by a degree or two of
hue in the deepest tones and matches it everywhere it matters.

Run it directly to print the scheme and its contrast audit:

    python3 scripts/m3color.py
"""
from __future__ import annotations

import math

TONES = [0, 4, 6, 10, 12, 17, 20, 22, 24, 25, 30, 40, 49, 50, 60, 70, 80, 85, 87, 90, 92, 94,
         95, 96, 98, 99, 100]

# ── sRGB ↔ CIELAB ──────────────────────────────────────
def _srgb_to_linear(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _linear_to_srgb(c: float) -> float:
    return 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055


WHITE = (0.95047, 1.0, 1.08883)


def hex_to_lab(h: str) -> tuple[float, float, float]:
    h = h.lstrip("#")
    r, g, b = (_srgb_to_linear(int(h[i:i + 2], 16) / 255) for i in (0, 2, 4))
    x = (0.4124564 * r + 0.3575761 * g + 0.1804375 * b) / WHITE[0]
    y = (0.2126729 * r + 0.7151522 * g + 0.0721750 * b) / WHITE[1]
    z = (0.0193339 * r + 0.1191920 * g + 0.9503041 * b) / WHITE[2]
    f = lambda t: t ** (1 / 3) if t > 216 / 24389 else (24389 / 27 * t + 16) / 116
    fx, fy, fz = f(x), f(y), f(z)
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


def lab_to_rgb(L: float, a: float, b: float) -> tuple[float, float, float]:
    fy = (L + 16) / 116
    fx, fz = fy + a / 500, fy - b / 200
    g = lambda t: t ** 3 if t ** 3 > 216 / 24389 else (116 * t - 16) / (24389 / 27)
    x, y, z = g(fx) * WHITE[0], g(fy) * WHITE[1], g(fz) * WHITE[2]
    r = 3.2404542 * x - 1.5371385 * y - 0.4985314 * z
    gg = -0.9692660 * x + 1.8760108 * y + 0.0415560 * z
    bb = 0.0556434 * x - 0.2040259 * y + 1.0572252 * z
    return _linear_to_srgb(r), _linear_to_srgb(gg), _linear_to_srgb(bb)


def _in_gamut(rgb) -> bool:
    return all(-1e-4 <= c <= 1 + 1e-4 for c in rgb)


def tone(hue_deg: float, chroma: float, t: float) -> str:
    """One tone of a palette: lightness t, that hue, as much chroma as fits."""
    h = math.radians(hue_deg)
    lo, hi = 0.0, chroma
    # Binary search the largest in-gamut chroma at this lightness.
    for _ in range(24):
        mid = (lo + hi) / 2
        if _in_gamut(lab_to_rgb(t, mid * math.cos(h), mid * math.sin(h))):
            lo = mid
        else:
            hi = mid
    r, g, b = lab_to_rgb(t, lo * math.cos(h), lo * math.sin(h))
    clamp = lambda c: max(0, min(255, round(c * 255)))
    return f"#{clamp(r):02x}{clamp(g):02x}{clamp(b):02x}"


def palette(hue: float, chroma: float) -> dict[int, str]:
    return {t: tone(hue, chroma, t) for t in TONES}


def palettes(source: str, mono: bool = False) -> dict[str, dict[int, str]]:
    """The six palettes M3 derives from a source colour.

    `mono` selects Material's own MONOCHROME scheme variant, which sets every
    palette's chroma to zero — `TonalPalette.fromHueAndChroma(hue, 0.0)` for
    primary, secondary, tertiary, neutral and neutral-variant alike, in
    material-color-utilities' DynamicScheme. The hue survives in the source
    but has nothing left to tint, so the five palettes collapse onto one grey
    ramp and the scheme is black, white and grey by construction rather than
    by a stylesheet talking every role out of its colour one at a time.

    The error palette is not part of that switch, in Material's code or here:
    it is a semantic colour, and the colour system's own note is that
    "specific colors, such as semantic colors, can be set to not dynamically
    change".
    """
    L, a, b = hex_to_lab(source)
    hue = math.degrees(math.atan2(b, a)) % 360
    chroma = math.hypot(a, b)
    if mono:
        grey = palette(hue, 0)
        return {k: grey for k in
                ("primary", "secondary", "tertiary", "neutral", "neutral_variant")} | {
            "error": palette(25, 84)}
    return {
        "primary": palette(hue, chroma),
        # Material's rules: secondary is a third of the chroma, tertiary sits
        # 60° away at half, and the neutrals keep only a trace of the hue.
        "secondary": palette(hue, chroma / 3),
        "tertiary": palette(hue + 60, chroma / 2),
        # Material tints the neutrals with a trace of the source hue, and so
        # do these. They were held at zero for a while — the paper stays paper
        # — but the planners are drawn on the tinted neutrals the card system
        # uses, and a grey page beside a warm one reads as two products rather
        # than one. At chroma 4 and 8 the trace is barely nameable on its own
        # and lands the surfaces and outlines on the planner's own values.
        "neutral": palette(hue, 4),
        "neutral_variant": palette(hue, 8),
        "error": palette(25, 84),
    }


# The light-theme tone for the four `on-*-container` roles is 30, not the 10
# it was when this table was written. Material changed it in August 2024 —
# "More colorful text and icons. The following color roles are updated in light
# theme to be more colorful while still having accessible color contrast: On
# primary container, On secondary container, On tertiary container, On error
# container" — and material-color-utilities' color_spec_2021 returns
# `s.isDark ? 90 : 30` for all four. (material-web's v0.192 SCSS still says 10;
# it predates the change and is not the authority.) Tone 30 keeps 4.5:1 against
# a tone-90 container, which the audit below proves rather than assumes.
#
# role -> (palette, light tone, dark tone)
ROLES = [
    ("primary", "primary", 40, 80),
    ("on-primary", "primary", 100, 20),
    ("primary-container", "primary", 90, 30),
    ("on-primary-container", "primary", 30, 90),
    ("secondary", "secondary", 40, 80),
    ("on-secondary", "secondary", 100, 20),
    ("secondary-container", "secondary", 90, 30),
    ("on-secondary-container", "secondary", 30, 90),
    ("tertiary", "tertiary", 40, 80),
    ("on-tertiary", "tertiary", 100, 20),
    ("tertiary-container", "tertiary", 90, 30),
    ("on-tertiary-container", "tertiary", 30, 90),
    ("error", "error", 40, 80),
    ("on-error", "error", 100, 20),
    ("error-container", "error", 90, 30),
    ("on-error-container", "error", 30, 90),
    # The page itself is paper, not the 98 tone: white, with the dot grid and
    # the containers above it doing the separating.
    ("surface", "neutral", 100, 6),
    ("on-surface", "neutral", 10, 90),
    ("surface-variant", "neutral_variant", 90, 30),
    ("on-surface-variant", "neutral_variant", 30, 80),
    ("surface-container-lowest", "neutral", 100, 4),
    ("surface-container-low", "neutral", 96, 10),
    ("surface-container", "neutral", 94, 12),
    ("surface-container-high", "neutral", 92, 17),
    ("surface-container-highest", "neutral", 90, 22),
    # The two the contrast rule is written against. Material checks every accent
    # and outline role not against `surface` but against `highestSurface` —
    # surface-dim in light, surface-bright in dark — because that is the
    # lightest paper the role can actually land on, and therefore the worst
    # case. Checking against `surface` flatters the result.
    ("surface-dim", "neutral", 87, 6),
    ("surface-bright", "neutral", 98, 24),
    ("inverse-surface", "neutral", 20, 90),
    ("inverse-on-surface", "neutral", 95, 20),
    ("inverse-primary", "primary", 80, 40),
    ("outline", "neutral_variant", 50, 60),
    ("outline-variant", "neutral_variant", 80, 30),
    ("scrim", "neutral", 0, 0),
    ("shadow", "neutral", 0, 0),
]

# Monochrome moves more than the chroma. With every palette on one grey ramp,
# the accent roles would land on the same tones as the surfaces they sit on —
# a primary at tone 40 is a mid grey on a white page, which reads as disabled
# rather than as the page's strongest colour. So Material re-tones the accents
# for this variant, and these are its numbers, read off the isMonochrome()
# branches in material-color-utilities' color_spec_2021: primary goes to the
# ends of the ramp (black on paper, white in the dark), its container comes in
# to 25/85, and the three accent families separate by tone where they can no
# longer separate by hue. Roles with no branch of their own — secondary, the
# surfaces, the outlines, the whole error family — keep the tones above.
#
# role -> (light tone, dark tone)
MONO_ROLES = {
    "primary": (0, 100),
    "on-primary": (90, 10),
    "primary-container": (25, 85),
    "on-primary-container": (100, 0),
    "on-secondary": (100, 10),
    "secondary-container": (85, 30),
    "on-secondary-container": (10, 90),
    "tertiary": (25, 90),
    "on-tertiary": (90, 10),
    "tertiary-container": (49, 60),
    "on-tertiary-container": (100, 0),
    "on-error-container": (10, 90),
}

# Pairs that must clear a contrast bar: (foreground, background, minimum).
# 3:1 is what Material guarantees for role pairs; text gets 4.5:1.
PAIRS = [
    ("on-primary", "primary", 4.5),
    ("on-primary-container", "primary-container", 4.5),
    ("on-secondary", "secondary", 4.5),
    ("on-secondary-container", "secondary-container", 4.5),
    ("on-tertiary", "tertiary", 4.5),
    ("on-tertiary-container", "tertiary-container", 4.5),
    ("on-error", "error", 4.5),
    ("on-error-container", "error-container", 4.5),
    ("on-surface", "surface", 4.5),
    ("on-surface-variant", "surface", 4.5),
    ("on-surface-variant", "surface-variant", 4.5),
    ("on-surface", "surface-container", 4.5),
    ("on-surface", "surface-container-high", 4.5),
    ("on-surface", "surface-container-highest", 4.5),
    # Against the worst-case surface, per highestSurface(), not the nominal one.
    ("outline", "surface-dim", 3.0),
    ("primary", "surface-dim", 3.0),
    ("secondary", "surface-dim", 3.0),
    ("tertiary", "surface-dim", 3.0),
    ("on-surface", "surface-bright", 4.5),
    ("on-surface-variant", "surface-bright", 4.5),
    ("inverse-on-surface", "inverse-surface", 4.5),
]


def luminance(h: str) -> float:
    h = h.lstrip("#")
    r, g, b = (_srgb_to_linear(int(h[i:i + 2], 16) / 255) for i in (0, 2, 4))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: str, b: str) -> float:
    la, lb = luminance(a), luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def scheme(source: str, mono: bool = False) -> tuple[dict[str, str], dict[str, str]]:
    p = palettes(source, mono)
    roles = [(role, pal) + (MONO_ROLES.get(role, (lt, dk)) if mono else (lt, dk))
             for role, pal, lt, dk in ROLES]
    light = {role: p[pal][lt] for role, pal, lt, _ in roles}
    dark = {role: p[pal][dk] for role, pal, _, dk in roles}
    return light, dark


def audit(light: dict[str, str], dark: dict[str, str]) -> list[str]:
    bad = []
    for name, sch in (("light", light), ("dark", dark)):
        for fg, bg, need in PAIRS:
            r = contrast(sch[fg], sch[bg])
            if r < need:
                bad.append(f"{name}: {fg} on {bg} = {r:.2f}:1, needs {need}")
    return bad


def css(source: str, mono: bool = False) -> str:
    light, dark = scheme(source, mono)
    out = [f"/* Generated by scripts/m3color.py from {source}"
           f"{', monochrome variant' if mono else ''} — do not edit. */",
           ":root{"]
    out += [f"  --md-sys-color-{k}:{v};" for k, v in light.items()]
    out += ["}", ":root[data-theme=dark]{"]
    out += [f"  --md-sys-color-{k}:{v};" for k, v in dark.items()]
    out += ["}"]
    return "\n".join(out)


# The card system's own green — the one every festival card, every chip and
# both planners are drawn in. Sourcing the scheme from it puts the chrome in
# the same family as the content it frames: primary lands on #4c662b, the
# secondary container within a hair of the cards' #DCE8C0, and the outlines on
# the planners' own #C7CBBA.
SOURCE = "#4C662B"

if __name__ == "__main__":
    import sys
    mono = "--mono" in sys.argv
    light, dark = scheme(SOURCE, mono)
    print(f"source {SOURCE}{' — monochrome' if mono else ''}\n")
    for role in light:
        print(f"  {role:28} {light[role]}   {dark[role]}")
    problems = audit(light, dark)
    print("\ncontrast audit:", "all pairs pass" if not problems else "")
    for p in problems:
        print("  ✗", p)
