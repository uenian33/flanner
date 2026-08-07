#!/usr/bin/env python3
"""Offline satellite basemap, cropped to exactly the same bounds as basemap.jpg.

Esri World Imagery tiles. Attribution is required and is rendered on the page.
"""
import json, math, pathlib, time, urllib.request
from PIL import Image

ROOT = pathlib.Path(__file__).resolve().parent.parent
META = json.loads((ROOT / "data" / "kallio" / "basemap.json").read_text())
B = META["bounds"]
Z, PX = META["z"], 256
OUT = ROOT / "assets" / "satellite.jpg"

lon2x = lambda lon, z: (lon + 180.0) / 360.0 * (1 << z)
def lat2y(lat, z):
    r = math.radians(lat)
    return (1.0 - math.log(math.tan(r) + 1/math.cos(r)) / math.pi) / 2.0 * (1 << z)

def fetch(url, tries=4):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "KallioBlockPartyPlanner/1.0"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read()
        except Exception as e:
            if i == tries - 1: raise
            time.sleep(1.5 * (i + 1))

x0, x1 = int(lon2x(B["w"], Z)), int(lon2x(B["e"], Z))
y0, y1 = int(lat2y(B["n"], Z)), int(lat2y(B["s"], Z))
cols, rows = x1 - x0 + 1, y1 - y0 + 1
canvas = Image.new("RGB", (cols * PX, rows * PX))
n = 0
for cx in range(x0, x1 + 1):
    for cy in range(y0, y1 + 1):
        raw = fetch(f"https://server.arcgisonline.com/ArcGIS/rest/services/"
                    f"World_Imagery/MapServer/tile/{Z}/{cy}/{cx}")
        tmp = ROOT / "assets" / "_s.jpg"; tmp.write_bytes(raw)
        canvas.paste(Image.open(tmp).convert("RGB"), ((cx-x0)*PX, (cy-y0)*PX))
        tmp.unlink(); n += 1
        print(f"  [{n}/{cols*rows}]")
        time.sleep(0.05)

canvas = canvas.crop((
    int(round((lon2x(B["w"], Z) - x0) * PX)), int(round((lat2y(B["n"], Z) - y0) * PX)),
    int(round((lon2x(B["e"], Z) - x0) * PX)), int(round((lat2y(B["s"], Z) - y0) * PX))))
W = 1400
canvas = canvas.resize((W, round(canvas.height * W / canvas.width)), Image.LANCZOS)
canvas.save(OUT, "JPEG", quality=76, optimize=True, progressive=True)
print(f"{OUT} {canvas.size} {OUT.stat().st_size//1024} KB")
