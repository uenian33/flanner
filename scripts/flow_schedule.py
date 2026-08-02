#!/usr/bin/env python3
"""Scrape the Flow Festival 2026 timetable.

The schedule page is server-rendered, so the whole weekend is in the HTML: one
block per day, then a venue group per stage, then an .event per set.
"""
import html, json, pathlib, re, urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "flow" / "schedule.json"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"}

def get(url):
    return urllib.request.urlopen(
        urllib.request.Request(url, headers=UA), timeout=45).read().decode("utf-8", "replace")

def strip(s):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s)).strip()

src = get("https://www.flowfestival.com/en/schedule/")

# Each id appears twice — once on the day tab, once on the day's content. Keep
# only the spans that actually contain venue groups.
marks = [(m.group(1), m.start()) for m in re.finditer(r'data-day-id="(\d+)"', src)]
marks.append((None, len(src)))
spans = [(did, a, b) for (did, a), (_, b) in zip(marks, marks[1:])
         if 'class="venue-group"' in src[a:b]]

days = []
for did, start, end in spans:
    block = src[start:end]
    label = strip(re.search(r"<h2[^>]*>(.*?)</h2>", block, re.S).group(1)) if re.search(r"<h2", block) else did
    venues = []
    parts = re.split(r'<div class="venue-group"', block)[1:]
    for p in parts:
        vm = re.search(r"<h[34][^>]*>(.*?)</h[34]>", p, re.S)
        venue = strip(vm.group(1)) if vm else "?"
        acts = []
        for ev in re.split(r'<div class="event"', p)[1:]:
            am = re.search(r'class="artist-name"[^>]*>(.*?)</a>', ev, re.S)
            tm = re.search(r'class="time"[^>]*>\s*(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})', ev, re.S)
            sm = re.search(r'data-base-href="([^"]+)"', ev)
            if not (am and tm):
                continue
            acts.append({"n": html.unescape(strip(am.group(1))),
                         "s": tm.group(1), "e": tm.group(2),
                         "slug": sm.group(1).rstrip("/").split("/")[-1] if sm else ""})
        if acts:
            venues.append({"venue": html.unescape(venue), "acts": acts})
    if venues:
        days.append({"id": did, "label": label, "venues": venues})

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(days, ensure_ascii=False, indent=1))
n = sum(len(v["acts"]) for d in days for v in d["venues"])
print(f"{len(days)} days, {sum(len(d['venues']) for d in days)} venue-days, {n} sets -> {OUT}")
for d in days:
    print(f"  {d['label']:12} {len(d['venues'])} venues, {sum(len(v['acts']) for v in d['venues'])} sets")
