#!/usr/bin/env python3
"""Social cards and structured data, shared by every builder.

One place decides what a page claims about itself, so the canonical URL, the
Open Graph card and the JSON-LD cannot drift apart from each other.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE = "https://uenian33.github.io/flanner"
SITE = "Flanner"


def _esc(v: str) -> str:
    return (str(v).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


# A verification token pastes in here once, and every page carries it. Google
# Search Console and Bing Webmaster Tools both accept the meta-tag method, which
# survives a rebuild in a way an uploaded HTML file does not.
GOOGLE_VERIFY = ""
BING_VERIFY = ""

# Told to every crawler on every page. The defaults are conservative — image
# previews are capped and snippets truncated — and a festival planner wants the
# opposite: a large thumbnail in Discover and a full answer in the snippet.
ROBOTS = ("index,follow,max-image-preview:large,max-snippet:-1,max-video-preview:-1")


def head(url: str, title: str, desc: str, image: str,
         kind: str = "website", jsonld: dict | list | None = None) -> str:
    """The block that goes under <title>: canonical, Open Graph, X, JSON-LD."""
    tags = [
        f'<link rel="canonical" href="{_esc(url)}">',
        f'<meta name="robots" content="{ROBOTS}">',
        # The audience is in Finland and searches in both languages, so the page
        # advertises Finnish as an alternate locale even though it is written in
        # English. No hreflang: there is no separate Finnish URL to point at, and
        # a self-referential hreflang would be a lie about a translation.
        '<meta name="geo.region" content="FI-18">',
        '<meta name="geo.placename" content="Helsinki">',
        f'<meta property="og:type" content="{kind}">',
        f'<meta property="og:site_name" content="{SITE}">',
        f'<meta property="og:locale" content="en_GB">',
        f'<meta property="og:locale:alternate" content="fi_FI">',
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
    if GOOGLE_VERIFY:
        tags.append(f'<meta name="google-site-verification" content="{_esc(GOOGLE_VERIFY)}">')
    if BING_VERIFY:
        tags.append(f'<meta name="msvalidate.01" content="{_esc(BING_VERIFY)}">')
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
            "description": "Plannable timetables for Helsinki festivals — "
                           "aikataulut, esiintyjät ja lavakartat.",
            "inLanguage": ["en", "fi"],
            "potentialAction": {
                "@type": "SearchAction",
                "target": {"@type": "EntryPoint",
                           "urlTemplate": f"{BASE}/?q={{search_term_string}}"},
                "query-input": "required name=search_term_string",
            },
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


# IndexNow: Bing, Yandex, Seznam and Naver accept a push instead of waiting to
# be crawled. The key is not a secret — it is published at the URL below purely
# to prove the submitter controls the host. Google does not participate.
INDEXNOW_KEY = "b7f4e2a91c8d45f6ae30b25c7d914e08"


def write_robots_and_sitemap(pages: list[tuple[str, str]]) -> None:
    """pages: (path, lastmod) — path relative to BASE, e.g. '' or 'kallio/'."""
    (ROOT / f"{INDEXNOW_KEY}.txt").write_text(INDEXNOW_KEY + "\n")
    (ROOT / "robots.txt").write_text(
        "# Flanner — https://uenian33.github.io/flanner/\n"
        "User-agent: *\n"
        "Allow: /\n\n"
        "# Nothing here is worth hiding, but these paths are build inputs, not\n"
        "# pages, and a crawler that indexes them wastes its budget on this host.\n"
        "Disallow: /scripts/\n"
        "Disallow: /tools/\n\n"
        "# The generative crawlers are welcome: an assistant that can read the\n"
        "# timetable is another way somebody finds a set they would have missed.\n"
        "User-agent: GPTBot\n"
        "User-agent: OAI-SearchBot\n"
        "User-agent: ChatGPT-User\n"
        "User-agent: PerplexityBot\n"
        "User-agent: ClaudeBot\n"
        "User-agent: Google-Extended\n"
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


_FI_MONTH = {1: "tammikuuta", 2: "helmikuuta", 3: "maaliskuuta", 4: "huhtikuuta",
             5: "toukokuuta", 6: "kesäkuuta", 7: "heinäkuuta", 8: "elokuuta",
             9: "syyskuuta", 10: "lokakuuta", 11: "marraskuuta", 12: "joulukuuta"}


def _fi_dates(f: dict) -> str:
    """'14.–16. elokuuta 2026' from the ISO start/end already in the data."""
    from datetime import date
    a = date.fromisoformat(f["start"][:10])
    b = date.fromisoformat(f["end"][:10])
    if a == b:
        return f"{a.day}. {_FI_MONTH[a.month]} {a.year}"
    if a.month == b.month:
        return f"{a.day}.–{b.day}. {_FI_MONTH[a.month]} {a.year}"
    return f"{a.day}. {_FI_MONTH[a.month]} – {b.day}. {_FI_MONTH[b.month]} {b.year}"


def _qa(f: dict) -> list[tuple[str, str, str]]:
    """(lang, question, answer) — what people actually type before a festival.

    Half of these are in Finnish. The audience is in Helsinki and searches for
    'aikataulu' and 'esiintyjät' at least as often as for 'timetable', and a
    page written only in English never surfaces for those queries at all.
    """
    n = f"{f['name']} {f['year']}"
    st, days = f["stats"], f["stats"]["days"]
    stars4 = ", ".join(f["stars"][:4])
    fi_dates = _fi_dates(f)
    return [
        ("en", f"When is {n}?",
         f"{n} runs {f['dates']} at {f['city']}."),
        ("fi", f"Milloin {n} järjestetään?",
         f"{n} järjestetään {fi_dates}, paikkana {f['city']}."),
        ("en", f"What time do {f['name']} set times start?",
         f"Flanner lists every set time for all {st['stages']} stages — "
         f"{st['acts']} acts across {days} day{'s' if days > 1 else ''}. "
         "Open the planner to see the full grid."),
        ("fi", f"Mistä löydän {n} aikataulun?",
         f"Flanner näyttää koko aikataulun: {st['acts']} esiintyjää {st['stages']} lavalla "
         f"{days} päivän aikana. Voit suodattaa esiintyjiä genren mukaan, hakea artistia "
         "nimellä ja koota oman ohjelmasi."),
        ("en", f"Who is playing {n}?",
         f"Headliners include {stars4}, plus {st['acts'] - 4} more acts."),
        ("fi", f"Ketkä esiintyvät {n} -festivaalilla?",
         f"Esiintyjiin kuuluvat {stars4} sekä {st['acts'] - 4} muuta artistia. "
         "Koko esiintyjälista löytyy planner-sivulta aakkosjärjestyksessä."),
        ("en", f"Is there a {f['name']} timetable I can plan with?",
         "Yes — Flanner turns the official schedule into a grid you can filter by genre, "
         "search by artist, and save your own route from. It works offline once loaded."),
        ("fi", "Toimiiko aikataulu ilman nettiyhteyttä?",
         "Kyllä. Koko sivu tallentuu selaimeesi, joten aikataulu, kartta ja oma ohjelmasi "
         "toimivat myös silloin kun festivaalialueella ei ole kenttää."),
    ]


def faq(f: dict) -> dict:
    """schema.org/FAQPage — the same questions the page shows, for rich results."""
    return {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "inLanguage": ["en", "fi"],
        "mainEntity": [
            {"@type": "Question", "name": q, "inLanguage": lang,
             "acceptedAnswer": {"@type": "Answer", "text": a}}
            for lang, q, a in _qa(f)
        ],
    }


def faq_html(f: dict) -> str:
    """The same Q&A as crawlable markup.

    Structured data alone is not indexable content — Google will show it as a
    rich result but will not rank the page on words that appear nowhere in the
    document. The Finnish answers have to exist as real text to do any work.
    """
    return "\n".join(
        f'<div class="faqq" lang="{lang}"><h3>{_esc(q)}</h3><p>{_esc(a)}</p></div>'
        for lang, q, a in _qa(f)
    )


def _site_qa(festivals: list[dict]) -> list[tuple[str, str, str]]:
    """Site-level questions — the ones that are about Flanner, not one festival."""
    names = ", ".join(f"{f['name']} {f['year']}" for f in festivals)
    fi_names = " ja ".join(f"{f['name']} {f['year']}" for f in festivals)
    return [
        ("en", "What is Flanner?",
         "Flanner turns a Helsinki festival's official timetable into a grid you can plan "
         "against: filter by genre, search for an artist, see where two sets clash, and "
         "save your own route. It is free, has no accounts and runs no analytics."),
        ("fi", "Mikä Flanner on?",
         "Flanner muuttaa helsinkiläisfestivaalien viralliset aikataulut muotoon, jota voi "
         "oikeasti suunnitella: suodata genren mukaan, hae artistia nimellä, näe milloin kaksi "
         "keikkaa menevät päällekkäin ja kokoa oma ohjelmasi. Ilmainen, ei tunnuksia."),
        ("en", "Which festivals are covered?",
         f"Right now {names}. More are added as their timetables are published — "
         "a request for one is welcome."),
        ("fi", "Mitkä festivaalit ovat mukana?",
         f"Tällä hetkellä {fi_names}. Lisää tulee sitä mukaa kun aikataulut julkaistaan."),
        ("en", "Is Flanner official?",
         "No. It is an independent, unofficial planner, not affiliated with any festival. "
         "Timetables come from each organiser's own published schedule, and where they "
         "disagree with anything shown here, the organiser is right."),
        ("fi", "Onko Flanner virallinen?",
         "Ei. Flanner on riippumaton, epävirallinen aikataulusovellus, joka ei ole sidoksissa "
         "mihinkään festivaaliin. Aikataulut perustuvat järjestäjien omiin julkaisuihin."),
        ("en", "Does it work without a signal?",
         "Yes. Flanner installs to your home screen and keeps every page it has opened, "
         "so the timetable, the stage map and your own plan keep working with no connection. "
         "Settings has a Save button that fetches the whole site in one go, for a festival "
         "you know you will reach before the signal does."),
        ("fi", "Toimiiko se ilman verkkoyhteyttä?",
         "Kyllä. Flannerin voi asentaa puhelimen aloitusnäytölle, ja se säilyttää jokaisen "
         "avatun sivun. Aikataulu, kartta ja oma ohjelmasi toimivat ilman kenttää. "
         "Asetuksista voi tallentaa koko sivuston kerralla."),
    ]


def site_faq(festivals: list[dict]) -> dict:
    return {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "inLanguage": ["en", "fi"],
        "mainEntity": [
            {"@type": "Question", "name": q, "inLanguage": lang,
             "acceptedAnswer": {"@type": "Answer", "text": a}}
            for lang, q, a in _site_qa(festivals)
        ],
    }


def site_faq_blocks(festivals: list[dict]) -> list[dict]:
    """The same questions as info.json content blocks, for the FAQ page."""
    return [b for lang, q, a in _site_qa(festivals)
            for b in ({"t": "h2", "v": q}, {"t": "p", "v": a})]


def site_faq_html(festivals: list[dict]) -> str:
    return "\n".join(
        f'<div class="faqq" lang="{lang}"><h3>{_esc(q)}</h3><p>{_esc(a)}</p></div>'
        for lang, q, a in _site_qa(festivals)
    )


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
