#!/usr/bin/env python3
"""The pictures for the add-to-home-screen instructions.

A screenshot of someone's own phone is the only illustration that helps here —
a drawing of Safari's share sheet is a drawing of something the reader is
looking at, and any difference between the two is the reader's problem. So the
sources are real screenshots, dropped in `assets/home/a2hs-src/`, and this
turns them into something a page can afford to carry:

  * resized to twice the width they are drawn at, which is all a phone can
    show and a third of what a screenshot arrives as;
  * written as WebP, with the original format kept as the fallback for the
    handful of browsers that still want one;
  * metadata stripped, since a screenshot carries the device it was taken on.

Nothing here invents a step. A source that is not there is a step with words
and no picture, which is what the card showed before there were any.
"""
from __future__ import annotations

import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "assets" / "home" / "a2hs-src"
OUT = ROOT / "assets" / "home"

# Drawn at 200 CSS px, so 400 covers a 2x screen and 600 a 3x one. Beyond that
# a screenshot of a phone is being carried at a size no phone can show. The
# sources are portrait, and 200 is what keeps three of them and their words
# inside a card someone can take in — the UI in them is large enough to read
# at that width, being a menu rather than a page of text.
WIDTHS = (400, 600)

# The steps, in order. `src` is the stem of the file to look for in a2hs-src;
# a step with no file is still a step.
STEPS = [
    {"src": "menu",
     "text": "Open Safari's page menu and choose Share.",
     "alt": "Safari's page menu, with Share at the top above Add to Bookmarks"},
    {"src": "share",
     "text": "At the end of the bottom row, press View More.",
     "alt": "The share sheet's bottom row: Copy, Add to Bookmarks, Add to "
            "Reading List, and View More"},
    {"src": "home",
     "text": "Choose Add to Home Screen, then press Add.",
     "alt": "The rest of the list, ending in Add to Home Screen"},
]


def _found(stem: str) -> pathlib.Path | None:
    if not SRC.is_dir():
        return None
    for p in sorted(SRC.iterdir()):
        if p.is_file() and p.stem == stem and not p.name.startswith("."):
            return p
    return None


def build() -> list[dict]:
    """Optimise whatever sources are present and describe every step.

    Returns one entry per step: its words, and — where a screenshot was
    found — the srcset a `<picture>` needs and the shape to reserve for it so
    the card does not jump when the image lands.
    """
    try:
        from PIL import Image
    except ImportError:                       # pragma: no cover - build machine
        Image = None

    out = []
    for step in STEPS:
        here = {"text": step["text"], "alt": step["alt"]}
        src = _found(step["src"])
        if src and Image is not None:
            im = Image.open(src)
            im = im.convert("RGB") if im.mode in ("P", "RGBA", "LA") else im
            w, h = im.size
            webp, png = [], []
            for target in WIDTHS:
                if target > w:                # never upscale a screenshot
                    continue
                small = im.resize((target, round(h * target / w)), Image.LANCZOS)
                stem = f"a2hs-{step['src']}-{target}"
                small.save(OUT / f"{stem}.webp", "WEBP", quality=82, method=6)
                webp.append(f"./assets/home/{stem}.webp {target}w")
                # One fallback, at the smaller size: it exists to be correct
                # rather than to be sharp, and every browser that needs it is
                # on a screen where the difference does not show.
                if target == WIDTHS[0]:
                    small.save(OUT / f"{stem}.jpg", "JPEG", quality=80,
                               optimize=True, progressive=True)
                    png.append(f"./assets/home/{stem}.jpg")
            if webp:
                here["webp"] = ", ".join(webp)
                here["fallback"] = png[0]
                here["w"], here["h"] = w, h
        out.append(here)
    return out


if __name__ == "__main__":
    for i, s in enumerate(build(), 1):
        got = "picture" if s.get("webp") else "words only"
        print(f"{i}. {got:11} {s['text']}")
    if not SRC.is_dir():
        print(f"\nno sources yet — put screenshots in {SRC.relative_to(ROOT)}/ "
              f"named {', '.join(s['src'] + '.png' for s in STEPS)}")
