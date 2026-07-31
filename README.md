# Kallio Block Party 2026 — stage planner

An unofficial planner for the 1 Aug 2026 street festival in Alppila, Helsinki.
Live at **https://uenian33.github.io/kallioblockpartyplanner/**

One self-contained page: font, both basemaps, the official map, the logo and every
artwork are inlined as data URIs, so it works with no signal once loaded. Picks are
saved to a first-party cookie on the reader's own device — no server, no analytics,
no third-party code, nothing collected.

Not affiliated with the organisers. Corrections welcome: wenyany94@gmail.com

## Deploying

`index.html` at the repo root is the whole site; `.nojekyll` stops Pages from
processing it. Rebuild and push:

```bash
python3 scripts/build.py && git commit -am "Update" && git push
```

- **`index.html`** — the planner. Timetable and list views, filters, artist cards
  with artwork and streaming links, a live map with stage pins, and a route planner.
  Light and dark themes, live "on now" indicators, and touch gestures throughout.
- **`calibrate.html`** — drag the stage pins onto their real positions and copy
  out corrected coordinates. Use this whenever a pin looks wrong.

## Rebuilding

```bash
python3 scripts/build.py && python3 scripts/build_calibrate.py
```

`build.py` reads `data/acts.json`, `data/basemap.json`, `data/artwork.json` and
`scripts/curated.json`, packs each stage's acts into non-overlapping lanes, and
substitutes everything into `scripts/template.html`. Edit the template for markup,
style and behaviour; edit `acts.json` for the timetable, genres and coordinates.

## Storage and consent

Picks, theme and view are written to a first-party cookie once the reader
accepts. Browsers block `document.cookie` on `file://` URLs, so the store falls
back to `localStorage` for the offline copy and the footer says which is in use.
Nothing is stored before consent — the plan is held in memory for that visit —
and declining leaves the planner fully usable. The route is saved as act indices
rather than names so a full day fits in one cookie.

There is nothing to collect: no server, no analytics, no third-party script, no
network request at runtime. The consent notice says exactly that, and the
footer's "Cookies & privacy" button reopens it.

## Map layers

**Street** (OSM/CARTO, light and dark to match the theme), **Satellite** (Esri
imagery) and **Official** (the organiser's poster). All three are baked into the
file, so the map works with no network. Every stage links out to Google Maps
walking directions, and a picked route becomes one multi-stop walking route.

## Correcting stage positions

1. Open `calibrate.html`, drag any misplaced pin (official map is alongside).
2. Hit **Copy corrected coordinates** — you get `{"alive":[lat,lon], …}`.
3. Paste those into the `lat`/`lon` fields of each stage in `data/acts.json`.
4. Rebuild.

## One-off data scripts

Run these only when the source data changes; their output is committed.

| Script | What it does |
|---|---|
| `geocode.py` | Pulls Alppila street geometry from Overpass and computes junctions. |
| `tiles.py` | Downloads CARTO dark basemap tiles, stitches, crops to the festival bbox, lifts the tone, writes `assets/basemap.jpg` + the Web Mercator origin in `data/basemap.json`. |
| `artwork.py` | Fetches artist images from Deezer and iTunes. |
| `enrich.py` | Bulk artist lookup against Deezer and MusicBrainz — a research aid, not a build input. |

## Data provenance

- **Timetable** — the organiser's "Full Schedule in One Picture"
  (`assets/full-schedule.png`), cross-checked against
  [klangi.fi](https://www.klangi.fi/uutiset/kallio-block-party-2026-ohjelma-aikataulu/).
  Where they disagreed the official image won: Soundgarden opens at 12:00, not 13:00.
- **Stage coordinates** — read off the organiser's map, then snapped to the real
  OSM junction each badge sits on. Accurate to the corner, not the metre — hence
  `calibrate.html`.
- **Basemap** — OpenStreetMap data, CARTO `dark_all` raster tiles at z17. Both
  require attribution, which is rendered on the map and in the footer.
- **Artwork and links** — Deezer and Apple Music, verified by hand. Automated
  name matching produced a lot of same-name strangers (a German ska band for
  "YEBO", a French prog group for "Wolve", one stock silhouette shared by three
  artists); those were dropped, so 20 of 92 musical acts carry a real image and
  the rest get a deterministic generated cover. Only confirmed profiles live in
  `scripts/curated.json`; everything else falls back to search URLs.
- **Genres** — the organisers' stage descriptions plus per-act classification.
  A guide, not gospel.

## Design notes

- **Palette** sampled from the organiser's own artwork: neon green `#b6fc46`,
  sky blue `#a8c4ee`, orange-red `#fc6238`. The light theme follows Flow
  Festival's bright style — grey paper, black ink, hard hairlines, one accent.
- **Stage hues carry text**, so `--cText` mixes each hue toward ink in the light
  theme; 45% keeps the brightest stage colour above 4.5:1 on grey paper.
- **The bottom bar** follows kinoon.fi's mobile material: full pill,
  `blur(12px) saturate(1.5)` over `rgba(22,22,25,.7)`, 1px hairline.
- **Type**: Rubik Bubbles for the wordmark, echoing the organiser's hand-drawn
  logo; Bricolage Grotesque for everything else.
- **The card** uses the iOS HIG type ramp and label opacities, opens at a medium
  detent, and moves between detents by transform rather than height.
- **Gestures**: swipe the sheet up to expand and down to dismiss, swipe a list
  row either way to add or drop it from the route, pinch the map to zoom.
- **Two layouts, not one scaled**: phones get a bottom tab bar, a full-width
  sheet and single-row scrolling filter groups. From 821px a left rail replaces
  the tab bar; from 1100px List view puts the map in a sticky column beside the
  list, and the act card turns landscape to match a landscape window.
- **Background** is a blurred crop of the organiser's poster under a scrim, so
  the page carries the festival's colour instead of a flat field.
