# Flanner

Plannable timetables for Helsinki festivals — **<https://uenian33.github.io/flanner/>**

Each planner is a single self-contained HTML file: fonts, maps, artwork and code
are inlined, so once a page has loaded it makes no further network requests and
keeps working with no signal. Installable to a home screen, where it opens
without browser chrome.

| Page | |
|---|---|
| `/` | Festival list, highlights, search and filters |
| `/kallio/` | Kallio Block Party 2026 — 98 acts, 9 stages |
| `/flow/` | Flow Festival 2026 — 156 sets, 10 stages, 3 days |
| `/about/` `/terms/` `/privacy/` | About, terms, EU data policy |

## Building

Everything under `scripts/` generates the pages; never edit the built HTML.

```bash
python3 scripts/build.py        # kallio/index.html
python3 scripts/build_flow.py   # flow/index.html
python3 scripts/build_home.py   # index.html
python3 scripts/build_info.py   # about, terms, privacy
python3 scripts/build_og.py     # social cards
cd scripts && python3 build_pwa.py   # icons, manifest, service worker
```

Shared pieces are single files both templates include — `_nav.css`,
`_footer.html`, `_settings.html`, `_pagefx.html`, `_offline.html` — so the bar,
footer and settings card cannot drift between pages.

Timetables are transcribed from each organiser's published schedule. Unofficial,
not affiliated with any festival.
