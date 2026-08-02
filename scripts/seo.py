#!/usr/bin/env python3
"""Social cards and structured data, shared by every builder.

One place decides what a page claims about itself, so the canonical URL, the
Open Graph card and the JSON-LD cannot drift apart from each other.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE = "https://uenian33.github.io/kallioblockpartyplanner"
SITE = "Flanner"


def _esc(v: str) -> str:
    return (str(v).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def head(url: str, title: str, desc: str, image: str,
         kind: str = "website", jsonld: dict | list | None = None) -> str:
    """The block that goes under <title>: canonical, Open Graph, X, JSON-LD."""
    tags = [
        f'<link rel="canonical" href="{_esc(url)}">',
        f'<meta property="og:type" content="{kind}">',
        f'<meta property="og:site_name" content="{SITE}">',
        f'<meta property="og:locale" content="en_GB">',
        f'<meta property="og:url" content="{_esc(url)}">',
        f'<meta property="og:title" content="{_esc(title)}">',
        f'<meta property="og:description" content="{_esc(desc)}">',
        f'<meta property="og:image" content="{_esc(image)}">',
        '<meta property="og:image:width" content="1200">',
        '<meta property="og:image:height" content="630">',
        f'<meta property="og:image:alt" content="{_esc(title)}">',
        '<meta name="twitter:card" content="summary_large_image">',
        f'<meta name="twitter:title" content="{_esc(title)}">',
        f'<meta name="twitter:description" content="{_esc(desc)}">',
        f'<meta name="twitter:image" content="{_esc(image)}">',
    ]
    if jsonld is not None:
        tags.append('<script type="application/ld+json">'
                    + json.dumps(jsonld, ensure_ascii=False, separators=(",", ":"))
                    + "</script>")
    return "\n".join(tags)


def festival_event(f: dict) -> dict:
    """A festival as schema.org/MusicEvent, so it can surface as a rich result."""
    return {
        "@context": "https://schema.org",
        "@type": "MusicFestival",
        "name": f"{f['name']} {f['year']}",
        "startDate": f["start"],
        "endDate": f["end"],
        "eventStatus": "https://schema.org/EventScheduled",
        "eventAttendanceMode": "https://schema.org/OfflineEventAttendanceMode",
        "location": {
            "@type": "Place",
            "name": f["city"],
            "address": {"@type": "PostalAddress",
                        "addressLocality": "Helsinki", "addressCountry": "FI"},
        },
        "image": [f"{BASE}/assets/og/{'kallio' if f['id'] == 'kbp' else 'flow'}.jpg"],
        "description": f["description"],
        "url": f"{BASE}/{f['planner']}",
        "sameAs": [f["official"]],
        "performer": [{"@type": "MusicGroup", "name": n} for n in f["stars"]],
        "organizer": {"@type": "Organization", "name": f["name"], "url": f["official"]},
        "isAccessibleForFree": bool(f["free"]),
        "offers": {
            "@type": "Offer",
            "url": f["official"] if f["free"] else f["tickets"],
            "priceCurrency": "EUR",
            "availability": "https://schema.org/InStock",
            **({"price": "0"} if f["free"] else {}),
        },
    }


def site_jsonld(festivals: list[dict]) -> list:
    return [
        {
            "@context": "https://schema.org",
            "@type": "WebSite",
            "name": SITE,
            "alternateName": "Flanner — Festival Planner",
            "url": f"{BASE}/",
            "description": "Plannable timetables for Helsinki festivals.",
            "inLanguage": "en",
        },
        {
            "@context": "https://schema.org",
            "@type": "ItemList",
            "name": "Helsinki festival planners",
            "itemListElement": [
                {"@type": "ListItem", "position": i + 1,
                 "url": f"{BASE}/{f['planner']}",
                 "name": f"{f['name']} {f['year']}"}
                for i, f in enumerate(festivals)
            ],
        },
    ]


def write_robots_and_sitemap(pages: list[tuple[str, str]]) -> None:
    """pages: (path, lastmod) — path relative to BASE, e.g. '' or 'kallio/'."""
    (ROOT / "robots.txt").write_text(
        "User-agent: *\n"
        "Allow: /\n\n"
        f"Sitemap: {BASE}/sitemap.xml\n"
    )
    urls = "\n".join(
        f"  <url><loc>{BASE}/{p}</loc><lastmod>{m}</lastmod>"
        f"<changefreq>{'weekly' if p in ('', 'kallio/', 'flow/') else 'yearly'}</changefreq>"
        f"<priority>{'1.0' if p == '' else '0.9' if p in ('kallio/', 'flow/') else '0.4'}</priority></url>"
        for p, m in pages
    )
    (ROOT / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{urls}\n</urlset>\n"
    )
    print(f"  robots.txt · sitemap.xml ({len(pages)} urls)")


def faq(f: dict) -> dict:
    """The questions people type into a search box before a festival."""
    n = f"{f['name']} {f['year']}"
    qa = [
        (f"When is {n}?",
         f"{n} runs {f['dates']} at {f['city']}."),
        (f"What time do {f['name']} set times start?",
         f"Flanner lists every set time for all {f['stats']['stages']} stages — "
         f"{f['stats']['acts']} acts across {f['stats']['days']} "
         f"day{'s' if f['stats']['days'] > 1 else ''}. Open the planner to see the full grid."),
        (f"Who is playing {f['name']} {f['year']}?",
         "Headliners include " + ", ".join(f["stars"][:4]) +
         f", plus {f['stats']['acts'] - 4} more acts."),
        (f"Is there a {f['name']} timetable I can plan with?",
         "Yes — Flanner turns the official schedule into a grid you can filter by genre, "
         "search by artist, and save your own route from. It works offline once loaded."),
    ]
    return {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {"@type": "Question", "name": q,
             "acceptedAnswer": {"@type": "Answer", "text": a}}
            for q, a in qa
        ],
    }


def breadcrumb(f: dict) -> dict:
    return {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Flanner", "item": f"{BASE}/"},
            {"@type": "ListItem", "position": 2,
             "name": f"{f['name']} {f['year']}", "item": f"{BASE}/{f['planner']}"},
        ],
    }
