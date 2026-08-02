#!/usr/bin/env python3
"""Fetch each Flow artist page for its links, portrait and blurb.

Flow publishes a real Spotify artist URL, a YouTube channel and a portrait on
every act's page — so unlike the KBP planner, nothing here has to be guessed.
"""
import html, json, pathlib, re, sys, time, urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCHED = ROOT / "data" / "flow" / "schedule.json"
OUT = ROOT / "data" / "flow" / "artists.json"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"}

def get(url, tries=3):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=35) as r:
                return r.read().decode("utf-8", "replace")
        except Exception:
            if i == tries - 1:
                return None
            time.sleep(1.5 * (i + 1))

def strip(s):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s)).strip()

days = json.loads(SCHED.read_text())
slugs = []
for d in days:
    for v in d["venues"]:
        for a in v["acts"]:
            if a["slug"] and a["slug"] not in slugs:
                slugs.append(a["slug"])

out = {}
for i, slug in enumerate(slugs, 1):
    src = get(f"https://www.flowfestival.com/en/program/music/{slug}/")
    print(f"[{i:3}/{len(slugs)}] {slug}", file=sys.stderr)
    if not src:
        continue
    rec = {}
    m = re.search(r'href="(https://open\.spotify\.com/artist/[^"?]+)', src)
    if m: rec["spotify"] = m.group(1)
    m = re.search(r'href="(https://(?:www\.)?youtube\.com/@[^"?]+)', src)
    if m: rec["youtube"] = m.group(1)
    m = re.search(r'href="(https://(?:www\.)?instagram\.com/[^"?/]+)', src)
    if m and "flowfestivalhelsinki" not in m.group(1): rec["instagram"] = m.group(1)
    m = re.search(r'href="(https://[^"]*soundcloud\.com/[^"?]+)', src)
    if m: rec["soundcloud"] = m.group(1)
    # portrait: the uploads image sized for the artist page
    imgs = re.findall(r'https://www\.flowfestival\.com/uploads/[^"\s]+?\.(?:jpg|jpeg|png)', src)
    port = [u for u in imgs if "portrait" in u.lower()] or imgs
    if port: rec["img"] = max(port, key=len)
    # blurb: the longest paragraph on the page
    paras = [strip(p) for p in re.findall(r"<p[^>]*>(.*?)</p>", src, re.S)]
    paras = [p for p in paras if len(p) > 80 and "cookie" not in p.lower()]
    if paras: rec["blurb"] = html.unescape(max(paras, key=len))[:600]
    if rec: out[slug] = rec
    time.sleep(0.12)

OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1))
have = lambda k: sum(1 for v in out.values() if k in v)
print(f"\n{len(out)}/{len(slugs)} artists: spotify={have('spotify')} youtube={have('youtube')} "
      f"img={have('img')} blurb={have('blurb')}", file=sys.stderr)
