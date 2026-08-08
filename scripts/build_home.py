#!/usr/bin/env python3
"""Build the Festival Planner home page.

One card per festival that has a planner, grouped by month, with a highlight
rail on top. The markup, the styles and the data travel in the page; the font
and the photographs are files the whole site shares, so opening a planner after
this does not download either of them again.
"""
import json, pathlib, re
from assets import ROOT
import fontsub
import m3color
import mwc
import a2hs
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

# React, ReactDOM, Leaflet, the runtime — in that order, because the runtime
# needs React in the document before it compiles. The names carry a hash of
# their contents, so they are found rather than written down.
LIB_ORDER = ("react-", "react-dom-", "leaflet-", "dc-runtime-")


def sprite(html: str) -> str:
    """Point a shared partial's glyph references at this page's own sprite."""
    return html.replace('href="#i-', 'href="#h-i-')


def shell_libs() -> list[str]:
    # The stem is followed by the hash and nothing else, so `react-` does not
    # also claim `react-dom-`.
    js = sorted((ROOT / "assets" / "js").glob("*.js"))
    out = []
    for stem in LIB_ORDER:
        pat = re.compile(re.escape(stem) + r"[0-9a-f]+\.js$")
        hit = [f for f in js if pat.match(f.name)]
        if len(hit) != 1:
            raise SystemExit(f"assets/js: expected one {stem}<hash>.js, found {len(hit)}")
        out.append(f"./assets/js/{hit[0].name}")
    return out

def screen_id(key: str) -> str:
    """The element a planner mounts into. The shell derives the same name."""
    return "p" + key[:1].upper() + key[1:]


def main():
    # Validated and normalised before anything is rendered — see schema.py.
    cfg = schema.load()
    # Where the site's festivals are, for the place filter — derived from the
    # records rather than listed a second time.
    cfg["places"] = schema.places(cfg)
    for f in cfg["festivals"]:
        # A festival we have not built a planner for has no poster and no
        # wordmark of its own; its card draws the category's artwork instead.
        # Named, not carried. A data URI cannot be lazy — the browser has the
        # bytes the moment it has the markup — so inlining these was paying for
        # every festival's photograph up front to render the two cards that are
        # on screen. As URLs the `loading="lazy"` the card already sets starts
        # working, and the shared logo is fetched once however many cards show it.
        if f.get("promo"):
            f["promoSrc"] = f"./assets/home/{f['promo']}"
        if f.get("logo"):
            f["logoSrc"] = f"./assets/{f['logo']}"
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
            "Flanner — Finnish festival timetables & aikataulut you can plan with",
            "Free stage grids, set times and maps for festivals in Helsinki, Tampere and "
            "Espoo — aikataulut, esiintyjät ja lavakartat. One page per festival, "
            "works offline once loaded.",
            f"{seo.BASE}/assets/og/home.jpg",
            jsonld=seo.site_jsonld(planned)
                   + [seo.festival_event(f) for f in planned]
        )),
        # First thing in the head, before a stylesheet is fetched, so the
        # first paint is already the reader's theme rather than a white
        # flash on the way to a black page.
        ("__THEMEBOOT__", schema.theme_boot()),
        # The illustrated steps for putting this on a home screen. The
        # pictures are real screenshots, optimised on the way in; a step
        # whose screenshot has not been dropped in yet is words alone.
        ("__A2HS__", json.dumps(a2hs.build(), ensure_ascii=False,
                                separators=(",", ":"))),
        ("__CATCSS__", schema.category_css(cfg)),
        # The namespace a planner writes its picks under. Stated once in
        # schema.py, because a page that asks under the wrong key finds nothing
        # and quietly stops offering to open a planner at your plan.
        ("__PICKS_NS__", schema.PICKS_NS),
        # The two places a colour that is not the page's own belongs: a
        # festival's own drawn cover, and the highlight, which is one festival
        # at a time rather than a list. The shell stays monochrome — see below.
        ("__ARTCSS__", schema.artwork_css(cfg) + "\n" + schema.highlight_css(cfg)
                       + "\n" + schema.calendar_css(cfg)),
        # The home page is drawn in Material's monochrome variant. Every
        # planner is themed from its own festival's colour, so the page that
        # lists them has to be the one surface in the site with no colour of
        # its own — otherwise the shell would be advertising a hue that
        # belongs to nothing on it, and each planner's would arrive as a
        # clash rather than as the festival's. What colour there is here
        # belongs to the festivals: their photographs and their wordmarks.
        ("__TOKENS__", m3color.css(m3color.SOURCE, mono=True) + "\n" +
         (ROOT / "scripts" / "_tokens.css").read_text()),
        ("__FONTCSS__", (ROOT / "scripts" / "_font.css").read_text()),
        ("__NAV_CSS__", (ROOT / "scripts" / "_nav.css").read_text()),
        ("__FOOTER_CSS__", (ROOT / "scripts" / "_footer.css").read_text()),
        # The shared partials name the sprite the way every other page does.
        # This page prefixes its own symbols, because on a phone it hosts a
        # planner and an id is document-wide — so their references are moved
        # with them, here rather than in the partials the other pages share.
        ("__SETTINGS__", sprite((ROOT / "scripts" / "_settings.html").read_text())),
        ("__FOOTER__", sprite(schema.footer())),
        ("__ROOT__", "./"),
        ("__NOTE__", NOTE),
        ("__CUR_PRIVACY__", ""), ("__CUR_TERMS__", ""), ("__CUR_ABOUT__", ""),
        ("__CUR_FAQ__", ""),
        ("__OFFLINE__", (ROOT / "scripts" / "_offline.html").read_text()),
        ("__SETTINGS_CSS__", (ROOT / "scripts" / "_settings.css").read_text()),
        # The app shell — the dock, the screens and the router that swaps
        # them without a document load. It names the four libraries a planner
        # needs, which are content-hashed, so it reads them off disk in the
        # order the runtime wants rather than repeating the names here; and it
        # names the planners, which are a folder someone drops in, so it reads
        # those off the records for the same reason.
        ("__SHELL__", (ROOT / "scripts" / "_shell.html").read_text()
            .replace("__LIBS__", json.dumps(shell_libs(), separators=(",", ":")))
            .replace("__PLANNERS__", json.dumps(schema.planner_dirs(), separators=(",", ":")))),
        # One empty screen per planner, for the shell to mount into. Nothing is
        # fetched until a reader asks for one.
        ("__SHELL_PAGES__", "\n".join(
            f'<section class="page shell-page" id="{screen_id(k)}" hidden></section>'
            for k in schema.planner_dirs())),
        ("__PAGEFX__", schema.pagefx()),
        ("__MWC__", mwc.script()),
        ("__CONTACT__", cfg["site"]["contact"]),
    ]:
        html = html.replace(tok, val)
    left = [t for t in ("__DATA__", "__FONTCSS__", "__CONTACT__") if t in html]
    if left:
        raise SystemExit(f"unreplaced tokens: {left}")
    OUT.write_text(fontsub.link(html, "./"))
    print(f"{OUT}\n  {len(cfg['festivals'])} festivals · {OUT.stat().st_size // 1024} KB")

if __name__ == "__main__":
    main()
