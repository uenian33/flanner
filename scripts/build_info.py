#!/usr/bin/env python3
"""Build the About / Terms / EU data policy pages.

One template, one JSON file of copy, three self-contained pages under
about/, terms/ and privacy/. Nothing here is fetched at runtime.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import seo

ROOT = Path(__file__).resolve().parent.parent

NOTE = ("<p>Unofficial planners, not affiliated with any of these festivals. Timetables come "
        "from each organiser's own published schedule; artwork and links from their own sites.</p>")


def render(block: str) -> str:
    """One content block of data/info.json into HTML."""
    kind, value = block["t"], block["v"]
    if kind == "lead":
        return f'<p class="lead">{value}</p>'
    if kind == "h2":
        return f"<h2>{value}</h2>"
    if kind == "p":
        return f"<p>{value}</p>"
    if kind == "callout":
        return f'<div class="callout">{value}</div>'
    if kind == "ul":
        return "<ul>" + "".join(f"<li>{i}</li>" for i in value) + "</ul>"
    raise ValueError(f"unknown block type {kind!r}")


def main() -> None:
    info = json.loads((ROOT / "data" / "info.json").read_text())
    cfg = json.loads((ROOT / "data" / "festivals.json").read_text())
    site = cfg["site"]
    template = (ROOT / "scripts" / "info.html").read_text()
    footer = (ROOT / "scripts" / "_footer.html").read_text()
    footer_css = (ROOT / "scripts" / "_footer.css").read_text()
    fontcss = (ROOT / "assets" / "font" / "festiplannr.css").read_text().strip()

    for page in info["pages"]:
        slug = page["slug"]
        html = template
        html = html.replace("__FOOTER__", footer)
        html = html.replace("__FOOTER_CSS__", footer_css)
        # The FAQ's questions live in seo.py, next to the structured data that
        # has to say the same thing — info.json carries only its lead.
        body = page["body"] + (seo.site_faq_blocks(cfg["festivals"])
                               if slug == "faq" else [])
        html = html.replace("__BODY__", "\n  ".join(render(b) for b in body))
        for token, value in [
            ("__FONTCSS__", fontcss),
            ("__TITLE__", page["title"]),
            ("__BLURB__", page["blurb"]),
            ("__UPDATED__", info["updated"]),
            ("__ROOT__", "../"),
            ("__NOTE__", NOTE),
            ("__PAGEFX__", (ROOT / "scripts" / "_pagefx.html").read_text()),
            ("__CONTACT__", site["contact"]),
            ("__BASE__", seo.BASE),
            ("__SLUG__", slug),
            ("__OG__", seo.head(
                f"{seo.BASE}/{slug}/",
                f"{page['title']} — Flanner",
                page["blurb"],
                f"{seo.BASE}/assets/og/info.jpg",
                kind="article",
                jsonld=seo.site_faq(cfg["festivals"]) if slug == "faq" else
                       {"@context": "https://schema.org", "@type": "WebPage",
                        "name": page["title"], "description": page["blurb"],
                        "url": f"{seo.BASE}/{slug}/",
                        "isPartOf": {"@type": "WebSite", "name": seo.SITE,
                                     "url": f"{seo.BASE}/"}},
            )),
        ]:
            html = html.replace(token, value)
        # mark the current page in the Info column, and un-link it
        for other in ("privacy", "terms", "about", "faq"):
            html = html.replace(
                f"__CUR_{other.upper()}__", ' aria-current="page"' if other == slug else ""
            )

        left = [t for t in ("__FONTCSS__", "__CONTACT__", "__BODY__") if t in html]
        if left:
            raise SystemExit(f"unreplaced tokens in {slug}: {left}")

        out = ROOT / slug / "index.html"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(html)
        print(f"  {out.relative_to(ROOT)} · {len(html) / 1024:.0f} KB")


if __name__ == "__main__":
    print(ROOT)
    main()
