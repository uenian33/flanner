#!/usr/bin/env python3
"""Build a planner page: the design from the artifact, the line-up from data.

    python3 scripts/build_planner.py            # both planners
    python3 scripts/build_planner.py kallio     # one

`scripts/planner.py` unpacks the design; everything here is the festival's own
side of it. Nothing about a line-up is written in this file: the stages, the
sets, the days and the facts under the title all come out of data/acts.json,
data/flow/ and data/festivals.json, so a corrected set time is a data edit.

Every substitution is anchored to a string in the design and fails the build if
that string moves — a silent miss would publish a planner carrying the design's
own sample line-up, which is the one failure nobody would notice.
"""
from __future__ import annotations

import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import planner as art_mod
import schema
import seo
from planner import MissingAnchor, inline_js, sub_once

ROOT = pathlib.Path(__file__).resolve().parent.parent

# ── the design's three categories ─────────────────────
# The component draws music, art and film. Our two festivals put on music and
# performance and no cinema, so 'film' is simply never emitted.
CAT_OF_TYPE = {
    "band": "music", "singer": "music", "dj": "music", "rap": "music",
    "host": "music", "live-electronic": "music", "live": "music",
    "performance": "art", "talk": "art", "workshop": "art",
    "screening": "film",
}
TYPE_LABEL = {
    "band": "Band", "singer": "Solo", "dj": "DJ", "rap": "Rap",
    "host": "Host", "live-electronic": "Live", "live": "Live",
    "performance": "Performance", "talk": "Talk", "workshop": "Workshop",
    "screening": "Screening",
}


def mins(hhmm: str) -> int:
    """Minutes past midnight, with the small hours belonging to the night
    before — 01:30 is 25:30, so a set that runs past midnight still sorts and
    draws after the one before it."""
    h, m = int(hhmm[:2]), int(hhmm[3:])
    return (h + 24 if h < 6 else h) * 60 + m


def title_case(genre: str) -> str:
    return " ".join(w.capitalize() for w in genre.replace("-", " ").split())


# ── festivals ─────────────────────────────────────────
class Festival:
    """One planner's worth of data, in the shape the component wants."""

    def __init__(self, fid: str, out: str, record: str, data: pathlib.Path,
                 basemap: pathlib.Path, images: dict):
        self.fid, self.out, self.data = fid, out, data
        self.f = schema.festival(record)
        self.acts = json.loads((data / "acts.json").read_text())
        self.basemap = json.loads(basemap.read_text())
        self.images = images

    # -- days ------------------------------------------
    @property
    def days(self) -> list[dict]:
        if "days" in self.acts:
            return [{"id": d["id"], "label": d["label"], "short": d["short"],
                     "date": d["date"], "start": d["start"], "end": d["end"]}
                    for d in self.acts["days"]]
        # A one-day festival still has a day: the event record carries it, and
        # the window comes from the hours the organiser publishes.
        ev = self.acts["event"]
        start, end = (ev.get("hours") or "12:00-22:00").split("-")
        y, m, d = ev["date"].split("-")
        import datetime
        dt = datetime.date(int(y), int(m), int(d))
        return [{"id": "d1", "label": dt.strftime("%a %-d %b"),
                 "short": dt.strftime("%a"), "date": ev["date"],
                 "start": mins(start.strip()), "end": mins(end.strip())}]

    # -- stages ----------------------------------------
    @property
    def stages(self) -> list[dict]:
        out = []
        for s in self.acts["stages"]:
            acts = s.get("acts", [])
            if not acts:
                continue
            cats = [CAT_OF_TYPE.get(a["type"], "music") for a in acts]
            out.append({
                "n": len(out) + 1,
                "name": s["name"],
                "cat": max(set(cats), key=cats.count),
                "lat": s["lat"], "lng": s["lon"],
                "note": s.get("blurb") or s.get("location") or "",
            })
        return out

    # -- sets ------------------------------------------
    @property
    def events(self) -> list[dict]:
        days = {d["id"] for d in self.days}
        one = self.days[0]["id"]
        out, i = [], 0
        for si, s in enumerate(x for x in self.acts["stages"] if x.get("acts")):
            for a in s["acts"]:
                day = a.get("day", one)
                if day not in days:
                    continue
                out.append({
                    "id": "e%d" % i, "s": si, "d": day,
                    "from": a["s"], "to": a["e"],
                    "title": a.get("display") or a["n"],
                    "cat": CAT_OF_TYPE.get(a["type"], "music"),
                    "type": TYPE_LABEL.get(a["type"], "Live"),
                    "genres": [title_case(g) for g in a.get("genres", [])],
                    "mark": "",
                    "a": mins(a["s"]), "b": mins(a["e"]),
                })
                i += 1
        return out

    # -- the copy under the title ----------------------
    @property
    def hours_line(self) -> str:
        ds = self.days
        lo, hi = min(d["start"] for d in ds), max(d["end"] for d in ds)
        hm = lambda m: "%02d:%02d" % (m // 60 % 24, m % 60)
        span = "%s–%s" % (hm(lo), hm(hi))
        return ("%s daily · %d %s" % (span, len(ds), "day" if len(ds) == 1 else "days")
                if len(ds) > 1 else span)

    @property
    def facts(self) -> list[str]:
        f = self.f
        return [
            self.hours_line,
            "%s · %s" % (f["city"], f["type"]),
            "Free entry" if f.get("free") else "Ticketed by the festival",
        ]

    @property
    def info_cards(self) -> list[dict]:
        """Four cards, every line of them derived from the festival record —
        the planner states what the organiser states and invents nothing."""
        f = self.f
        st = f["stats"]
        return [
            {"eyebrow": "When", "title": f["dates"],
             "body": "%s. %d %s across %d stages." % (
                 self.hours_line, st["acts"],
                 "act" if st["acts"] == 1 else "acts", st["stages"])},
            {"eyebrow": "Where", "title": f["city"],
             "body": f["description"]},
            {"eyebrow": "Tickets",
             "title": "Free entry" if f.get("free") else "Sold by the festival",
             "body": ("No ticket, no wristband — the streets are the venue."
                      if f.get("free") else
                      "Tickets and wristbands are the festival's own; this "
                      "planner sells nothing and links to their site.")},
            {"eyebrow": "This planner", "title": "Unofficial, and offline",
             "body": "Transcribed from the organiser's published schedule and "
                     "not affiliated with the festival. Once it has loaded it "
                     "needs no signal, and your picks stay on this device."},
        ]


FESTIVALS = {
    "kallio": Festival("kallio", "kallio", "kbp", ROOT / "data",
                       ROOT / "data" / "basemap.json",
                       {"street": "assets/basemap-light.jpg",
                        "satellite": "assets/satellite.jpg"}),
    "flow": Festival("flow", "flow", "flow", ROOT / "data" / "flow",
                     ROOT / "data" / "flow" / "basemap.json",
                     {"street": "assets/flow-basemap-light.jpg",
                      "satellite": "assets/flow-satellite.jpg"}),
}


def js(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def data_uri(path: pathlib.Path) -> str:
    import base64
    mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png"}[
        path.suffix.lstrip(".").lower()]
    return "data:%s;base64,%s" % (mime, base64.b64encode(path.read_bytes()).decode())


# ── the substitutions ─────────────────────────────────
def patch_script(src: str, fest: Festival) -> str:
    days, stages, events = fest.days, fest.stages, fest.events
    first = days[0]["id"]

    src = sub_once(src, r"  STAGES = \[.*?\n  \];",
                   "  STAGES = %s;" % js(stages), "STAGES")

    src = sub_once(src, r"  EVENTS = \[.*?\n  \}\)\);",
                   "  EVENTS = %s;" % js(events), "EVENTS")

    # One window per day, read off the day the reader is on. The design had a
    # single pair of constants because it drew a single day.
    src = sub_once(
        src,
        r"  DAY_START = \d+;\n  DAY_END = \d+;\n  NOW = [^;]+;",
        "  DAYS = %s;\n"
        "  get DAY_WINDOW() { return this.DAYS.find(d => d.id === this.state.day) || this.DAYS[0]; }\n"
        "  get DAY_START() { return this.DAY_WINDOW.start; }\n"
        "  get DAY_END() { return this.DAY_WINDOW.end; }\n"
        "  /* The now-line is the clock, and only on a day the festival is on;\n"
        "     off-festival it sits at the start rather than pretending. */\n"
        "  get NOW() {\n"
        "    const d = new Date(), m = d.getHours() * 60 + d.getMinutes();\n"
        "    const today = this.DAYS.find(x => x.date === d.toISOString().slice(0, 10));\n"
        "    return today && today.id === this.state.day\n"
        "      ? Math.max(this.DAY_START, Math.min(this.DAY_END, m < 360 ? m + 1440 : m))\n"
        "      : this.DAY_START;\n"
        "  }" % js([dict(d, date=d.get("date", "")) for d in days]),
        "day window")

    # The programme is one day at a time now.
    src = sub_once(src, r"    return this\.EVENTS\.filter\(e =>\n      S\.cats",
                   "    return this.EVENTS.filter(e =>\n      e.d === S.day &&\n      S.cats",
                   "day filter")

    src = sub_once(src, r"const days = \[\{ id: 'fri'.*?\}\]\.map",
                   "const days = this.DAYS.map(d => ({ id: d.id, label: d.label, short: d.short })).map",
                   "day tabs")

    src = sub_once(src, r"const dayEmpty = S\.day !== 'sat';",
                   "const dayEmpty = !this.EVENTS.some(e => e.d === S.day);",
                   "empty day")

    src = sub_once(src, r"emptyDayTitle: \([^)]*\) \+ ' is not published yet'",
                   "emptyDayTitle: (this.DAY_WINDOW.label) + ' is not published yet'",
                   "empty day title")

    src = sub_once(src, r"      infoCards: \[.*?\n      \],",
                   "      infoCards: %s," % js(fest.info_cards), "info cards")

    # Day labels that were written into strings.
    src = sub_once(src, r"'Flow Festival 2026 · Sat 15 August\\n'",
                   "(%s + ' · ' + this.DAY_WINDOW.label + '\\n')"
                   % js(fest.f["name"] + " " + fest.f["year"]), "clipboard header")
    src = sub_once(src, r"' minutes · Sat 15 August'",
                   "' minutes · ' + this.DAY_WINDOW.label", "sheet time line")
    src = sub_once(src, r"' acts on Saturday</span>'",
                   "' acts on ' + this.DAY_WINDOW.short + '<\\/span>'", "map popup")

    # The design wrote its one day's name into six more strings.
    day_short = "this.DAY_WINDOW.short"
    day_label = "this.DAY_WINDOW.label"
    src = sub_once(src, r"count: n \+ ' acts on Saturday'",
                   "count: n + ' acts on ' + %s" % day_short, "stage card count")
    src = sub_once(src, r"'Nothing on Saturday matches every filter at once\. ",
                   "'Nothing on ' + %s + ' matches every filter at once. ' + '" % day_short,
                   "no-match copy")
    src = sub_once(src, r"'Your Flow weekend'",
                   js("Your " + fest.f["name"]), "plan heading")
    src = sub_once(src, r"'Your Saturday schedule'",
                   "'Your ' + %s + ' schedule'" % day_short, "picks heading")
    src = sub_once(src, r"'Saturday, act by act'",
                   "%s + ', act by act'" % day_label, "list heading")
    src = sub_once(src, r"'Nothing starred for Saturday yet'",
                   "'Nothing starred for ' + %s + ' yet'" % day_short, "empty stars")

    # The day the planner opens on: the one being held today, else the first.
    src = sub_once(src, r"day: 'sat',",
                   "day: (function (D) { const t = new Date().toISOString().slice(0, 10);\n"
                   "      return (D.find(d => d.date === t) || D[0]).id; })(%s),"
                   % js([{"id": d["id"], "date": d.get("date", "")} for d in days]),
                   "opening day")

    return patch_stage_colours(patch_weather(patch_map(src, fest), fest), fest)


# ── one colour per stage ──────────────────────────────
# The design colours a set by what kind of thing it is — music, performance,
# film — which is three colours for ten stages, so a glance at the grid says
# nothing about where you are. Each stage gets its own tonal palette instead,
# and every drawing of a set takes its colour from the stage it is on: the
# column head, the cell, the row number, the map pin and the sheet.
#
# The palettes are M3's own construction, not a hand-picked set: one hue per
# stage, evenly spaced around the wheel from the design's green, read off at
# the five tones the design's own category palettes use — container 90,
# on-container 16, a 79 for the pin, and the 28/95 pair the plan state takes.
def stage_palette(n: int) -> list[dict]:
    import m3color
    step = 360.0 / max(n, 1)
    out = []
    for i in range(n):
        h = (124 + i * step) % 360
        out.append({
            "bg": m3color.tone(h, 21, 90),
            "fg": m3color.tone(h, 23, 16),
            "dot": m3color.tone(h, 39, 79),
            "planBg": m3color.tone(h, 36, 28),
            "planFg": m3color.tone(h, 15, 95),
        })
    return out


def patch_stage_colours(src: str, fest: Festival) -> str:
    pal = stage_palette(len(fest.stages))
    src = sub_once(
        src, r"  CAT = \{",
        "  STAGE_PALETTE = %s;\n"
        "  /* The colour of everything that belongs to a stage. */\n"
        "  stageColor(i) { return this.STAGE_PALETTE[i %% this.STAGE_PALETTE.length]; }\n\n"
        "  CAT = {" % js(pal),
        "stage palette")

    for old, new, what in [
        (r"next\.burstColor = this\.CAT\[ev\.cat\]\.planBg;",
         "next.burstColor = this.stageColor(ev.s).planBg;", "burst colour"),
        (r"const st = this\.STAGES\[i\], c = this\.CAT\[st\.cat\];",
         "const st = this.STAGES[i], c = this.stageColor(i);", "stage card"),
        (r"      const c = this\.CAT\[st\.cat\];",
         "      const c = this.stageColor(i);", "map pin"),
        (r"const c = C\[ev\.cat\], dur = ev\.b - ev\.a,",
         "const c = this.stageColor(ev.s), dur = ev.b - ev.a,", "timetable cell"),
        (r"const c = C\[ev\.cat\], A = this\.ART\[ev\.cat\], st = this\.STAGES\[ev\.s\];",
         "const c = this.stageColor(ev.s), A = this.ART[ev.cat], st = this.STAGES[ev.s];",
         "list row"),
        (r"const c = C\[sev\.cat\], A = this\.ART\[sev\.cat\], st = this\.STAGES\[sev\.s\];",
         "const c = this.stageColor(sev.s), A = this.ART[sev.cat], st = this.STAGES[sev.s];",
         "detail sheet"),
        (r"background: C\[st\.cat\]\.bg, color: C\[st\.cat\]\.fg",
         "background: this.stageColor(i).bg, color: this.stageColor(i).fg",
         "column head number"),
    ]:
        src = sub_once(src, old, new, what)
    return src


# ── weather ───────────────────────────────────────────
# Open-Meteo: no key, no account, CORS open, free for non-commercial use, and
# it answers for a point. The forecast is asked for the festival's own
# coordinates and the day the reader is on — never for the reader's location,
# which this site does not ask for and does not want.
WEATHER_JS = """
  /* ── weather ──────────────────────────────────────
     Fetched from Open-Meteo for the festival's own coordinates, for whichever
     day is on screen, and only ever for that: nothing here reads where the
     reader is. A forecast this far out is worth little, so the card simply
     does not appear until the API answers — with no signal, or outside the
     sixteen days it forecasts, the header keeps its own counsel rather than
     showing numbers nobody stands behind. */
  WEATHER = __WEATHER__;

  WX_ICON(code, hour) {
    const night = hour < 5 || hour >= 22;
    if (code === 0) return night ? '#wi-clear-night' : '#wi-clear';
    if (code === 1 || code === 2) return night ? '#wi-partly-night' : '#wi-partly';
    if (code === 3 || code === 45 || code === 48) return '#wi-overcast';
    if (code >= 61 && code <= 67) return '#wi-rain';
    if (code >= 95) return '#wi-rain';
    if (code >= 71 && code <= 86) return '#wi-showers';
    if (code >= 51 && code <= 57) return '#wi-showers';
    if (code >= 80 && code <= 82) return '#wi-showers';
    return '#wi-cloudy';
  }

  WX_WORD(code) {
    if (code === 0) return 'Clear';
    if (code === 1) return 'Mainly clear';
    if (code === 2) return 'Partly cloudy';
    if (code === 3) return 'Overcast';
    if (code === 45 || code === 48) return 'Fog';
    if (code >= 51 && code <= 57) return 'Drizzle';
    if (code >= 61 && code <= 67) return 'Rain';
    if (code >= 71 && code <= 77) return 'Snow';
    if (code >= 80 && code <= 82) return 'Showers';
    if (code >= 85 && code <= 86) return 'Snow showers';
    if (code >= 95) return 'Thunderstorm';
    return 'Cloudy';
  }

  loadWeather() {
    const w = this.WEATHER, day = this.DAY_WINDOW;
    if (!day || !day.date || this.wxAsked === day.date) return;
    this.wxAsked = day.date;
    /* The hours the festival is open, three apart — as timestamps rather than
       as an hour range, because a day that ends at 01:00 ends on the next
       date and an hour-range test can never match both ends of it. */
    const stamp = (m) => {
      const d = new Date(day.date + 'T12:00:00Z');
      d.setUTCDate(d.getUTCDate() + Math.floor(m / 1440));
      return d.toISOString().slice(0, 10) + 'T'
        + String(Math.floor(m / 60) % 24).padStart(2, '0') + ':00';
    };
    const wanted = [];
    for (let m = day.start; m <= day.end && wanted.length < 5; m += 180) wanted.push(stamp(m));
    const last = stamp(day.end);
    const url = 'https://api.open-meteo.com/v1/forecast'
      + '?latitude=' + w.lat + '&longitude=' + w.lon
      + '&hourly=temperature_2m,weather_code,precipitation_probability'
      + '&timezone=' + encodeURIComponent(w.tz)
      + '&start_date=' + day.date + '&end_date=' + last.slice(0, 10);
    fetch(url).then(r => (r.ok ? r.json() : null)).then(j => {
      const h = j && j.hourly;
      if (!h || !h.time || !h.time.length) { this.setState({ wx: null }); return; }
      const rows = [];
      for (const t of wanted) {
        const i = h.time.indexOf(t);
        if (i < 0 || h.temperature_2m[i] == null) continue;
        const hr = Number(t.slice(11, 13));
        rows.push({
          time: String(hr).padStart(2, '0') + ':00',
          icon: this.WX_ICON(h.weather_code[i], hr),
          temp: Math.round(h.temperature_2m[i]) + '°',
          rain: Math.max(0, Math.min(100, Number(h.precipitation_probability[i]) || 0))
        });
      }
      if (!rows.length) { this.setState({ wx: null }); return; }
      /* The reading the header shows is the middle of the festival day. */
      const i0 = Math.max(0, h.time.indexOf(wanted[Math.floor(wanted.length / 2)]));
      this.setState({ wx: {
        rows: rows,
        temp: Math.round(h.temperature_2m[i0]) + '°',
        word: this.WX_WORD(h.weather_code[i0]),
        icon: this.WX_ICON(h.weather_code[i0], Number(h.time[i0].slice(11, 13))),
        credit: 'Forecast: Open-Meteo'
      } });
    }).catch(() => this.setState({ wx: null }));
  }
"""


def patch_weather(src: str, fest: Festival) -> str:
    stages = fest.stages
    lat = round(sum(s["lat"] for s in stages) / len(stages), 4)
    lon = round(sum(s["lng"] for s in stages) / len(stages), 4)
    block = (WEATHER_JS + WEATHER_NOTE_JS).replace(
        "__WEATHER__", js({"lat": lat, "lon": lon, "tz": "Europe/Helsinki"}))

    # The component gains the weather methods, and asks for the forecast when it
    # mounts and whenever the day changes.
    src = sub_once(src, r"  componentDidMount\(\) \{",
                   block + "\n  componentDidMount() {\n    this.loadWeather();",
                   "weather methods")
    src = sub_once(src, r"  componentDidUpdate\(\) \{",
                   "  componentDidUpdate() {\n    this.loadWeather();",
                   "weather refresh")

    # The card is drawn from the answer, and only when there is one.
    src = sub_once(
        src,
        r"      forecast: \[\n        \{ time: '15:00'.*?\n      \]\.map\(\(f, i\) => \(\{",
        "      forecast: ((S.wx && S.wx.rows) || []).map((f, i) => ({",
        "forecast rows")
    src = sub_once(src, r"barStyle: \{ position: 'absolute', top: 0, bottom: 0, left: f\.from \+ '%', width: \(f\.to - f\.from\) \+ '%'",
                   "barStyle: { position: 'absolute', top: 0, bottom: 0, left: '0%', width: f.rain + '%'",
                   "forecast bar")

    for old, new, what in [
        (r"this\.props\.showWeather !== false && S\.weatherOpen === true;",
         "this.props.showWeather !== false && !!S.wx && S.weatherOpen === true;", "weather shown"),
        (r"showWeather: this\.props\.showWeather !== false && S\.weatherOpen === true,",
         "showWeather: this.props.showWeather !== false && !!S.wx && S.weatherOpen === true,", "weather prop"),
        (r"showWeatherBrief: this\.props\.showWeather !== false,",
         "showWeatherBrief: this.props.showWeather !== false && !!S.wx,", "weather brief"),
        (r"weatherToggleLabel: S\.weatherOpen === true \? 'Hide the weather' : 'Weather: 21°, overcast',",
         "weatherToggleLabel: S.weatherOpen === true ? 'Hide the weather'\n"
         "        : ('Weather: ' + (S.wx ? S.wx.temp + ', ' + S.wx.word.toLowerCase() : 'not available')),",
         "weather label"),
    ]:
        src = sub_once(src, old, new, what)

    # The three values the header and the card show, published for the template.
    src = sub_once(src, r"      showWeatherWord: !narrow,",
                   "      showWeatherWord: !narrow,\n"
                   "      wxTemp: S.wx ? S.wx.temp : '',\n"
                   "      wxWord: S.wx ? S.wx.word : '',\n"
                   "      wxIcon: S.wx ? S.wx.icon : '#wi-cloudy',\n"
                   "      wxNote: this.wxNote(),",
                   "weather values")
    return src


WEATHER_NOTE_JS = """
  /* One sentence about the day, and where the numbers came from. Said only
     when the forecast supports it — no rain, no rain sentence. */
  wxNote() {
    const wx = this.state.wx;
    if (!wx) return '';
    const wet = wx.rows.reduce((a, r) => (r.rain > a.rain ? r : a), wx.rows[0]);
    return (wet.rain >= 40
      ? 'Rain likely around ' + wet.time + ' — ' + wet.rain + '% at its highest. '
      : (wet.rain >= 15 ? 'A ' + wet.rain + '% chance of rain at its highest. '
                        : 'Little rain in the forecast. '))
      + 'Forecast from Open-Meteo, for the festival site.';
  }
"""


def patch_map(src: str, fest: Festival) -> str:
    b = fest.basemap["bounds"]
    bounds = [[b["s"], b["w"]], [b["n"], b["e"]]]
    centre = [(b["s"] + b["n"]) / 2, (b["w"] + b["e"]) / 2]
    attr = fest.basemap.get("attribution", "(c) OpenStreetMap contributors (c) CARTO")

    src = sub_once(src, r"\.setView\(\[[\d.]+, [\d.]+\], 16\)",
                   ".setView(%s, 16)" % js(centre), "map centre")

    src = sub_once(
        src,
        r"    this\.layers = \{\n      street: L\.tileLayer\(.*?\n    \};",
        """    /* The basemap ships with the page as one stitched image, placed by the
       Web Mercator bounds it was cut to, so the map draws with no signal —
       which is the point of a planner you open in a field. Where there IS a
       signal the real slippy layers take over, and then you can pan past the
       festival; the probe below is what decides, and it costs one tile. */
    const BOUNDS = %s;
    const still = (url, credit) => L.layerGroup(
      [L.imageOverlay(url, BOUNDS, { attribution: credit })]);
    this.layers = {
      street: still(this.BASE_STREET, %s),
      satellite: still(this.BASE_SATELLITE, 'Imagery &copy; Esri')
    };
    map.setMaxBounds(L.latLngBounds(BOUNDS).pad(0.25));
    const live = {
      street: () => L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png',
        { subdomains: 'abcd', maxZoom: 20, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &middot; &copy; <a href="https://carto.com/attributions">CARTO<\\/a>' }),
      satellite: () => L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
        { maxZoom: 19, attribution: 'Imagery &copy; Esri' })
    };
    const probe = new Image();
    probe.onload = () => {
      if (!this.map) return;
      map.setMaxBounds(null);
      Object.keys(this.layers).forEach(k => {
        this.layers[k].clearLayers();
        this.layers[k].addLayer(live[k]());
      });
    };
    probe.referrerPolicy = 'no-referrer';
    probe.src = 'https://a.basemaps.cartocdn.com/light_all/0/0/0.png';""" % (
            js(bounds), js(attr)),
        "map layers")
    return src


def patch_template(tpl: str, fest: Festival) -> str:
    f = fest.f
    name = "%s %s" % (f["name"], f["year"])
    tpl = sub_once(tpl, r'(<h1 style="[^"]*">)Flow Festival 2026</h1>',
                   r"\g<0>", "title", flags=re.S) if False else tpl
    tpl = sub_once(tpl, r">Flow Festival 2026</h1>",
                   ">%s</h1>" % name, "hero title")
    tpl = sub_once(tpl, r">14–16 August 2026<", ">%s<" % f["dates"], "hero dates")
    tpl = sub_once(tpl, r">Gates 15:00, music until 01:00<",
                   ">%s<" % fest.facts[0], "hero fact 1")
    tpl = sub_once(tpl, r">Suvilahti, Sörnäinen · Metro to Kalasatama<",
                   ">%s<" % fest.facts[1], "hero fact 2")
    tpl = sub_once(tpl, r">Day ticket €99 · 3-day pass €249<",
                   ">%s<" % fest.facts[2], "hero fact 3")
    tpl = sub_once(tpl, r">Ten stages in a former power plant by the sea\.<",
                   ">%s<" % f["description"], "hero description")

    # The three chips under the copy, and the two links beside them.
    tags = (f.get("tags") or [])[:3]
    for old, new in zip(("Outdoors", "3-day pass", "18+ after 22:00"), tags):
        tpl = sub_once(tpl, r">%s<" % re.escape(old), ">%s<" % new, "hero tag " + old)
    tpl = sub_once(tpl, r'href="#official-site"', 'href="%s"' % f["official"],
                   "official link")
    if f.get("tickets"):
        tpl = sub_once(tpl, r'href="#tickets"', 'href="%s" target="_blank" '
                       'rel="noopener noreferrer"' % f["tickets"], "ticket link")
    else:
        # Nothing to sell: the button would be a link to nowhere.
        tpl = sub_once(tpl, r'<a href="#tickets".*?</a>', "", "ticket button")

    tpl = sub_once(tpl, r">Suvilahti · illustrative<",
                   ">%s · illustrative<" % f["city"].split(",")[0], "artwork label")

    # ---- weather: the sample reading becomes the fetched one ----
    for _ in range(2):
        tpl = sub_once(tpl, r">21°<", ">{{ wxTemp }}<", "weather temperature")
        tpl = sub_once(tpl, r">Overcast<", ">{{ wxWord }}<", "weather word")
        tpl = sub_once(tpl, r'<use href="#wi-overcast"></use>',
                       '<use href="{{ wxIcon }}"></use>', "weather icon")
    tpl = sub_once(tpl, r">Rain likely 18:00–20:00\. The yards are unsheltered\.<",
                   ">{{ wxNote }}<", "weather note")

    # The chip above the timetable already says which mode this is; the
    # heading and the sentence under it said it twice more.
    tpl = sub_once(
        tpl,
        r'<h2 style="margin:0;font-size:22px;font-weight:600;line-height:28px;'
        r'letter-spacing:-\.014em">\{\{ rowsHeading \}\}</h2>\s*'
        r'<p style="margin:0;font-size:14px;line-height:20px;letter-spacing:'
        r'\.016em;color:var\(--on-var,#494E42\)">\{\{ tableSub \}\}</p>',
        "", "picks heading")

    # The design drew a night sky: its six icons have no sun in them, because
    # its sample forecast never needed one. A real forecast does.
    tpl = sub_once(
        tpl, r'(<symbol id="wi-cloudy")',
        '<symbol id="wi-clear" sc-camel-view-box="0 0 48 48">'
        '<circle cx="24" cy="24" r="8"></circle>'
        '<path d="M24 6v4M24 38v4M6 24h4M38 24h4'
        'M11.3 11.3l2.9 2.9M33.8 33.8l2.9 2.9M36.7 11.3l-2.9 2.9M14.2 33.8l-2.9 2.9">'
        '</path></symbol>'
        '<symbol id="wi-partly" sc-camel-view-box="0 0 48 48">'
        '<circle cx="30" cy="17" r="6"></circle>'
        '<path d="M30 5v3M30 26v3M18 17h3M39 17h3M22.2 9.2l2.1 2.1M35.7 22.7l2.1 2.1">'
        '</path><circle cx="19" cy="30" r="9"></circle>'
        '<circle cx="30" cy="33.5" r="6.5"></circle></symbol>'
        r"\1", "daytime icons", flags=0)
    return tpl
    tpl = sub_once(tpl, r">Five stages inside the Suvilahti yards\..*?<",
                   ">%d stages across %s. Pins sit on the organiser's own map "
                   "marks — tap one to see what is on.<"
                   % (len(fest.stages), f["city"].split(",")[0]), "map blurb")
    return tpl


# ── the page ──────────────────────────────────────────
def build(fid: str) -> pathlib.Path:
    fest = FESTIVALS[fid]
    art = art_mod.Artifact()
    f = fest.f

    script = patch_script(art.js, fest)
    template = art.resolve(patch_template(art.template, fest))

    # The two basemaps travel with the page, as the old planners' did.
    script = ("  BASE_STREET = %s;\n  BASE_SATELLITE = %s;\n" % (
        js(data_uri(ROOT / fest.images["street"])),
        js(data_uri(ROOT / fest.images["satellite"]))
    )).join(script.split("  STAGES = ", 1)[0:1] + ["  STAGES = " + script.split("  STAGES = ", 1)[1]])

    props = json.loads(art.props)
    # The weather is real now — fetched for the festival's own coordinates — so
    # the control stays on. It shows nothing until the forecast answers.
    props["showWeather"]["default"] = True
    props_attr = json.dumps(props, ensure_ascii=False).replace('"', "&quot;")

    title = "%s %s timetable — set times, stages and a map" % (f["name"], f["year"])
    desc = ("%s Set times for all %d acts on %d stages, filters by stage, type "
            "and genre, a stage map, and your own plan. Works offline."
            % (f["description"], f["stats"]["acts"], f["stats"]["stages"]))
    og = seo.head(
        f"{seo.BASE}/{f['planner']}",
        title,
        desc,
        f"{seo.BASE}/assets/og/{fid}.jpg",
        kind="article",
        jsonld=[seo.festival_event(f), seo.faq(f), seo.breadcrumb(f)],
    )

    page = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<!-- Two departures from the policy the rest of the site runs under, both
     forced by the design's runtime and both scoped to the planners.

     'unsafe-eval': the dc-runtime compiles the component from source at load,
     so the class arrives as a string and is evaluated. Nothing on this page
     takes input from anywhere — no query is read, no message is accepted, no
     third-party script is loaded — so the string it evaluates is the one that
     shipped with it.

     The two tile hosts: the basemap travels with the page as an image, and
     these are asked for only if a probe finds a signal.

     api.open-meteo.com: the forecast, asked for the festival's coordinates —
     never the reader's, which this page does not ask for. -->
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'self' 'unsafe-inline' 'unsafe-eval'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https://*.basemaps.cartocdn.com https://server.arcgisonline.com; font-src data:; connect-src 'self' https://api.open-meteo.com; manifest-src 'self'; worker-src 'self'; base-uri 'none'; form-action 'none'">
<meta name="referrer" content="strict-origin-when-cross-origin">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#f5f5f5">
<link rel="manifest" href="../manifest.webmanifest">
<link rel="apple-touch-icon" href="../assets/icons/apple-touch-icon.png">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="Flanner">
<meta name="mobile-web-app-capable" content="yes">
<title>{title}</title>
<meta name="description" content="{desc}">
{og}
<style>
{art.font_css()}
{art.other_css()}
</style>
<script>/* react */
{inline_js(art.libs['react'])}
</script>
<script>/* react-dom */
{inline_js(art.libs['react-dom'])}
</script>
<script>/* leaflet */
{inline_js(art.libs['leaflet'])}
</script>
<script>/* dc-runtime */
{inline_js(art.libs['dc-runtime'])}
</script>
</head>
<body>
<x-dc>
{template}
</x-dc>
<script type="text/x-dc" data-dc-script="" data-props="{props_attr}">
{script}
</script>
</body>
</html>
"""
    out = ROOT / fest.out / "index.html"
    out.parent.mkdir(exist_ok=True)
    out.write_text(page)
    print(f"  {out.relative_to(ROOT)} · {len(fest.stages)} stages · "
          f"{len(fest.events)} sets · {len(fest.days)} day(s) · {len(page) // 1024} KB")
    return out


if __name__ == "__main__":
    which = sys.argv[1:] or list(FESTIVALS)
    print(ROOT)
    for fid in which:
        build(fid)
