#!/usr/bin/env python3
"""Turn the scraped Flow schedule + artist pages into the planner's data shape.

Stages are constant across the weekend, so each act carries its day. Genres are
derived from Flow's own artist blurbs by keyword, which is a guide rather than
an authority — the blurbs are prose, not tags.
"""
import json, pathlib, re

ROOT = pathlib.Path(__file__).resolve().parent.parent
D = ROOT / "data" / "flow"
sched = json.loads((D / "schedule.json").read_text())
arts = json.loads((D / "artists.json").read_text())

DAY_IDS = {"FRI": ("fri", "Fri 14 Aug", "Fri", "2026-08-14"),
           "SAT": ("sat", "Sat 15 Aug", "Sat", "2026-08-15"),
           "SUN": ("sun", "Sun 16 Aug", "Sun", "2026-08-16")}

# Flow's own stage character, from the festival's descriptions of each area.
COORD = {
 "main":(60.18618,24.97258), "silver":(60.18692,24.97052), "black":(60.18658,24.96982),
 "balloon":(60.18701,24.97181), "other":(60.18722,24.97298), "front":(60.18652,24.97148),
 "backyard":(60.18602,24.97079), "xgarden":(60.18580,24.97352), "lanson":(60.18669,24.97401),
 "tiivis":(60.18700,24.97302),   # confirmed: OSM arts_centre "Tiivistämö"
}
STAGES = {
 "Main Stage":            ("main",   1, "#fff203", "The big one, by the gasholders. Headliners and the largest crowds."),
 "Silver Arena":          ("silver", 2, "#9aa7b8", "Covered arena stage — the second-biggest bookings of the weekend."),
 "Black Tent":            ("black",  3, "#c084fc", "Tented stage for rising names, rap and left-field pop."),
 "Balloon 360°":          ("balloon",4, "#fb7185", "In the round, under the balloon. Jazz, folk and world music."),
 "The Other Sound":       ("other",  5, "#2dd4bf", "Experimental, contemporary classical and sound art."),
 "Front Yard":            ("front",  6, "#22d3ee", "The main dance floor: house, techno, bass, long DJ sets."),
 "Heineken Backyard":     ("backyard",7,"#4ade80", "Back-yard dance stage, mostly two-hour DJ sets."),
 "X Garden":              ("xgarden",8, "#fc8c46", "Club-leaning garden stage, local and international DJs."),
 "Lanson Champagne Bar & Lounge": ("lanson", 9, "#e8c07a", "Bar and lounge with DJs from open to close."),
 "Tiivistämö":            ("tiivis", 10, "#94a3b8", "Indoor venue for talks and non-music programme."),
}

GENRE_WORDS = [
 ("techno", ["techno"]), ("house", ["house", "disco house"]), ("disco", ["disco"]),
 ("dnb", ["drum and bass", "drum & bass", "jungle", "dnb"]),
 ("bass", ["dubstep", "bass music", "garage", "uk garage", "grime"]),
 ("electronic", ["electronic", "synth", "producer", "club", "dance music", "rave"]),
 ("ambient", ["ambient", "drone", "meditative"]),
 ("experimental", ["experimental", "avant-garde", "sound art", "noise"]),
 ("classical", ["classical", "orchestra", "chamber", "contemporary music"]),
 ("jazz", ["jazz", "saxophon", "improvis"]),
 ("rap", ["rap", "hip hop", "hip-hop", "mc "]),
 ("rnb-soul", ["r&b", "soul", "neo-soul", "funk"]),
 ("rock", ["rock", "guitar band", "riff"]), ("punk", ["punk", "hardcore"]),
 ("metal", ["metal"]), ("indie", ["indie", "alternative", "lo-fi", "shoegaze"]),
 ("pop", ["pop"]), ("folk", ["folk", "kansanmusiikki", "traditional"]),
 ("reggae", ["reggae", "dub", "roots"]),
 ("afro", ["afro", "african", "amapiano", "highlife"]),
 ("latin", ["latin", "brazil", "cumbia", "reggaeton", "salsa"]),
 ("world", ["world music", "global"]),
]
STAGE_FALLBACK = {"front": ["electronic","house"], "backyard": ["electronic","house"],
                  "xgarden": ["electronic","club"], "lanson": ["electronic","eclectic"],
                  "other": ["experimental"], "balloon": ["jazz","world"],
                  "main": ["pop"], "silver": ["pop"], "black": ["indie"], "tiivis": ["talk"]}

def mins(t):
    h, m = t.split(":"); return int(h) * 60 + int(m)

def classify(name, blurb, sid):
    text = (name + " " + (blurb or "")).lower()
    g = []
    for label, words in GENRE_WORDS:
        if any(w in text for w in words) and label not in g:
            g.append(label)
    if not g:
        g = list(STAGE_FALLBACK.get(sid, ["electronic"]))
    return g[:3]

def act_type(name, blurb, sid):
    n = name.lower()
    if sid == "tiivis" or "workshop" in n or "family sunday" in n or "talks" in n:
        return "performance"
    if "(dj set)" in n or n.startswith("dj ") or " dj " in n or "b2b" in n:
        return "dj"
    b = (blurb or "").lower()
    if re.search(r"\bdj\b", n) or ("dj" in b and "band" not in b and "live" not in n.lower()):
        return "dj"
    if any(w in n for w in ["band", "quartet", "orchestra", "trio", "ensemble", "(live)", "live band"]):
        return "band"
    if "producer" in b and "dj" in b:
        return "dj"
    return "live"

days_out, stages = [], {}
for d in sched:
    key = d["label"].split()[0].upper()
    did, dlabel, dshort, date = DAY_IDS[key]
    starts, ends = [], []
    for v in d["venues"]:
        vname = v["venue"]
        sid, num, colour, blurb = STAGES[vname]
        st = stages.setdefault(sid, {"id": sid, "num": num, "name": vname,
                                     "lat": COORD[sid][0], "lon": COORD[sid][1],
                                     "short": vname.replace(" Champagne Bar & Lounge", ""),
                                     "location": "", "blurb": blurb,
                                     "color": colour, "acts": []})
        for a in v["acts"]:
            s, e = mins(a["s"]), mins(a["e"])
            # Anything before 06:00 belongs to the previous festival day: a set
            # billed on Friday that starts at 00:00 runs into Saturday morning.
            if s < 360: s += 1440
            if e < 360: e += 1440
            if e <= s: e += 1440
            info = arts.get(a["slug"], {})
            st["acts"].append({
                "n": a["n"], "day": did, "s": a["s"], "e": a["e"], "sm": s, "em": e,
                "slug": a["slug"], "type": act_type(a["n"], info.get("blurb"), sid),
                "genres": classify(a["n"], info.get("blurb"), sid),
                "note": info.get("blurb", ""),
                "links": {k: v2 for k, v2 in info.items() if k in
                          ("spotify", "youtube", "instagram", "soundcloud")},
                "img": info.get("img", ""),
            })
            starts.append(s); ends.append(e)
    days_out.append({"id": did, "label": dlabel, "short": dshort, "date": date,
                     "start": (min(starts) // 60) * 60, "end": -(-max(ends) // 60) * 60})

out = {"event": {"name": "Flow Festival 2026", "city": "Suvilahti, Helsinki",
                 "site": "https://www.flowfestival.com/en/"},
       "days": days_out,
       "stages": [stages[s] for s in sorted(stages, key=lambda k: stages[k]["num"])]}
(D / "acts.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))

n = sum(len(s["acts"]) for s in out["stages"])
print(f"{len(out['days'])} days, {len(out['stages'])} stages, {n} sets")
for d in out["days"]:
    print(f"  {d['label']}  {d['start']//60:02d}:00 – {d['end']//60:02d}:00 "
          f"({sum(1 for s in out['stages'] for a in s['acts'] if a['day']==d['id'])} sets)")
from collections import Counter
print("types:", Counter(a["type"] for s in out["stages"] for a in s["acts"]).most_common())
print("genres:", Counter(g for s in out["stages"] for a in s["acts"] for g in a["genres"]).most_common(12))
