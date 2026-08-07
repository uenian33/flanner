#!/usr/bin/env python3
"""Build the offline basemap.

Downloads CARTO 'dark matter' raster tiles (OpenStreetMap data) covering the
festival area, stitches them into one image, and records the exact Web Mercator
pixel origin so the page can place stage pins from real lat/lon.

Attribution (required, rendered on the page): (c) OpenStreetMap contributors, (c) CARTO.
"""

import json
import math
import pathlib
import time
import urllib.request

from PIL import Image, ImageEnhance

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT_IMG = ROOT / "assets" / "basemap.jpg"
OUT_META = ROOT / "data" / "kallio" / "basemap.json"

Z = 17
RETINA = 2
TILE = 256                      # logical tile size
PX = TILE * RETINA              # downloaded tile size
STYLE = "dark_all"

# Festival area, padded so no pin sits on the edge.
S, W, N, E = 60.18760, 24.93640, 60.19390, 24.94940


def lon2x(lon, z):
    return (lon + 180.0) / 360.0 * (1 << z)


def lat2y(lat, z):
    r = math.radians(lat)
    return (1.0 - math.log(math.tan(r) + 1.0 / math.cos(r)) / math.pi) / 2.0 * (1 << z)


def fetch(url, tries=4):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "KallioBlockPartyPlanner/1.0 (personal offline festival map)",
                "Referer": "https://www.openstreetmap.org/",
            })
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read()
        except Exception as e:
            if i == tries - 1:
                raise
            print(f"    retry {i+1}: {e}")
            time.sleep(1.5 * (i + 1))


def main():
    x0, x1 = int(lon2x(W, Z)), int(lon2x(E, Z))
    y0, y1 = int(lat2y(N, Z)), int(lat2y(S, Z))
    cols, rows = x1 - x0 + 1, y1 - y0 + 1
    print(f"z{Z}  x {x0}..{x1}  y {y0}..{y1}  = {cols}x{rows} = {cols*rows} tiles @{PX}px")

    canvas = Image.new("RGB", (cols * PX, rows * PX), (12, 14, 18))
    subs = "abcd"
    n = 0
    for cx in range(x0, x1 + 1):
        for cy in range(y0, y1 + 1):
            s = subs[n % len(subs)]
            url = (f"https://{s}.basemaps.cartocdn.com/{STYLE}/{Z}/{cx}/{cy}"
                   f"{'@2x' if RETINA == 2 else ''}.png")
            print(f"  [{n+1:2}/{cols*rows}] {cx},{cy}")
            raw = fetch(url)
            tmp = ROOT / "assets" / "_t.png"
            tmp.write_bytes(raw)
            canvas.paste(Image.open(tmp).convert("RGB"),
                         ((cx - x0) * PX, (cy - y0) * PX))
            tmp.unlink()
            n += 1
            time.sleep(0.08)

    # Crop to the requested bounds so no tile padding is carried around.
    left = int(round((lon2x(W, Z) - x0) * PX))
    right = int(round((lon2x(E, Z) - x0) * PX))
    top = int(round((lat2y(N, Z) - y0) * PX))
    bottom = int(round((lat2y(S, Z) - y0) * PX))
    canvas = canvas.crop((left, top, right, bottom))

    # dark_all is near-black at this zoom; lift it so street names stay legible
    # against the page while the map still reads as a dark surface.
    canvas = ImageEnhance.Brightness(canvas).enhance(1.85)
    canvas = ImageEnhance.Contrast(canvas).enhance(1.22)
    canvas = ImageEnhance.Color(canvas).enhance(0.85)

    canvas.save(OUT_IMG, "JPEG", quality=84, optimize=True, progressive=True)

    # Logical (256-px-tile) Web Mercator pixel coordinates of the crop's
    # top-left corner. The page converts lat/lon the same way to place pins.
    meta = {
        "z": Z, "tile": TILE,
        "originX": lon2x(W, Z) * TILE,
        "originY": lat2y(N, Z) * TILE,
        "wLogical": (lon2x(E, Z) - lon2x(W, Z)) * TILE,
        "hLogical": (lat2y(S, Z) - lat2y(N, Z)) * TILE,
        "wPixels": canvas.size[0], "hPixels": canvas.size[1],
        "bounds": {"s": S, "w": W, "n": N, "e": E},
        "attribution": "(c) OpenStreetMap contributors (c) CARTO",
    }
    OUT_META.write_text(json.dumps(meta, indent=1))
    kb = OUT_IMG.stat().st_size // 1024
    print(f"\n{OUT_IMG}  {canvas.size[0]}x{canvas.size[1]}  {kb} KB")
    print(f"{OUT_META}")


if __name__ == "__main__":
    main()
