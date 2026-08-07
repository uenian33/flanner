#!/usr/bin/env python3
"""Build the Flow Festival 2026 planner from the same template as the KBP one.

Same engine, different festival: three days instead of one, Flow's own palette,
and artist links/portraits taken from Flow's own artist pages rather than
guessed from third-party APIs.
"""
import base64, json, pathlib, sys, urllib.parse
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import fontsub
import m3color
import seo
from build import ROOT, data_uri, pack_lanes, GENRE_LABELS, TYPE_LABELS
import schema

D = ROOT / "data" / "flow"
OUT = ROOT / "flow" / "index.html"

# Flow's bright style: warm grey paper, pure black ink, one electric accent.
THEME = """
:root{
  --kbp-green:#fff203; --kbp-sky:#bcbcbc; --kbp-red:#ff4a1c; --kbp-sand:#d9d9d9;
  --bg:#101010; --bg2:#191919; --panel:#1f1f1f; --panel2:#2a2a2a;
  --line:#2a2a2a; --line2:#3d3d3d;
  --tx:#f4f4f4; --tx2:#a8a8a8; --tx3:#8a8a8a;
  --accent-ink:#fff203; --on-accent:#111000; --shade:rgba(0,0,0,.55);
  --sheet:#151515; --sheet2:#1e1e1e;
  --chip-line:var(--line2);
  --glass:rgba(20,20,20,.72); --glass-line:rgba(255,255,255,.08);
  --glass-pill:rgba(255,255,255,.11); --glass-tx:rgba(255,255,255,.58); --glass-on:#fff;
}
:root[data-theme=light]{
  --bg:#f5f5f5; --bg2:#fff; --panel:#fafafa; --panel2:#ececec;
  --line:rgba(0,0,0,.13); --line2:rgba(0,0,0,.8);
  --tx:#000; --tx2:#3a3a3a; --tx3:#5c5c5c;
  --accent-ink:#6f6800; --on-accent:#000; --shade:rgba(0,0,0,.16);
  --sheet:#fff; --sheet2:#ededed;
  --chip-line:rgba(0,0,0,.26);
  --glass:rgba(255,255,255,.8); --glass-line:rgba(0,0,0,.16);
  --glass-pill:rgba(0,0,0,.09); --glass-tx:rgba(20,20,20,.6); --glass-on:#000;
}
.logo img{width:clamp(150px,24vw,260px)}
h1{font-size:var(--md-sys-typescale-headline-small-size);
  line-height:var(--md-sys-typescale-headline-small-line-height)}
@media(min-width:600px){h1{font-size:var(--md-sys-typescale-display-small-size);
  line-height:var(--md-sys-typescale-display-small-line-height)}}
@media(min-width:1200px){h1{font-size:var(--md-sys-typescale-display-medium-size);
  line-height:var(--md-sys-typescale-display-medium-line-height)}}

/* ── Flow's own visual language ───────────────────────────
   Their site is grey paper, black hairlines, one electric yellow, condensed
   uppercase headlines, fully-round buttons, and vertical yellow bars used as
   a barcode motif behind the masthead. */
@keyframes bargrow{0%,100%{transform:scaleY(1)}50%{transform:scaleY(var(--s,1.14))}}
.flowbars{overflow:hidden}
.flowbars i{position:absolute;left:var(--x);top:var(--t);width:var(--w);height:var(--h);
  background:var(--accent);transform-origin:50% 0;opacity:.9;
  animation:bargrow 5.5s ease-in-out infinite;animation-delay:var(--d)}
.flowbars i:nth-child(3n){--s:1.22;opacity:.55}
.flowbars i:nth-child(4n){--s:1.08;background:var(--tx);opacity:.14}
:root[data-theme=light] .flowbars i{opacity:1}
:root[data-theme=light] .flowbars i:nth-child(3n){opacity:.7}
@media(prefers-reduced-motion:reduce){.flowbars i{animation:none}}
@media(max-width:640px){.flowbars i:nth-child(n+8):nth-child(-n+10){display:none}}

/* condensed uppercase marquee, the strip that runs under their masthead */
.ticker{position:relative;overflow:hidden;border-top:1px solid var(--line2);
  border-bottom:1px solid var(--line2);background:var(--accent);margin-top:16px}
.ticker div{display:flex;gap:0;width:max-content;animation:tick 32s linear infinite}
.ticker span{font-family:var(--title);font-size:var(--md-sys-typescale-title-small-size);letter-spacing:.06em;
  text-transform:uppercase;color:#000;padding:7px 0;white-space:nowrap}
.ticker span::after{content:"◆";margin:0 18px;
  font-size:var(--md-sys-typescale-label-small-size);vertical-align:2px}
@keyframes tick{to{transform:translateX(-50%)}}
@media(prefers-reduced-motion:reduce){.ticker div{animation:none}}

/* buttons and chips take Flow's fully-round, hard-edged treatment */
.ghost,.chip,.cyes,.cno{border-radius:10rem}
.seg,.seg button,.iconbtn{border-radius:10rem}
h1{letter-spacing:.01em;line-height:.94}
.snm,.aname,.cbody h2{letter-spacing:-.005em}
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
        ("__MAP_AR__", f'{basemap["wPixels"]}/{basemap["hPixels"]}'),
        ("__THEME__", THEME),
        ("__HOME__", "../"),
        ("__NAV_CSS__", (ROOT / "scripts" / "_nav.css").read_text()),
        ("__TOKENS__", m3color.css(m3color.SOURCE) + "\n" +
         (ROOT / "scripts" / "_tokens.css").read_text()),
        ("__FONTCSS__", (ROOT / "scripts" / "_font.css").read_text()),
        ("__YEAR__", '2026'),
        ("__STAGES__", '10'),
        ("__WHEN__", '<b>14–16 August</b> <i>·</i> 3 days'),
        ("__WHERE__", 'Suvilahti, Helsinki'),
        ("__SITE_URL__", 'https://www.flowfestival.com/en/'),
        ("__SITE_LABEL__", 'flowfestival.com'),
        ("__SCHEDULE_URL__", 'https://www.flowfestival.com/en/schedule/'),
        ("__SCHEDULE_LABEL__", 'Official schedule'),
        ("__TICKER__", '<div class="ticker" aria-hidden="true"><div><span>14.–16.8.2026</span><span>FLOW FESTIVAL</span><span>SUVILAHTI</span><span>HELSINKI</span><span>156 ACTS</span><span>10 STAGES</span><span>3 DAYS</span><span>14.–16.8.2026</span><span>FLOW FESTIVAL</span><span>SUVILAHTI</span><span>HELSINKI</span><span>156 ACTS</span><span>10 STAGES</span><span>3 DAYS</span></div></div>'),
        ("__BRANDNAME__", 'Flow Festival'),
        ("__PAGETITLE__", 'Flow Festival 2026 aikataulu & timetable — set times, map'),
        ("__METADESC__", 'Flow Festival 2026 timetable and aikataulu: all 156 sets on 10 stages at Suvilahti, Helsinki, 14–16 August. Set times, esiintyjät, artist previews and a stage map. Works offline.'),
        ("__KEYWORDS__", 'Flow Festival 2026, Flow Festival aikataulu, Flow Festival 2026 esiintyjät, Flow Festival timetable, Flow Festival set times, Flow Festival ohjelma, Suvilahti Helsinki, festivaali Helsinki 2026, festival lineup'),
        ("__OG__", (lambda _f: seo.head(
            f"{seo.BASE}/{_f['planner']}",
            f"{_f['name']} {_f['year']} timetable — set times, stages and map",
            f"Plannable timetable for {_f['name']} {_f['year']}: {_f['stats']['acts']} acts "
            f"across {_f['stats']['stages']} stages, with artist previews, genre filters and an "
            f"interactive stage map. Works offline once loaded.",
            f"{seo.BASE}/assets/og/flow.jpg",
            kind="article",
            jsonld=[seo.festival_event(_f), seo.faq(_f), seo.breadcrumb(_f)],
        ))(next(x for x in json.loads((ROOT / "data" / "festivals.json").read_text())["festivals"] if x["id"] == "flow"))),
        ("__FAQHTML__", seo.faq_html(next(x for x in json.loads((ROOT / "data" / "festivals.json").read_text())["festivals"] if x["id"] == "flow"))),
        ("__OFFLINE__", (ROOT / "scripts" / "_offline.html").read_text()),
        ("__SETTINGS__", (ROOT / "scripts" / "_settings.html").read_text()),
        ("__FOOTER__", (ROOT / "scripts" / "_footer.html").read_text()),
        ("__FOOTER_CSS__", (ROOT / "scripts" / "_footer.css").read_text()),
        ("__ROOT__", "../"),
        ("__NOTE__", '<p>Set times transcribed from Flow Festival\'s own published timetable; where a listing and the official schedule disagreed, the official schedule won.</p><p>Stage pins are placed from the organiser\'s site plan against the real Suvilahti geometry. Street map © OpenStreetMap contributors, tiles © CARTO; satellite imagery © Esri.</p><p>An unofficial planner, not affiliated with the organisers. Also here: the <a href="../kallio/">Kallio Block Party 2026 planner</a>, same engine.</p>'),
        ("__CUR_PRIVACY__", ""), ("__CUR_TERMS__", ""), ("__CUR_ABOUT__", ""),
        ("__CUR_FAQ__", ""),
        ("__SETTINGS_CSS__", (ROOT / "scripts" / "_settings.css").read_text()),
        ("__PAGEFX__", schema.pagefx()),
        ("__CONTACT__", json.loads((ROOT / "data" / "festivals.json").read_text())["site"]["contact"]),
        ("__PROVENANCE__", "  <p>Set times transcribed from Flow Festival's own published timetable; where a listing and the\n  official schedule disagreed, the official schedule won.</p>\n  <p>Stage pins are placed from the organiser's site plan against the real Suvilahti geometry, so\n  positions are accurate to the yard rather than the metre. Street map © OpenStreetMap\n  contributors, tiles © CARTO; satellite imagery © Esri.</p>"),
        ("__DECO__", (ROOT / "scripts" / "deco-flow.html").read_text()),
        ("__SIBLING__", '<p>Also here: the '
                        '<a href="../kallio/">Kallio Block Party 2026 planner</a>, same engine.</p>'),
    ]:
        html = html.replace(tok, val)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(fontsub.inline(html))
    n = sum(len(s["acts"]) for s in stages)
    print(f"{OUT}\n  {n} sets · {len(stages)} stages · {len(acts['days'])} days · "
          f"{len(art)} portraits · {OUT.stat().st_size//1024} KB")

if __name__ == "__main__":
    build()
