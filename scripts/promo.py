#!/usr/bin/env python3
"""The photograph on a festival's card, and behind its planner's title.

A festival that publishes a picture of itself should be shown as itself. Where
one has not — or has published only a poster made of type, which fights the
name printed over it — the card and the hero draw the category's own artwork
instead, and that is the right answer rather than a gap.

    python3 scripts/promo.py blockfest https://…/crowd.jpg
    python3 scripts/promo.py blockfest ~/Downloads/blockfest.png
    python3 scripts/promo.py --list

What arrives is whatever a CMS had on the day: a 2048px original, sometimes
4000. What ships is 760 wide, which is twice the 380 a card is drawn at on a
phone and enough for the hero on any of them, at the quality the two
photographs already here were cut to. Metadata goes: a press photograph carries
the camera, the photographer and often a location, none of which belongs in a
file this site serves.

The source URL is written into `data/festivals.json` beside the file, so where
each picture came from is answerable later without going back through a build
log — these are the festivals' own photographs, used to point at the festivals.
"""
from __future__ import annotations

import io
import json
import pathlib
import sys
import urllib.request

from PIL import Image, ImageOps

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "home"

# Twice the width a card draws it at on a phone, which is also plenty for the
# hero: past this a reader is carrying pixels no layout on the site asks for.
WIDTH = 760
# The taller a picture is, the more of a card it takes before its words start.
# Anything deeper than 4:3 is cropped to it from the middle, where the subject
# of a festival photograph almost always is.
MAX_RATIO = 4 / 3
QUALITY = 82

UA = {"User-Agent": "Flanner/1.0 (personal festival planner; contact via the site)"}


def fetch(src: str) -> bytes:
    """A URL, or a file already on the disk.

    Some of these arrive as a link on the festival's own site and some arrive
    as a file, because what a festival publishes as its key visual is not
    always reachable at an address — several of these sites compose theirs out
    of CSS and a logo, and the picture only exists once a browser has drawn it.
    """
    if "://" not in src:
        return pathlib.Path(src).expanduser().read_bytes()
    req = urllib.request.Request(src, headers=UA)
    with urllib.request.urlopen(req, timeout=45) as r:
        return r.read()


def fit(raw: bytes) -> Image.Image:
    im = Image.open(io.BytesIO(raw))
    # A photograph off a phone carries its orientation in EXIF rather than in
    # its pixels; every reader honours that and Pillow does not, so it is
    # applied here before anything is measured.
    # Flattened onto white before anything else: a PNG key visual carries an
    # alpha channel, and a JPEG has none — left to Pillow the transparent parts
    # come out black, which on a cream poster is the whole background.
    im = ImageOps.exif_transpose(im)
    if im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGBA")
        flat = Image.new("RGB", im.size, (255, 255, 255))
        flat.paste(im, mask=im.split()[-1])
        im = flat
    else:
        im = im.convert("RGB")
    w, h = im.size
    if h > w / MAX_RATIO:
        keep = int(round(w / MAX_RATIO))
        top = (h - keep) // 2
        im = im.crop((0, top, w, top + keep))
    if im.width > WIDTH:
        im = im.resize((WIDTH, round(im.height * WIDTH / im.width)), Image.LANCZOS)
    return im


def save(fid: str, im: Image.Image) -> pathlib.Path:
    out = OUT / f"{fid}-promo.jpg"
    # No `exif=` and no `icc_profile=`: a new image, carrying nothing it came
    # with. Progressive, because a card's picture is the first thing on it.
    im.save(out, "JPEG", quality=QUALITY, optimize=True, progressive=True)
    return out


def listing() -> None:
    cfg = json.loads((ROOT / "data" / "festivals.json").read_text())
    for f in cfg["festivals"]:
        mark = "photo" if f.get("promo") else "drawn"
        src = f.get("promoFrom", "")
        print(f"  {f['id']:12s} {mark:5s} {f.get('promo', '') or '—':24s} {src}")


def main(argv: list[str]) -> None:
    if not argv or argv[0] == "--list":
        listing()
        if not argv:
            raise SystemExit("\nusage: promo.py <festival-id> <image-url-or-path>  |  --list")
        return
    if len(argv) != 2:
        raise SystemExit("usage: promo.py <festival-id> <image-url-or-path>")
    fid, url = argv
    cfg = json.loads((ROOT / "data" / "festivals.json").read_text())
    if not any(f["id"] == fid for f in cfg["festivals"]):
        raise SystemExit(f"{fid}: not a festival in data/festivals.json")
    im = fit(fetch(url))
    out = save(fid, im)
    kb = out.stat().st_size // 1024
    print(f"  {out.relative_to(ROOT)}  {im.width}x{im.height}  {kb} KB")
    print(f"  add to its record:  \"promo\": \"{out.name}\", \"cardArt\": \"photo\",")
    print(f"                      \"promoFrom\": \"{url}\"")


if __name__ == "__main__":
    main(sys.argv[1:])
