#!/usr/bin/env python3
"""Build the Flow Festival 2026 planner from the same template as the KBP one.

Same engine, different festival: three days instead of one, Flow's own palette,
and artist links/portraits taken from Flow's own artist pages rather than
guessed from third-party APIs.
"""
import base64, json, pathlib, urllib.parse
from build import ROOT, data_uri, pack_lanes, GENRE_LABELS, TYPE_LABELS

D = ROOT / "data" / "flow"
OUT = ROOT / "flow" / "index.html"

# Flow's bright style: warm grey paper, pure black ink, one electric accent.
THEME = """
:root{
  --kbp-green:#fff203; --kbp-sky:#bcbcbc; --kbp-red:#ff4a1c; --kbp-sand:#d9d9d9;
  --bg:#0b0b0b; --bg2:#151515; --panel:#1b1b1b; --panel2:#242424;
  --line:#2a2a2a; --line2:#3d3d3d;
  --tx:#f4f4f4; --tx2:#a8a8a8; --tx3:#8a8a8a;
  --accent-ink:#fff203; --on-accent:#111000; --shade:rgba(0,0,0,.55);
  --sheet:#151515; --sheet2:#1e1e1e;
  --chip-line:var(--line2);
  --glass:rgba(20,20,20,.72); --glass-line:rgba(255,255,255,.08);
  --glass-pill:rgba(255,255,255,.11); --glass-tx:rgba(255,255,255,.58); --glass-on:#fff;
}
:root[data-theme=light]{
  --bg:#e6e6e6; --bg2:#fff; --panel:#f2f2f2; --panel2:#eaeaea;
  --line:rgba(0,0,0,.14); --line2:rgba(0,0,0,.82);
  --tx:#000; --tx2:#3a3a3a; --tx3:#5c5c5c;
  --accent-ink:#6f6800; --on-accent:#000; --shade:rgba(0,0,0,.16);
  --sheet:#fff; --sheet2:#ededed;
  --chip-line:rgba(0,0,0,.26);
  --glass:rgba(255,255,255,.8); --glass-line:rgba(0,0,0,.16);
  --glass-pill:rgba(0,0,0,.09); --glass-tx:rgba(20,20,20,.6); --glass-on:#000;
}
.logo img{width:clamp(150px,24vw,260px)}
h1{font-size:clamp(26px,6.2vw,50px)}
"""

def build():
    acts = json.loads((D / "acts.json").read_text())
    basemap = json.loads((D / "basemap.json").read_text())
    images = json.loads((D / "images.json").read_text())

    genres_seen, types_seen = set(), set()
    stages = []
    for st in acts["stages"]:
        lanes = {}
        for d in acts["days"]:
            todays = [a for a in st["acts"] if a["day"] == d["id"]]
            lanes[d["id"]] = pack_lanes(todays, lambda a: a["sm"], lambda a: a["em"]) if todays else 1
        out = []
        for a in st["acts"]:
            genres_seen.update(a["genres"]); types_seen.add(a["type"])
            direct = dict(a.get("links") or {})
            if a["slug"]:
                direct["homepage"] = "https://www.flowfestival.com/en/program/music/" + a["slug"]
            q = urllib.parse.quote(a["n"])
            out.append({
                "name": a["n"], "q": a["n"], "day": a["day"],
                "s": a["s"], "e": a["e"], "sm": a["sm"], "em": a["em"], "lane": a["lane"],
                "type": a["type"], "genres": a["genres"],
                "b2b": "b2b" in a["n"].lower(), "allday": False,
                "nomusic": a["type"] == "performance",
                "note": a.get("note", ""),
                "direct": direct,
                "search": {} if a["type"] == "performance" else {
                    "spotify": f"https://open.spotify.com/search/{q}",
                    "soundcloud": f"https://soundcloud.com/search?q={q}",
                    "youtube": f"https://www.youtube.com/results?search_query={q}",
                },
            })
        stages.append({**{k: st[k] for k in ("id", "num", "name", "short", "location", "blurb", "color")},
                       "lat": st["lat"], "lon": st["lon"], "lanes": lanes,
                       "acts": sorted(out, key=lambda x: x["sm"])})

    payload = {
        "event": acts["event"], "stages": stages, "poi": acts.get("poi", []),
        "days": acts["days"],
        "genreLabels": {g: GENRE_LABELS.get(g, g.replace("-", " ").title())
                        for g in sorted(genres_seen)},
        "typeLabels": {t: TYPE_LABELS.get(t, t.title()) for t in sorted(types_seen)},
        "presets": {"live": "main", "second": "front"},
        "hasPoster": False, "basemap": basemap,
    }
    art = {a["n"]: {"src": data_uri(ROOT / "assets" / "flow-art" / images[a["slug"]]),
                    "source": "flow"}
           for st in acts["stages"] for a in st["acts"] if a["slug"] in images}

    html = (ROOT / "scripts" / "template.html").read_text()
    blank = "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"
    for tok, val in [
        ("__DATA__", json.dumps(payload, ensure_ascii=False, separators=(",", ":"))),
        ("__ART__", json.dumps(art, ensure_ascii=False, separators=(",", ":"))),
        ("__BASEMAP__", data_uri(ROOT / "assets" / "flow-basemap.jpg")),
        ("__BASEMAP_LIGHT__", data_uri(ROOT / "assets" / "flow-basemap-light.jpg")),
        ("__SATELLITE__", data_uri(ROOT / "assets" / "flow-satellite.jpg")),
        ("__POSTER__", blank),
        ("__LOGO__", data_uri(ROOT / "assets" / "flow-logo.svg")),
        ("__TEXTURE__", data_uri(ROOT / "assets" / "flow-texture.jpg")),
        ("__FONT_TITLE__", data_uri(ROOT / "assets" / "font" / "title-latin.woff2")),
        ("__FONT_LATIN__", data_uri(ROOT / "assets" / "font" / "disp-latin.woff2")),
        ("__FONT_EXT__", data_uri(ROOT / "assets" / "font" / "disp-latin-ext.woff2")),
        ("__MAP_AR__", f'{basemap["wPixels"]}/{basemap["hPixels"]}'),
        ("__THEME__", THEME),
        ("__SIBLING__", '<p>Also here: the '
                        '<a href="../">Kallio Block Party 2026 planner</a>, same engine.</p>'),
    ]:
        html = html.replace(tok, val)

    # festival-specific copy
    html = html.replace("Kallio Block Party 2026 — Stage Planner", "Flow Festival 2026 — Stage Planner")
    html = html.replace("Kallio&nbsp;Block&nbsp;Party Planner", "Flow Festival Planner")
    html = html.replace('alt="Kallio Block Party 2026"', 'alt="Flow Festival 2026"')
    html = html.replace("KBP<span class=\"pl\">&nbsp;planner</span>", "Flow<span class=\"pl\">&nbsp;planner</span>")
    html = html.replace("https://www.kallioblockparty.org/program/", "https://www.flowfestival.com/en/schedule/")
    html = html.replace("https://www.kallioblockparty.org/", "https://www.flowfestival.com/en/")
    html = html.replace("kallioblockparty.org", "flowfestival.com")
    html = html.replace("Official programme", "Official schedule")
    html = html.replace("<b>9</b> stages", "<b>10</b> stages")
    html = html.replace("Sat <b>1 August</b> <i>·</i> 12:00–22:00",
                        "<b>14–16 August</b> <i>·</i> 3 days")
    html = html.replace("Alppila, Helsinki <i>·</i> free entry", "Suvilahti, Helsinki")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(html)
    n = sum(len(s["acts"]) for s in stages)
    print(f"{OUT}\n  {n} sets · {len(stages)} stages · {len(acts['days'])} days · "
          f"{len(art)} portraits · {OUT.stat().st_size//1024} KB")

if __name__ == "__main__":
    build()
