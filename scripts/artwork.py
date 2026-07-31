#!/usr/bin/env python3
"""Fetch a representative image for each act.

Two keyless sources, in order of trust:
  1. Deezer artist picture  - only for names that match exactly.
  2. iTunes Search album art - only when the returned artistName matches exactly.

Anything unmatched gets no image; the page draws a deterministic generative
cover from the act's name instead of showing a wrong face.
"""

import hashlib
import io
import json
import pathlib
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request

from PIL import Image

ROOT = pathlib.Path(__file__).resolve().parent.parent
ACTS = ROOT / "data" / "acts.json"
CURATED = ROOT / "scripts" / "curated.json"
ART_DIR = ROOT / "assets" / "art"
OUT = ROOT / "data" / "artwork.json"

UA = "KallioBlockPartyPlanner/1.0 (personal festival schedule)"
SIZE = 320

# Names common enough that an exact string match still means nothing.
BLOCKED = {
    "turbo", "ray", "aquarius", "dreamer", "void", "prinssi", "are", "wibe",
    "lionize", "rakata", "clamo", "mayela", "zeze", "1961", "hash", "seka",
    "tens", "drdecks", "temporados", "milk", "yebo", "wolve", "nosleep",
    "sensorydeprivation", "rumbus", "chalalo", "aquarius", "matinaro",
    "digitalmindz", "thefvce", "artlius", "jeku",
}


def norm(s):
    s = unicodedata.normalize("NFKD", s.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"\b(dj|live|host)\b", " ", s)
    return re.sub(r"[^a-z0-9]+", "", s)


def get(url):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.read()
    except Exception:
        return None


def getjson(url):
    raw = get(url)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


def try_deezer(name):
    d = getjson("https://api.deezer.com/search/artist?q=" +
                urllib.parse.quote(name) + "&limit=5")
    if not d or not d.get("data"):
        return None
    t = norm(name)
    for a in d["data"]:
        if norm(a["name"]) == t and a.get("picture_xl"):
            # Deezer serves a generic silhouette when it has no real photo.
            if a.get("nb_fan", 0) < 1 and a.get("nb_album", 0) < 1:
                continue
            return a["picture_xl"], "deezer", a["link"]
    return None


def try_itunes(name):
    d = getjson("https://itunes.apple.com/search?media=music&entity=album&limit=8&term=" +
                urllib.parse.quote(name))
    if not d or not d.get("results"):
        return None
    t = norm(name)
    for r in d["results"]:
        if norm(r.get("artistName", "")) == t and r.get("artworkUrl100"):
            return (r["artworkUrl100"].replace("100x100", "600x600"),
                    "itunes", r.get("artistViewUrl", ""))
    return None


def save(raw, slug):
    try:
        im = Image.open(io.BytesIO(raw)).convert("RGB")
    except Exception:
        return None
    w, h = im.size
    if min(w, h) < 120:
        return None
    # centre-crop to square, then downscale
    side = min(w, h)
    im = im.crop(((w - side) // 2, (h - side) // 2,
                  (w - side) // 2 + side, (h - side) // 2 + side))
    im = im.resize((SIZE, SIZE), Image.LANCZOS)
    # A flat grey rectangle is Deezer's placeholder; skip those.
    if len(im.convert("L").getcolors(maxcolors=100000) or []) < 40:
        return None
    p = ART_DIR / f"{slug}.jpg"
    im.save(p, "JPEG", quality=80, optimize=True, progressive=True)
    return p.name


def main():
    ART_DIR.mkdir(parents=True, exist_ok=True)
    data = json.loads(ACTS.read_text())
    curated = json.loads(CURATED.read_text())
    out = {}
    names = []
    for st in data["stages"]:
        for a in st["acts"]:
            if not a.get("nomusic"):
                names.append(a["n"])

    for i, name in enumerate(names, 1):
        slug = hashlib.md5(name.encode()).hexdigest()[:10]
        n = norm(name)
        print(f"[{i:3}/{len(names)}] {name}", file=sys.stderr)
        if n in BLOCKED:
            print("            blocked (too generic)", file=sys.stderr)
            continue
        hit = try_deezer(name) or try_itunes(name)
        time.sleep(0.15)
        if not hit:
            continue
        url, src, prof = hit
        raw = get(url)
        if not raw:
            continue
        fn = save(raw, slug)
        if fn:
            out[name] = {"file": fn, "source": src, "profile": prof}
            print(f"            {src} -> {fn}", file=sys.stderr)

    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print(f"\n{len(out)}/{len(names)} acts have artwork -> {OUT}", file=sys.stderr)


if __name__ == "__main__":
    main()
