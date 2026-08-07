#!/usr/bin/env python3
"""Icons, manifest and service worker — the bits that make Flanner installable.

The worker has two jobs, and they want opposite policies.

A page is a document that can be corrected: it is served from cache at once and
refreshed behind the reader, which is the right trade for a planner opened in a
field with two bars of signal. An asset is not — the font, the photographs and
the two basemaps are the same bytes every time, and a build that changes one
changes the cache name along with it. So an asset that is in the cache is
answered from the cache and the network is left alone. That distinction is new:
until the font and the maps moved out of the documents there were no
sub-resources to have a policy about.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw

import schema
import seo

ROOT = Path(__file__).resolve().parent.parent
ICONS = ROOT / "assets" / "icons"

# What the worker precaches on install. Everything else is picked up as it is
# visited, so a first run does not pull the whole site nobody asked for yet.
#
# The two Latin fonts are here because every page on the site is set in one of
# them: fetched once on the first visit, they are the difference between a
# second page that draws immediately and one that draws in a fallback face
# first. The Extended cuts are not — they carry a unicode-range most readers
# never reach.
SHELL = ["./", "./manifest.webmanifest",
         "./assets/icons/icon-192.png", "./assets/icons/icon-512.png",
         "./assets/font/inter-latin.woff2", "./assets/font/robotoflex-latin.woff2"]

# Every page the site publishes. The planners come from the records rather than
# from a list kept here: a festival is a folder someone drops in, and a list
# that had to be edited alongside it would leave the new planner out of the
# cache stamp and out of "save for offline" — which nobody would notice until
# they opened it in a field with no signal.
PLANNERS = [f"./{f['planner']}" for f in schema.load()["festivals"] if f.get("planner")]
PAGES = ["./"] + PLANNERS + ["./about/", "./faq/", "./terms/", "./privacy/"]


PLATE = "#2E4B12"      # the "In your plan" chip green
PETAL = "#B1D18A"
ACCENT = "#EDF6DA"     # the petal you have added, and the centre

# The mark on its 96 grid: one petal is a lobe of radius 10 centred at
# (48, 18) closing to a point at (48, 40), and the other five are that same
# shape turned in 60-degree steps about the centre. Nothing is drawn by hand,
# so the six lobes are identical and the outer edge lands on r 40 all round.
_LOBE_C, _LOBE_R = (48.0, 18.0), 10.0
_WEDGE = [(48.0, 40.0), (39.09, 22.55), (56.91, 22.55)]


def _turn(p, deg):
    """A point rotated about the mark's centre, the way SVG's rotate() does."""
    import math
    a = math.radians(deg)
    x, y = p[0] - 48.0, p[1] - 48.0
    return (48.0 + x * math.cos(a) - y * math.sin(a),
            48.0 + x * math.sin(a) + y * math.cos(a))


def _petal(d: ImageDraw.ImageDraw, deg: float, k: float, fill: str) -> None:
    cx, cy = _turn(_LOBE_C, deg)
    d.ellipse([(cx - _LOBE_R) * k, (cy - _LOBE_R) * k,
               (cx + _LOBE_R) * k, (cy + _LOBE_R) * k], fill=fill)
    d.polygon([(x * k, y * k) for x, y in (_turn(p, deg) for p in _WEDGE)], fill=fill)


def mark(size: int, pad: float = 0.0, plate: bool = True) -> Image.Image:
    """The Flanner mark, on its plate — the app icon at any size."""
    s = size * 4
    k = s / 96.0
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if plate:
        d.rounded_rectangle([0, 0, s - 1, s - 1], radius=24 * k, fill=PLATE)
    for deg in (60, 120, 180, 240, 300):
        _petal(d, deg, k, PETAL)
    _petal(d, 0, k, ACCENT)
    d.ellipse([(48 - 5) * k, (48 - 5) * k, (48 + 5) * k, (48 + 5) * k], fill=ACCENT)
    img = img.resize((size, size), Image.LANCZOS)
    if pad <= 0:
        return img
    # A maskable icon may be cropped to a circle, so the mark is inset and the
    # plate is redrawn full-bleed underneath it.
    canvas = Image.new("RGBA", (size, size), PLATE)
    inner = int(size * (1 - pad * 2))
    small = mark(inner, plate=False)
    canvas.paste(small, ((size - inner) // 2, (size - inner) // 2), small)
    return canvas


def main() -> None:
    ICONS.mkdir(parents=True, exist_ok=True)

    # The mark comes with its own plate, at the corner radius the brand draws.
    for n in (192, 512):
        mark(n).save(ICONS / f"icon-{n}.png", optimize=True)
    # A maskable icon may be cropped to a circle, so it needs a wider safe zone.
    mark(512, pad=0.20).save(ICONS / "icon-maskable-512.png", optimize=True)
    # Apple ignores maskable and does not round transparent corners itself.
    mark(180).save(ICONS / "apple-touch-icon.png", optimize=True)
    print(f"  icons → {len(list(ICONS.glob('*.png')))} files")

    manifest = {
        "id": "/flanner/",
        "name": "Flanner — Finnish festival planner",
        "short_name": "Flanner",
        "description": "Plannable timetables for Finnish festivals. Works offline.",
        "start_url": "./",
        "scope": "./",
        "display": "standalone",
        "orientation": "any",
        "lang": "en",
        "dir": "ltr",
        # The installed app opens on the home page, and the home page's
        # surface is tone 100 on the monochrome scheme — the same value its
        # own theme-color meta carries, so the title bar and the page are one
        # colour rather than a tone apart.
        "background_color": "#ffffff",
        "theme_color": "#ffffff",
        "categories": ["music", "entertainment", "travel"],
        "icons": [
            {"src": "assets/icons/icon-192.png", "sizes": "192x192", "type": "image/png"},
            {"src": "assets/icons/icon-512.png", "sizes": "512x512", "type": "image/png"},
            {"src": "assets/icons/icon-maskable-512.png", "sizes": "512x512",
             "type": "image/png", "purpose": "maskable"},
        ],
        # Long-pressing the installed icon offers a few planners. Android shows
        # four at most, so these are the next four festivals to happen rather
        # than all of them — a shortcut to a festival that is over is a dead
        # entry in a menu with four slots.
        "shortcuts": [
            {"name": f["name"], "url": f["planner"]}
            for f in sorted((x for x in schema.load()["festivals"] if x.get("planner")),
                            key=lambda x: x["start"])[:4]
        ],
    }
    (ROOT / "manifest.webmanifest").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")

    # The cache name carries a hash of every built page and of every file they
    # now point at, so a deploy that changes any of them retires the old cache
    # instead of serving it forever. The assets have to be in the hash because
    # they are answered from the cache without a revalidating request: a
    # basemap that changed under a cache name that did not would be served from
    # the old store until something else forced a new one.
    stamp = hashlib.sha256()
    for page in PAGES:
        f = ROOT / page.lstrip("./") / "index.html" if page != "./" else ROOT / "index.html"
        if f.exists():
            stamp.update(f.read_bytes())
    for base in ("assets", "data"):
        for f in sorted(ROOT.joinpath(base).rglob("*")):
            if f.is_file():
                stamp.update(f.relative_to(ROOT).as_posix().encode())
                stamp.update(hashlib.sha256(f.read_bytes()).digest())
    version = stamp.hexdigest()[:12]

    # What "save for offline" downloads. Written here rather than listed by
    # hand in `_offline.html`, because the shared files are content-hashed and
    # a festival is a folder someone drops in — a hand-kept list would be one
    # planner behind the moment either changed, and the reader would find out
    # in a field.
    pages = PAGES
    assets = sorted(
        "./" + f.relative_to(ROOT).as_posix()
        for base in ("assets/js", "assets/font", "assets/home", "assets/icons")
        for f in ROOT.joinpath(base).glob("*") if f.is_file())
    assets += sorted(
        "./" + f.relative_to(ROOT).as_posix()
        for f in ROOT.joinpath("data").rglob("planner.js"))
    # The basemaps a planner names, read off the planners rather than repeated.
    # They are named in the festival's data now rather than in its page — which
    # is where this used to look, so between the data split and this line every
    # basemap was quietly missing from "save for offline": the one file the
    # feature exists for, gone from the one list that fetches it.
    import re as _re
    maps = set()
    for f in sorted(ROOT.joinpath("data").rglob("planner.js")):
        maps |= {"./" + m for m in _re.findall(r"assets/[\w.-]+\.jpg", f.read_text())}
    offline = {"pages": pages, "assets": assets + sorted(maps)}
    (ROOT / "assets" / "offline.json").write_text(
        json.dumps(offline, indent=1) + "\n")
    print(f"  offline list → {len(pages)} pages · {len(offline['assets'])} files")

    sw = f"""/* Flanner service worker — generated by scripts/build_pwa.py, do not edit. */
const CACHE = 'flanner-{version}';
const SHELL = {json.dumps(SHELL)};

self.addEventListener('install', e => {{
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)).then(() => self.skipWaiting()));
}});

self.addEventListener('activate', e => {{
  e.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys
        .filter(k => k !== CACHE && k !== 'flanner-offline')
        .map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
}});

/* Documents are stale-while-revalidate: a planner opened at a festival should
   paint from cache immediately rather than wait on a flaky connection, and
   pick up any correction on the next visit.

   Assets under assets/ are cache-first. They are content the build replaces
   wholesale rather than edits, and the cache name carries a hash of every
   page, so a deploy that changes one arrives with a new store to put it in.
   Revalidating them would spend a request per font and per basemap on every
   page view to be told each time that nothing had changed. */
self.addEventListener('fetch', e => {{
  const req = e.request;
  if (req.method !== 'GET' || new URL(req.url).origin !== self.location.origin) return;

  const asset = /\\/(assets|data)\\//.test(new URL(req.url).pathname);

  e.respondWith((async () => {{
    const cache = await caches.open(CACHE);
    if (asset) {{
      const have = await cache.match(req, {{ignoreSearch: true}});
      if (have) return have;
      const got = await fetch(req).catch(() => null);
      if (got && got.ok) cache.put(req, got.clone());
      if (got) return got;
      return new Response('', {{status: 504}});
    }}
    /* Read from any Flanner cache, not just this build's. "Save for offline"
       writes from the page, and if it ran before this worker created its own
       store the download would otherwise be invisible here. */
    const hit = await cache.match(req, {{ignoreSearch: true}}) ||
      await (async () => {{
        for (const name of await caches.keys()) {{
          if (name === CACHE || !name.startsWith('flanner-')) continue;
          const m = await (await caches.open(name)).match(req, {{ignoreSearch: true}});
          if (m) return m;
        }}
        return null;
      }})();
    const live = fetch(req).then(res => {{
      if (res && res.ok) cache.put(req, res.clone());
      return res;
    }}).catch(() => null);

    if (hit) {{ e.waitUntil(live); return hit; }}
    const res = await live;
    if (res) return res;
    /* Offline and never seen: fall back to the page we do have. */
    return (await cache.match('./')) ||
      new Response('Offline, and this page has not been opened before.',
        {{status: 503, headers: {{'Content-Type': 'text/plain'}}}});
  }})());
}});
"""
    (ROOT / "sw.js").write_text(sw)
    print(f"  manifest.webmanifest · sw.js (cache flanner-{version})")


if __name__ == "__main__":
    print(ROOT)
    main()
