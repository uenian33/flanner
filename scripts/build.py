#!/usr/bin/env python3
"""Build the self-contained Kallio Block Party 2026 stage planner.

Inputs
  data/acts.json        timetable, genre classification, stage coordinates
  data/basemap.json     Web Mercator origin of the stitched basemap
  data/artwork.json     verified artist images
  scripts/curated.json  hand-verified artist links
  scripts/template.html markup, styles and behaviour

Output
  index.html            one file, no network needed: font, basemap, official
                        map and every artwork are inlined as data URIs.
"""

import base64
import json
import sys
from pathlib import Path as _P
sys.path.insert(0, str(_P(__file__).resolve().parent))
import schema
import seo
import mimetypes
import pathlib
import urllib.parse

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = ROOT / "kallio" / "index.html"

DAY_START, DAY_END = 12 * 60, 22 * 60
LANE_H = 74

STAGE_COLORS = {
    "alive": "#f59e0b", "woj": "#c084fc", "happyhour": "#f472b6", "ptnky": "#22d3ee",
    "dnb": "#4ade80", "katto": "#60a5fa", "rap": "#fb7185", "power": "#a3e635",
    "soundgarden": "#2dd4bf", "activities": "#94a3b8",
}

GENRE_LABELS = {
    "house": "House", "techno": "Techno", "hard": "Hard dance", "dnb": "Drum & bass",
    "jungle": "Jungle", "rap": "Rap", "indie": "Indie", "rock": "Rock", "pop": "Pop",
    "alternative": "Alternative", "afro": "Afro", "latin": "Latin",
    "global-club": "Global club", "disco": "Disco", "electronic": "Electronic",
    "experimental": "Experimental", "rnb-soul": "R&B / Soul", "eclectic": "Eclectic",
    "garage": "Garage", "family": "Family", "workshop": "Workshop", "theatre": "Theatre",
}

TYPE_LABELS = {
    "band": "Band", "singer": "Singer / solo", "dj": "DJ", "rap": "Rap / MC",
    "live-electronic": "Live electronic", "performance": "Performance", "host": "Host",
}


def mins(t):
    h, m = t.split(":")
    return int(h) * 60 + int(m)


def data_uri(path):
    mime = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
    if path.suffix == ".woff2":
        mime = "font/woff2"
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode()}"


def pack_lanes(acts, key_s=lambda a: mins(a["s"]), key_e=lambda a: mins(a["e"])):
    """Greedy interval packing: each act takes the lowest lane that is free."""
    ends = []
    for a in sorted(acts, key=lambda x: (key_s(x), -(key_e(x) - key_s(x)))):
        for i, end in enumerate(ends):
            if key_s(a) >= end:
                a["lane"] = i
                ends[i] = key_e(a)
                break
        else:
            a["lane"] = len(ends)
            ends.append(key_e(a))
    return len(ends)


def search_links(name, cur):
    e = urllib.parse.quote(cur.get("sq", name))
    return {
        "spotify": f"https://open.spotify.com/search/{e}",
        "soundcloud": f"https://soundcloud.com/search?q={e}",
        "youtube": f"https://www.youtube.com/results?search_query={e}",
    }


def main():
    acts = json.loads((DATA / "acts.json").read_text())
    curated = json.loads((ROOT / "scripts" / "curated.json").read_text())
    basemap = json.loads((DATA / "basemap.json").read_text())
    artwork = json.loads((DATA / "artwork.json").read_text())

    genres_seen, types_seen = set(), set()
    stages = []

    for st in acts["stages"]:
        lanes = pack_lanes(st["acts"])
        out = []
        for a in st["acts"]:
            name = a["n"]
            cur = curated.get(name, {})
            genres_seen.update(a["genres"])
            types_seen.add(a["type"])
            out.append({
                "name": a.get("display", name), "q": name,
                "s": a["s"], "e": a["e"], "sm": mins(a["s"]), "em": mins(a["e"]),
                "type": a["type"], "genres": a["genres"], "lane": a["lane"],
                "day": "d1",
                "b2b": a.get("b2b", False), "allday": a.get("allday", False),
                "nomusic": a.get("nomusic", False), "note": cur.get("note", ""),
                "direct": {k: v for k, v in cur.items()
                           if k not in ("note", "sq") and not k.startswith("_")},
                "search": {} if a.get("nomusic") else search_links(name, cur),
            })
        stages.append({
            "id": st["id"], "num": st["num"], "name": st["name"],
            "short": st.get("short", st["name"]), "location": st["location"],
            "blurb": st["blurb"], "color": STAGE_COLORS[st["id"]],
            "lat": st["lat"], "lon": st["lon"], "lanes": {"d1": lanes},
            "acts": sorted(out, key=lambda x: x["sm"]),
        })

    payload = {
        "event": acts["event"], "stages": stages, "poi": acts.get("poi", []),
        "genreLabels": {g: GENRE_LABELS[g] for g in GENRE_LABELS if g in genres_seen},
        "typeLabels": {t: TYPE_LABELS[t] for t in TYPE_LABELS if t in types_seen},
        "days": [{"id": "d1", "label": "Sat 1 August", "short": "Sat",
                  "date": acts["event"]["date"], "start": DAY_START, "end": DAY_END}],
        "presets": {"live": "alive", "second": "rap"}, "hasPoster": True,
        "basemap": basemap,
    }

    art_payload = {
        name: {"src": data_uri(ROOT / "assets" / "art" / v["file"]), "source": v["source"]}
        for name, v in artwork.items()
    }

    html = (ROOT / "scripts" / "template.html").read_text()
    ar = f'{basemap["wPixels"]}/{basemap["hPixels"]}'
    for token, value in [
        ("__DATA__", json.dumps(payload, ensure_ascii=False, separators=(",", ":"))),
        ("__ART__", json.dumps(art_payload, ensure_ascii=False, separators=(",", ":"))),
        ("__BASEMAP__", data_uri(ROOT / "assets" / "basemap.jpg")),
        ("__POSTER__", data_uri(ROOT / "assets" / "map.jpg")),
        ("__SATELLITE__", data_uri(ROOT / "assets" / "satellite.jpg")),
        ("__BASEMAP_LIGHT__", data_uri(ROOT / "assets" / "basemap-light.jpg")),
        ("__LOGO__", data_uri(ROOT / "assets" / "logo.png")),
        ("__TEXTURE__", data_uri(ROOT / "assets" / "texture.jpg")),
        ("__MAP_AR__", ar),
        ("__THEME__", ""),
        ("__HOME__", "../"),
        ("__NAV_CSS__", (ROOT / "scripts" / "_nav.css").read_text()),
        ("__TOKENS__", (ROOT / "scripts" / "_tokens.css").read_text()),
        ("__FONTCSS__", ""),
        ("__YEAR__", '2026'),
        ("__STAGES__", '9'),
        ("__WHEN__", 'Sat <b>1 August</b> <i>·</i> 12:00–22:00'),
        ("__WHERE__", 'Alppila, Helsinki <i>·</i> free entry'),
        ("__SITE_URL__", 'https://www.kallioblockparty.org/'),
        ("__SITE_LABEL__", 'kallioblockparty.org'),
        ("__SCHEDULE_URL__", 'https://www.kallioblockparty.org/program/'),
        ("__SCHEDULE_LABEL__", 'Official programme'),
        ("__TICKER__", ''),
        ("__BRANDNAME__", 'Kallio Block Party'),
        ("__PAGETITLE__", 'Kallio Block Party 2026 aikataulu & timetable — set times'),
        ("__METADESC__", 'Kallio Block Party 2026 timetable and aikataulu: all 98 acts on 9 stages in Alppila, Helsinki, 1 August. Set times, esiintyjät, genre filters and a stage map. Free entry, works offline.'),
        ("__KEYWORDS__", 'Kallio Block Party 2026, Kallio Block Party aikataulu, Kallio Block Party esiintyjät, Kallio Block Party ohjelma, KBP 2026 timetable, set times, Alppila Helsinki, ilmainen festivaali Helsinki, free festival Helsinki, techno, stage map'),
        ("__OG__", (lambda _f: seo.head(
            f"{seo.BASE}/{_f['planner']}",
            f"{_f['name']} {_f['year']} timetable — set times, stages and map",
            f"Plannable timetable for {_f['name']} {_f['year']}: {_f['stats']['acts']} acts "
            f"across {_f['stats']['stages']} stages, with artist previews, genre filters and an "
            f"interactive stage map. Works offline once loaded.",
            f"{seo.BASE}/assets/og/kallio.jpg",
            kind="article",
            jsonld=[seo.festival_event(_f), seo.faq(_f), seo.breadcrumb(_f)],
        ))(schema.festival("kbp"))),
        ("__FAQHTML__", seo.faq_html(schema.festival("kbp"))),
        ("__OFFLINE__", (ROOT / "scripts" / "_offline.html").read_text()),
        ("__SETTINGS__", (ROOT / "scripts" / "_settings.html").read_text()),
        ("__FOOTER__", (ROOT / "scripts" / "_footer.html").read_text()),
        ("__FOOTER_CSS__", (ROOT / "scripts" / "_footer.css").read_text()),
        ("__ROOT__", "../"),
        ("__NOTE__", '<p>Timetable transcribed from the organiser\'s official “Full Schedule in One Picture” and cross-checked against <a href="https://www.klangi.fi/uutiset/kallio-block-party-2026-ohjelma-aikataulu/" target="_blank" rel="noopener">klangi.fi</a>; where they disagreed the official image won.</p><p>Stage pins are the organiser\'s map badges snapped to the real street junctions they sit on. Street map © OpenStreetMap contributors, tiles © CARTO; satellite imagery © Esri. The “Official” layer is the organiser\'s own map.</p><p>An unofficial planner, not affiliated with the organisers. Also here: the <a href="../flow/">Flow Festival 2026 planner</a>, same engine.</p>'),
        ("__CUR_PRIVACY__", ""), ("__CUR_TERMS__", ""), ("__CUR_ABOUT__", ""),
        ("__CUR_FAQ__", ""),
        ("__SETTINGS_CSS__", (ROOT / "scripts" / "_settings.css").read_text()),
        ("__PAGEFX__", (ROOT / "scripts" / "_pagefx.html").read_text()),
        ("__CONTACT__", schema.load()["site"]["contact"]),
        ("__PROVENANCE__", '  <p>Timetable transcribed from the organiser\'s official “Full Schedule in One Picture” and\n  cross-checked against <a href="https://www.klangi.fi/uutiset/kallio-block-party-2026-ohjelma-aikataulu/" target="_blank" rel="noopener">klangi.fi</a>; where they disagreed the official image won.</p>\n  <p>Stage pins are the organiser\'s map badges snapped to the real street junctions they sit on, so\n  positions are accurate to the corner rather than the metre. Street map © OpenStreetMap\n  contributors, tiles © CARTO; satellite imagery © Esri. The “Official” layer is the organiser\'s\n  own map.</p>'),
        ("__DECO__", (ROOT / "scripts" / "deco-kbp.html").read_text()),
        ("__SIBLING__", '<p>Planning Flow too? There is a '
                        '<a href="../flow/">Flow Festival 2026 planner</a> built from the same engine.</p>'),
    ]:
        html = html.replace(token, value)

    leftover = [t for t in ("__DATA__", "__ART__", "__BASEMAP__", "__POSTER__", "__LOGO__", "__SATELLITE__", "__TEXTURE__", "__BASEMAP_LIGHT__",
                            "__FONT_LATIN__", "__FONT_EXT__", "__FONT_TITLE__", "__THEME__", "__SIBLING__", "__DECO__", "__HOME__", "__MAP_AR__") if t in html]
    if leftover:
        raise SystemExit(f"unreplaced tokens: {leftover}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(html)
    n = sum(len(s["acts"]) for s in stages)
    print(f"{OUT}\n  {n} acts · {len(stages)} stages · {len(art_payload)} artworks "
          f"· {OUT.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
