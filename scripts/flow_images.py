#!/usr/bin/env python3
"""Download and square-crop the Flow artist portraits."""
import io, json, pathlib, sys, time, urllib.request
from PIL import Image

ROOT = pathlib.Path(__file__).resolve().parent.parent
D = ROOT / "data" / "flow"
ART = ROOT / "assets" / "flow-art"
ART.mkdir(parents=True, exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"}
SIZE = 300

arts = json.loads((D / "artists.json").read_text())
out = {}
for i, (slug, rec) in enumerate(arts.items(), 1):
    url = rec.get("img")
    if not url:
        continue
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
            im = Image.open(io.BytesIO(r.read())).convert("RGB")
    except Exception as e:
        print(f"  skip {slug}: {e}", file=sys.stderr); continue
    w, h = im.size
    side = min(w, h)
    im = im.crop(((w - side)//2, 0, (w - side)//2 + side, side))   # portraits: crop to the top
    im = im.resize((SIZE, SIZE), Image.LANCZOS)
    im.save(ART / f"{slug}.jpg", "JPEG", quality=76, optimize=True, progressive=True)
    out[slug] = f"{slug}.jpg"
    print(f"[{i:3}/{len(arts)}] {slug}", file=sys.stderr)
    time.sleep(0.05)

(D / "images.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
tot = sum(f.stat().st_size for f in ART.glob("*.jpg"))
print(f"\n{len(out)} portraits, {tot//1024} KB total", file=sys.stderr)
