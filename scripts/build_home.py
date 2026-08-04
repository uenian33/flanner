#!/usr/bin/env python3
"""Build the Festival Planner home page.

One card per festival that has a planner, grouped by month, with a highlight
rail on top. Everything is inlined so the page is a single file like the
planners it links to.
"""
import json, pathlib
from build import ROOT, data_uri
import fontsub
import m3color
import mwc
import schema
import seo

NOTE = (
    "<p>Unofficial planners, not affiliated with any of these festivals. Timetables come from "
    "each organiser's own published schedule; artwork and links from their own sites.</p>"
    "<p>Each planner is a single page that keeps working offline once loaded, stores your picks "
    "on your own device, and collects nothing.</p>"
)

OUT = ROOT / "index.html"
H = ROOT / "assets" / "home"

def main():
    # Validated and normalised before anything is rendered — see schema.py.
    cfg = schema.load()
    for f in cfg["festivals"]:
        # A festival we have not built a planner for has no poster and no
        # wordmark of its own; its card draws the category's artwork instead.
        if f.get("promo"):
            f["promoSrc"] = data_uri(H / f["promo"])
        if f.get("logo"):
            f["logoSrc"] = data_uri(ROOT / "assets" / f["logo"])
        f.pop("promo", None); f.pop("logo", None)
    # The structured data describes the pages this site publishes, so only the
    # festivals with a planner of ours appear in it.
    planned = [f for f in cfg["festivals"] if f.get("planner")]

    html = (ROOT / "scripts" / "home.html").read_text()
    for tok, val in [
        ("__DATA__", json.dumps(cfg, ensure_ascii=False, separators=(",", ":"))),
        ("__BASE__", seo.BASE),
        ("__OG__", seo.head(
            f"{seo.BASE}/",
            "Flanner — Helsinki festival timetables & aikataulut you can plan with",
            "Free stage grids, set times and maps for Flow Festival and Kallio Block Party "
            "2026 — aikataulut, esiintyjät ja lavakartat. One page per festival, "
            "works offline once loaded.",
            f"{seo.BASE}/assets/og/home.jpg",
            jsonld=seo.site_jsonld(planned)
                   + [seo.festival_event(f) for f in planned]
        )),
        ("__CATCSS__", schema.category_css(cfg)),
        ("__TOKENS__", m3color.css(m3color.SOURCE) + "\n" +
         (ROOT / "scripts" / "_tokens.css").read_text()),
        ("__FONTCSS__", (ROOT / "scripts" / "_font.css").read_text()),
        ("__NAV_CSS__", (ROOT / "scripts" / "_nav.css").read_text()),
        ("__FOOTER_CSS__", (ROOT / "scripts" / "_footer.css").read_text()),
        ("__SETTINGS__", (ROOT / "scripts" / "_settings.html").read_text()),
        ("__FOOTER__", (ROOT / "scripts" / "_footer.html").read_text()),
        ("__ROOT__", "./"),
        ("__NOTE__", NOTE),
        ("__CUR_PRIVACY__", ""), ("__CUR_TERMS__", ""), ("__CUR_ABOUT__", ""),
        ("__CUR_FAQ__", ""),
        ("__OFFLINE__", (ROOT / "scripts" / "_offline.html").read_text()),
        ("__SETTINGS_CSS__", (ROOT / "scripts" / "_settings.css").read_text()),
        ("__PAGEFX__", (ROOT / "scripts" / "_pagefx.html").read_text()),
        ("__MWC__", mwc.script()),
        ("__CONTACT__", cfg["site"]["contact"]),
    ]:
        html = html.replace(tok, val)
    left = [t for t in ("__DATA__", "__FONTCSS__", "__CONTACT__") if t in html]
    if left:
        raise SystemExit(f"unreplaced tokens: {left}")
    OUT.write_text(fontsub.inline(html))
    print(f"{OUT}\n  {len(cfg['festivals'])} festivals · {OUT.stat().st_size // 1024} KB")

if __name__ == "__main__":
    main()
