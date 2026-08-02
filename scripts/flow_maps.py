#!/usr/bin/env python3
"""Offline basemaps for the Flow planner: Suvilahti, dark + light + satellite."""
import json, math, pathlib, time, urllib.request
from PIL import Image, ImageEnhance

ROOT = pathlib.Path(__file__).resolve().parent.parent
A = ROOT / "assets"
S, W, N, E = 60.18420, 24.96620, 60.18950, 24.97620      # Suvilahti festival area
Z, PX = 17, 512
UA = {"User-Agent": "FlowFestivalPlanner/1.0 (personal offline festival map)",
      "Referer": "https://www.openstreetmap.org/"}

lon2x = lambda lon, z: (lon + 180) / 360 * (1 << z)
def lat2y(lat, z):
    r = math.radians(lat)
    return (1 - math.log(math.tan(r) + 1/math.cos(r)) / math.pi) / 2 * (1 << z)

def fetch(u, tries=4):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=30) as r:
                return r.read()
        except Exception:
            if i == tries - 1: raise
            time.sleep(1.5 * (i + 1))

def build(url_fn, out, px, tone=None):
    x0, x1 = int(lon2x(W, Z)), int(lon2x(E, Z))
    y0, y1 = int(lat2y(N, Z)), int(lat2y(S, Z))
    cols, rows = x1 - x0 + 1, y1 - y0 + 1
    canvas = Image.new("RGB", (cols * px, rows * px))
    n = 0
    for cx in range(x0, x1 + 1):
        for cy in range(y0, y1 + 1):
            tmp = A / "_f.img"; tmp.write_bytes(fetch(url_fn(cx, cy, n)))
            canvas.paste(Image.open(tmp).convert("RGB"), ((cx-x0)*px, (cy-y0)*px)); tmp.unlink()
            n += 1; time.sleep(0.05)
    canvas = canvas.crop((int(round((lon2x(W,Z)-x0)*px)), int(round((lat2y(N,Z)-y0)*px)),
                          int(round((lon2x(E,Z)-x0)*px)), int(round((lat2y(S,Z)-y0)*px))))
    if tone:
        canvas = ImageEnhance.Brightness(canvas).enhance(tone[0])
        canvas = ImageEnhance.Contrast(canvas).enhance(tone[1])
    wpx = 1500
    canvas = canvas.resize((wpx, round(canvas.height * wpx / canvas.width)), Image.LANCZOS)
    canvas.save(out, "JPEG", quality=80, optimize=True, progressive=True)
    print(f"  {out.name}  {canvas.size}  {out.stat().st_size//1024} KB")
    return canvas.size

subs = "abcd"
carto = lambda style: (lambda cx, cy, n: f"https://{subs[n%4]}.basemaps.cartocdn.com/{style}/{Z}/{cx}/{cy}@2x.png")
esri = lambda cx, cy, n: (f"https://server.arcgisonline.com/ArcGIS/rest/services/"
                          f"World_Imagery/MapServer/tile/{Z}/{cy}/{cx}")

print("Suvilahti basemaps:")
size = build(carto("dark_all"),  A / "flow-basemap.jpg", 512, (1.85, 1.22))
build(carto("light_all"), A / "flow-basemap-light.jpg", 512, (0.97, 1.12))
build(esri, A / "flow-satellite.jpg", 256)

(ROOT / "data" / "flow" / "basemap.json").write_text(json.dumps({
    "z": Z, "tile": 256,
    "originX": lon2x(W, Z) * 256, "originY": lat2y(N, Z) * 256,
    "wLogical": (lon2x(E, Z) - lon2x(W, Z)) * 256,
    "hLogical": (lat2y(S, Z) - lat2y(N, Z)) * 256,
    "wPixels": size[0], "hPixels": size[1],
    "bounds": {"s": S, "w": W, "n": N, "e": E},
}, indent=1))
print("wrote data/flow/basemap.json")
