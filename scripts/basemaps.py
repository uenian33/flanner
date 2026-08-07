#!/usr/bin/env python3
"""Offline basemaps for every festival — street, satellite, and the projection.

A planner's map is a stitched image rather than a tile layer, because it has to
draw in a field with no signal. That means each festival needs three things
built together: a light street image, a satellite image cropped to exactly the
same bounds, and the Web Mercator origin the page converts lat/lon against.

There were three scripts doing this, one per festival, each with its bounding
box and its output paths written into the code — so adding a festival meant
copying a file and editing it in four places. Here the bounding box is the only
thing a festival contributes; everything else is derived from its id.

    python3 scripts/basemaps.py blockfest lostinmusic
    python3 scripts/basemaps.py --all

Attribution is required by both providers and is rendered on the page:
(c) OpenStreetMap contributors (c) CARTO, and Imagery (c) Esri.
"""
from __future__ import annotations

import json
import math
import pathlib
import sys
import time
import urllib.request

from PIL import Image, ImageEnhance

ROOT = pathlib.Path(__file__).resolve().parent.parent
A = ROOT / "assets"

# South, west, north, east — padded so no pin sits on the edge, and no wider
# than that, because every extra degree is tiles downloaded and kilobytes a
# reader carries to a field.
AREAS: dict[str, tuple[float, float, float, float]] = {
    "kallio":      (60.18760, 24.93640, 60.19390, 24.94940),  # Karhupuisto
    "flow":        (60.18420, 24.96620, 60.18950, 24.97620),  # Suvilahti
    "blockfest":   (61.48950, 23.75500, 61.49650, 23.76900),  # Ratinanniemi
    "lostinmusic": (61.49400, 23.75600, 61.50400, 23.78200),  # Tampere centre
    "juhlaviikot": (60.17700, 24.93600, 60.18400, 24.95000),  # Tokoinranta
    "espoocine":   (60.17550, 24.80400, 60.18220, 24.81800),  # Tapiola
    "tamperejazz": (61.49550, 23.77100, 61.50100, 23.78300),  # Tullikamari
}

# The two festivals built before this script existed keep the filenames their
# pages already name; everything after them is `<id>-`.
STEMS = {"kallio": "", "flow": "flow-"}

Z = 17
UA = {"User-Agent": "Flanner/1.0 (personal offline festival map)",
      "Referer": "https://www.openstreetmap.org/"}
SUBS = "abcd"


def lon2x(lon: float, z: int) -> float:
    return (lon + 180.0) / 360.0 * (1 << z)


def lat2y(lat: float, z: int) -> float:
    r = math.radians(lat)
    return (1.0 - math.log(math.tan(r) + 1.0 / math.cos(r)) / math.pi) / 2.0 * (1 << z)


def fetch(url: str, tries: int = 4) -> bytes:
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read()
        except Exception as e:
            if i == tries - 1:
                raise
            print(f"      retry {i+1}: {e}")
            time.sleep(1.5 * (i + 1))
    raise AssertionError("unreachable")


def stitch(bbox, url_fn, out: pathlib.Path, px: int, tone=None, width: int = 1500):
    """Download the tiles covering `bbox`, crop to it exactly, and save."""
    s, w, n, e = bbox
    x0, x1 = int(lon2x(w, Z)), int(lon2x(e, Z))
    y0, y1 = int(lat2y(n, Z)), int(lat2y(s, Z))
    cols, rows = x1 - x0 + 1, y1 - y0 + 1
    canvas = Image.new("RGB", (cols * px, rows * px))
    tmp = A / f"_tile-{out.stem}.img"
    i = 0
    for cx in range(x0, x1 + 1):
        for cy in range(y0, y1 + 1):
            tmp.write_bytes(fetch(url_fn(cx, cy, i)))
            canvas.paste(Image.open(tmp).convert("RGB"), ((cx - x0) * px, (cy - y0) * px))
            i += 1
            time.sleep(0.05)
    tmp.unlink(missing_ok=True)
    # Crop to the requested bounds, so no tile padding is carried around and
    # the origin recorded below is the origin of the pixels that shipped.
    canvas = canvas.crop((
        int(round((lon2x(w, Z) - x0) * px)), int(round((lat2y(n, Z) - y0) * px)),
        int(round((lon2x(e, Z) - x0) * px)), int(round((lat2y(s, Z) - y0) * px))))
    if tone:
        canvas = ImageEnhance.Brightness(canvas).enhance(tone[0])
        canvas = ImageEnhance.Contrast(canvas).enhance(tone[1])
    canvas = canvas.resize((width, round(canvas.height * width / canvas.width)), Image.LANCZOS)
    canvas.save(out, "JPEG", quality=80, optimize=True, progressive=True)
    print(f"    {out.name:34s} {canvas.size[0]}x{canvas.size[1]}  "
          f"{out.stat().st_size // 1024} KB  ({cols * rows} tiles)")
    return canvas.size


def carto(style: str):
    return lambda cx, cy, i: (f"https://{SUBS[i % 4]}.basemaps.cartocdn.com/"
                              f"{style}/{Z}/{cx}/{cy}@2x.png")


def esri(cx: int, cy: int, i: int) -> str:
    return (f"https://server.arcgisonline.com/ArcGIS/rest/services/"
            f"World_Imagery/MapServer/tile/{Z}/{cy}/{cx}")


def build(fid: str) -> None:
    if fid not in AREAS:
        raise SystemExit(f"{fid}: no area in AREAS — add its bounding box first")
    bbox = AREAS[fid]
    s, w, n, e = bbox
    stem = STEMS.get(fid, f"{fid}-")
    print(f"{fid}  {s},{w} .. {n},{e}")

    # The dark cut is Kallio's alone — the planner draws its map light, and the
    # dark image is only still referenced by the pre-split build. Everything
    # new gets the two the page actually loads.
    size = stitch(bbox, carto("light_all"), A / f"{stem}basemap-light.jpg", 512, (0.97, 1.12))
    stitch(bbox, esri, A / f"{stem}satellite.jpg", 256)

    meta = {
        "z": Z, "tile": 256,
        # Logical (256-px-tile) Web Mercator pixel coordinates of the crop's
        # top-left corner. The page converts lat/lon the same way to place pins.
        "originX": lon2x(w, Z) * 256, "originY": lat2y(n, Z) * 256,
        "wLogical": (lon2x(e, Z) - lon2x(w, Z)) * 256,
        "hLogical": (lat2y(s, Z) - lat2y(n, Z)) * 256,
        "wPixels": size[0], "hPixels": size[1],
        "bounds": {"s": s, "w": w, "n": n, "e": e},
        "attribution": "(c) OpenStreetMap contributors (c) CARTO",
    }
    out = ROOT / "data" / fid / "basemap.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(meta, indent=1) + "\n")
    print(f"    data/{fid}/basemap.json")


def main(argv: list[str]) -> None:
    want = list(AREAS) if argv[:1] == ["--all"] else argv
    if not want:
        raise SystemExit(f"usage: basemaps.py <festival>...  |  --all\n"
                         f"  known: {', '.join(AREAS)}")
    for fid in want:
        build(fid)


if __name__ == "__main__":
    main(sys.argv[1:])
