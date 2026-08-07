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


# ── what can actually be played ───────────────────────
# A link is not a player. Spotify will embed an artist, an album or a track
# from its own URL, so those play. YouTube will only embed a video, and every
# YouTube link in this data is a channel — `youtube.com/@handle` — which has no
# video id in it and cannot be resolved to one without asking YouTube. Those
# stay what they are: a link to the act's channel, in the row of links.
SPOTIFY = re.compile(r"open\.spotify\.com/(?:intl-[a-z]+/)?(artist|album|track|episode)/([A-Za-z0-9]+)")
YOUTUBE = re.compile(r"(?:youtube\.com/(?:watch\?v=|embed/|shorts/)|youtu\.be/)([A-Za-z0-9_-]{11})")


def playable(links: dict) -> dict:
    out = {}
    m = YOUTUBE.search(links.get("youtube", "") or "")
    if m:
        out["youtube"] = m.group(1)
    m = SPOTIFY.search(links.get("spotify", "") or "")
    if m:
        out["spotify"] = "%s/%s" % (m.group(1), m.group(2))
    return out


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
        # `n` is the day of the month, which is what the day chips print beside
        # the weekday — "Sat 15" — in whichever language the drawer is set to.
        if "days" in self.acts:
            return [{"id": d["id"], "label": d["label"], "short": d["short"],
                     "date": d["date"], "n": int(d["date"][8:10]),
                     "start": d["start"], "end": d["end"]}
                    for d in self.acts["days"]]
        # A one-day festival still has a day: the event record carries it, and
        # the window comes from the hours the organiser publishes.
        ev = self.acts["event"]
        start, end = (ev.get("hours") or "12:00-22:00").split("-")
        y, m, d = ev["date"].split("-")
        import datetime
        dt = datetime.date(int(y), int(m), int(d))
        return [{"id": "d1", "label": dt.strftime("%a %-d %b"),
                 "short": dt.strftime("%a"), "date": ev["date"], "n": dt.day,
                 "start": mins(start.strip()), "end": mins(end.strip())}]

    # -- the day names, in each language the drawer offers ----
    # The design ships a language picker that renames the day chips. Ours has
    # the same three languages and the same job; the names are read off the
    # festival's own dates rather than written out for one sample weekend.
    WEEKDAYS = {
        "en": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
        "fi": ["Ma", "Ti", "Ke", "To", "Pe", "La", "Su"],
        "sv": ["Mån", "Tis", "Ons", "Tors", "Fre", "Lör", "Sön"],
    }

    @property
    def langs(self) -> list[dict]:
        import datetime
        wd = [datetime.date(*map(int, d["date"].split("-"))).weekday()
              for d in self.days]
        return [
            {"id": "en", "label": "English", "sub": "EN",
             "days": [self.WEEKDAYS["en"][i] for i in wd]},
            {"id": "fi", "label": "Suomi", "sub": "FI",
             "days": [self.WEEKDAYS["fi"][i] for i in wd]},
            {"id": "sv", "label": "Svenska", "sub": "SV",
             "days": [self.WEEKDAYS["sv"][i] for i in wd]},
        ]

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
                # Where it actually is, in the organiser's own words — the
                # street or the corner, which is what a map app is given and
                # what someone standing in the festival reads.
                "where": s.get("location") or "",
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
                ev = {
                    "id": "e%d" % i, "s": si, "d": day,
                    "from": a["s"], "to": a["e"],
                    "title": a.get("display") or a["n"],
                    "cat": CAT_OF_TYPE.get(a["type"], "music"),
                    "type": TYPE_LABEL.get(a["type"], "Live"),
                    "genres": [title_case(g) for g in a.get("genres", [])],
                    "mark": "",
                    "a": mins(a["s"]), "b": mins(a["e"]),
                }
                # The sheet has a paragraph and four link buttons; the record
                # has the organiser's own introduction and the act's own
                # profiles. Emitted only where the act has them, so a set with
                # nothing written about it keeps the design's own fallbacks.
                if a.get("note"):
                    ev["bio"] = a["note"]
                links = {k: v for k, v in (a.get("links") or {}).items() if v}
                if links:
                    ev["links"] = links
                media = playable(links)
                if media:
                    ev["media"] = media
                out.append(ev)
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


def _aspect(path: pathlib.Path) -> float:
    """How wide a mark is for its height — a wordmark strip or a round one."""
    if path.suffix.lower() == ".svg":
        m = re.search(r'viewBox="([\d.\-]+) ([\d.\-]+) ([\d.]+) ([\d.]+)"',
                      path.read_text())
        return float(m.group(3)) / float(m.group(4)) if m else 1.0
    if path.suffix.lower() == ".png":
        b = path.read_bytes()
        w = int.from_bytes(b[16:20], "big")
        h = int.from_bytes(b[20:24], "big")
        return w / h if h else 1.0
    return 1.0


def data_uri(path: pathlib.Path) -> str:
    import base64
    mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
            "svg": "image/svg+xml"}[path.suffix.lstrip(".").lower()]
    return "data:%s;base64,%s" % (mime, base64.b64encode(path.read_bytes()).decode())


# ── the substitutions ─────────────────────────────────
def patch_script(src: str, fest: Festival) -> str:
    days, stages, events = fest.days, fest.stages, fest.events
    f = fest.f
    first = days[0]["id"]

    src = sub_once(src, r"  STAGES = \[.*?\n  \];",
                   "  STAGES = %s;" % js(stages), "STAGES")

    src = sub_once(src, r"  EVENTS = \[.*?\n  \}\)\);",
                   "  EVENTS = %s;" % js(events), "EVENTS")

    # One window per day, read off the day the reader is on. The design had a
    # single pair of constants because it drew a single day. The pair and the
    # now-line sit either side of the design's own tables, so they are replaced
    # where each of them stands rather than as one block.
    src = sub_once(
        src,
        r"  DAY_START = \d+;\n  DAY_END = \d+;",
        "  DAYS = %s;\n"
        "  get DAY_WINDOW() { return this.DAYS.find(d => d.id === this.state.day) || this.DAYS[0]; }\n"
        "  get DAY_START() { return this.DAY_WINDOW.start; }\n"
        "  get DAY_END() { return this.DAY_WINDOW.end; }"
        % js([dict(d, date=d.get("date", "")) for d in days]),
        "day window")

    src = sub_once(
        src,
        r"  NOW = [^;]+;",
        "  /* The now-line is the clock, and only on a day the festival is on;\n"
        "     off-festival it sits at the start rather than pretending. */\n"
        "  get NOW() {\n"
        "    const d = new Date(), m = d.getHours() * 60 + d.getMinutes();\n"
        "    const today = this.DAYS.find(x => x.date === d.toISOString().slice(0, 10));\n"
        "    return today && today.id === this.state.day\n"
        "      ? Math.max(this.DAY_START, Math.min(this.DAY_END, m < 360 ? m + 1440 : m))\n"
        "      : this.DAY_START;\n"
        "  }\n"
        "  /* The same clock, but it says nothing rather than something safe:\n"
        "     null off the festival, so an act at noon on a Tuesday in March\n"
        "     does not claim to be playing. */\n"
        "  get LIVE_AT() {\n"
        "    const d = new Date(), m = d.getHours() * 60 + d.getMinutes();\n"
        "    const today = this.DAYS.find(x => x.date === d.toISOString().slice(0, 10));\n"
        "    if (!today || today.id !== this.state.day) return null;\n"
        "    return m < 360 ? m + 1440 : m;\n"
        "  }\n"
        "  /* Who the Lineup row shows. The festival names its own headliners\n"
        "     and those come first, in the order it names them. The rest of\n"
        "     the row is the timetable's own answer, the one every festival\n"
        "     poster gives: the act that closes a stage is the act that stage\n"
        "     was built around — one for each stage the headliners have not\n"
        "     already spoken for, in the organiser's stage order, so the row\n"
        "     stands for the whole festival rather than for its main stage.\n"
        "     Anything over six hours is a day-long installation rather than\n"
        "     a set, and is not what closes anything. */\n"
        "  STARS = " + js(f.get("stars") or []) + ";\n"
        "  get LINEUP() {\n"
        "    if (this._lineup) return this._lineup;\n"
        "    const out = [], seen = new Set();\n"
        "    this.STARS.forEach(name => {\n"
        "      const ev = this.EVENTS.find(e => e.title === name);\n"
        "      if (ev && !seen.has(ev.id)) { out.push(ev); seen.add(ev.id); }\n"
        "    });\n"
        "    const stages = new Set(out.map(e => e.s));\n"
        "    const last = new Map();\n"
        "    this.EVENTS.forEach(ev => {\n"
        "      if (ev.b - ev.a > 360 || stages.has(ev.s)) return;\n"
        "      const cur = last.get(ev.s);\n"
        "      if (!cur || ev.a > cur.a) last.set(ev.s, ev);\n"
        "    });\n"
        "    [...last.keys()].sort((x, y) => x - y).forEach(k => out.push(last.get(k)));\n"
        "    this._lineup = out.slice(0, 12);\n"
        "    return this._lineup;\n"
        "  }\n"
        "  /* One bar of the little sound level in the Live chip. */\n"
        "  liveBar(i) {\n"
        "    return {\n"
        "      inlineSize: '2px', blockSize: '9px', borderRadius: '1px',\n"
        "      background: 'currentColor', transformOrigin: '50% 100%',\n"
        "      animation: 'fp-live 1s cubic-bezier(.2,0,0,1) '\n"
        "        + (i * .33).toFixed(2) + 's infinite'\n"
        "    };\n"
        "  }",
        "now line")

    # ---- the two pickers in the drawer ----
    # The language picker keeps its job — it names the day chips — and gets the
    # festival's own days to name.
    src = sub_once(src, r"  LANGS = \[.*?\n  \];",
                   "  LANGS = %s;" % js(fest.langs), "languages")

    # The location picker offered three cities. A planner is one festival in
    # one place, so the list is that place and the row that would ask you to
    # choose between three of them goes.
    src = sub_once(src, r"  PLACES = \[.*?\n  \];",
                   "  PLACES = %s;" % js([{
                       "id": "site", "label": fest.f["city"],
                       "sub": fest.f["city"].split(",")[0],
                       "site": fest.f["city"].split(",")[0]}]), "places")
    src = sub_once(src, r",\n      \{ id: 'place', aria: 'Location'[^\n]*\n    \];",
                   "\n    ];", "location row")
    src = sub_once(src, r"lang: 'en', place: 'helsinki',", "lang: 'en', place: 'site',",
                   "opening place")

    # The programme is one day at a time now.
    src = sub_once(src, r"    return this\.EVENTS\.filter\(e =>\n      S\.cats",
                   "    return this.EVENTS.filter(e =>\n      e.d === S.day &&\n      S.cats",
                   "day filter")

    # …and so are the numbers beside the filters. A design drawing one day
    # could count every set it had; ours would offer "Pop 46" over a day that
    # holds twelve of them.
    src = sub_once(src, r"    this\.EVENTS\.forEach\(e => \{ const f = types\.find",
                   "    this.EVENTS.filter(e => e.d === S.day)"
                   ".forEach(e => { const f = types.find", "type facet counts")
    src = sub_once(src, r"    this\.EVENTS\.forEach\(e => e\.genres\.forEach",
                   "    this.EVENTS.filter(e => e.d === S.day)"
                   ".forEach(e => e.genres.forEach", "genre facet counts")

    # The design's three sample days become ours, and keep the design's own
    # trick of naming them in the language the drawer is set to — the names
    # themselves are read off our dates, one list per language.
    src = sub_once(src, r"const days = \[\{ id: 'fri'.*?\}\)\)\.map",
                   "const days = this.DAYS.map((d, di) => ({ id: d.id, n: d.n,\n"
                   "      label: (dayNames[di] || d.short) + ' ' + d.n,\n"
                   "      short: dayNames[di] || d.short })).map",
                   "day tabs")

    src = sub_once(src, r"const dayEmpty = S\.day !== 'sat';",
                   "const dayEmpty = !this.EVENTS.some(e => e.d === S.day);",
                   "empty day")

    src = sub_once(src, r"emptyDayTitle: \([^)]*\) \+ ' is not published yet'",
                   "emptyDayTitle: (this.DAY_WINDOW.label) + ' is not published yet'",
                   "empty day title")

    # ---- the act sheet's four link buttons ----
    # The design searches each service for the act's name, because a design has
    # no act to link to. Where the record holds the act's own page, the button
    # goes there instead and says so; where it does not, the search stands.
    src = sub_once(
        src,
        r"      const linkDefs = \[\n(?:.*?\n)*?      \];",
        "      const L = sev.links || {};\n"
        "      const linkDefs = [\n"
        "        { id: 'spotify', site: 'Spotify', icon: '#i-spotify', stroked: true,\n"
        "          home: L.spotify, find: 'https://open.spotify.com/search/' + q },\n"
        "        { id: 'youtube', site: 'YouTube', icon: '#i-youtube', stroked: false,\n"
        "          home: L.youtube, find: 'https://www.youtube.com/results?search_query=' + q },\n"
        "        { id: 'soundcloud', site: 'SoundCloud', icon: '#i-soundcloud', stroked: true,\n"
        "          home: L.soundcloud, find: 'https://soundcloud.com/search?q=' + q },\n"
        "        { id: 'instagram', site: 'Instagram', icon: '#i-instagram', stroked: true,\n"
        "          home: L.instagram,\n"
        "          find: 'https://www.instagram.com/explore/search/keyword/?q=' + q }\n"
        "      ].map(l => ({\n"
        "        id: l.id, icon: l.icon, stroked: l.stroked, href: l.home || l.find,\n"
        "        label: (l.home ? sev.title + ' on ' : 'Find ' + sev.title + ' on ') + l.site\n"
        "      }));",
        "act links")

    # ---- the act sheet on a phone ----
    # An introduction the organiser wrote runs to a paragraph, and on a phone
    # that paragraph pushed Navigate and Add to plan — and the bar behind the
    # sheet — off the bottom of the screen. Three lines and a Read more, and
    # the actions ride at the foot of the sheet while the rest of it scrolls,
    # so the two things a reader came to press are always where they can be
    # pressed. The sheet is unchanged on anything wider.
    src = sub_once(
        src,
        r"        intro: sev\.bio \|\| 'An artist introduction arrives with the published programme\.',",
        "        intro: sev.bio || 'An artist introduction arrives with the published programme.',\n"
        "        /* Shown only where there is more than the clip can hold, which\n"
        "           is measured rather than guessed at — see measureBio. */\n"
        "        showBioToggle: !S.bioFits,\n"
        "        bioExpanded: String(!!S.bioOpen),\n"
        "        bioToggleLabel: S.bioOpen ? 'Show less' : 'Read more',\n"
        "        toggleBio: () => this.setState(s => ({ bioOpen: !s.bioOpen })),",
        "sheet introduction")

    # A landscape phone is not "mob" — it is 844px wide — but it has 390px of
    # height, and the sheet has to fit in that just as much. Both the folded
    # introduction and the sheet that scrolls under its own actions key off
    # the height as well as the shell.
    src = sub_once(src, r"    const mob = mode === 'bar';",
                   "    const mob = mode === 'bar';\n"
                   "    const tight = mob || (S.vh || 900) < 720;",
                   "tight viewport")

    # The artwork is a 16:9 band across the top of the sheet, which on a phone
    # held sideways is most of the screen. It gives way: capped where the
    # viewport is short, gone where it is very short, so the act's own details
    # keep the room.
    src = sub_once(
        src,
        r"        mediaStyle: \{ position: 'relative', margin: '12px', aspectRatio: '16 / 9',"
        r" borderRadius: '20px', overflow: 'hidden', background: A\.bg \},",
        "        mediaStyle: Object.assign({\n"
        "          position: 'relative', flex: 'none', margin: '12px', aspectRatio: '16 / 9',\n"
        "          borderRadius: '20px', overflow: 'hidden', background: A.bg\n"
        "        }, (S.vh || 900) < 520 ? { display: 'none' }\n"
        "          : tight ? { maxHeight: 'min(30dvh, 190px)' } : null),",
        "sheet media")

    # ---- the day row on a phone ----
    # The phone layout writes its own day chips, and writes the design's three
    # sample days into them by hand — so a one-day festival was offered "Fri
    # 14", and the pill that slides between them was a third of the row wide
    # wherever it was standing. Both come off the festival's own days now.
    src = sub_once(src, r"        label: narrow \? d\.short : d\.label, pressed: String\(on\),",
                   "        label: narrow ? d.short : d.label, full: d.label, pressed: String(on),",
                   "day chip full label")
    src = sub_once(src, r"          label: \['Fri 14', 'Sat 15', 'Sun 16'\]\[i\], pressed: d\.pressed,",
                   "          label: d.full || d.label, pressed: d.pressed,", "phone day labels")
    src = sub_once(src, r"    const dayIdx = Math\.max\(0, \['fri', 'sat', 'sun'\]\.indexOf\(S\.day\)\);",
                   "    const dayIdx = Math.max(0, this.DAYS.findIndex(d => d.id === S.day));",
                   "phone day index")
    src = sub_once(src,
                   r"          width: 'calc\(\(100% - 18px\) / 3\)', height: '40px', borderRadius: '20px',",
                   "          width: 'calc((100% - ' + (10 + (this.DAYS.length - 1) * 4) + 'px) / '\n"
                   "            + this.DAYS.length + ')', height: '40px', borderRadius: '20px',",
                   "phone day pill")

    # Three and a half stage columns is the design's phone grid, drawn at
    # 390px. On a 320px screen that is a 79px column, and an act's name comes
    # out one letter to the line. Below 360px the grid shows two and a half
    # instead — a column wide enough to read, and the half still says there is
    # more to the right.
    src = sub_once(
        src,
        r"const gutter = 44, headH = 48, colMin = 'calc\(\(100dvw - ' \+ 44 \+ 'px\) / 3\.5\)';",
        "const gutter = 44, headH = 48,\n"
        "        colMin = 'calc((100dvw - 44px) / ' + (S.w < 360 ? '2.5' : '3.5') + ')';",
        "phone column width")

    # The design's empty player promises "a Spotify or YouTube player appears
    # here once the act's link is in the programme data" — the links are in the
    # data, and they are the four buttons underneath. Nothing embeds a player
    # from this page, so the promise goes rather than being left to expire.
    src = sub_once(src, r"hasPlayer: !!media, noPlayer: !media,",
                   "hasPlayer: !!media, noPlayer: false,", "empty player")

    src = sub_once(
        src,
        r"      sheetStyle: \{\n"
        r"        position: 'relative', width: 'min\(480px, 100%\)', overflow: 'visible',\n"
        r"        borderRadius: '28px', background: sev \? this\.ART\[sev\.cat\]\.surf : 'var\(--card,#F2F0EB\)',\n"
        r"        boxShadow: '0 12px 48px rgba\(20,24,14,\.24\)', animation: 'fp-rise \.28s cubic-bezier\(\.2,0,0,1\)'\n"
        r"      \},",
        "      sheetStyle: Object.assign({\n"
        "        position: 'relative', overflow: 'visible',\n"
        "        /* The card is drawn to two widths: one column, and two from\n"
        "           700px of its own width. The dialog was capped at 480px, so\n"
        "           the second was unreachable — on a screen with the room for\n"
        "           it, the card gets its full measure. */\n"
        "        inlineSize: '100%',\n"
        "        borderRadius: '28px', background: sev ? this.ART[sev.cat].surf : 'var(--card,#F2F0EB)',\n"
        "        boxShadow: '0 12px 48px rgba(20,24,14,.24)', animation: 'fp-rise .28s cubic-bezier(.2,0,0,1)'\n"
        "      }, tight ? {\n"
        "        display: 'flex', flexDirection: 'column', overflow: 'hidden',\n"
        "        /* The bar floats over the page, so the sheet stops short of it. */\n"
        "        maxHeight: mob ? 'calc(100dvh - 150px)' : 'calc(100dvh - 48px)'\n"
        "      } : null),\n"
        "      /* The scrim keeps that same clearance, so a sheet that has been\n"
        "         unfolded scrolls clear of the bar rather than under it. */\n"
        "      sheetScrimStyle: {\n"
        "        position: 'fixed', inset: 0, zIndex: 70, display: 'grid',\n"
        "        justifyItems: 'center', placeContent: 'safe center',\n"
        "        padding: mob ? '16px 16px 124px' : '24px',\n"
        "        overflowY: 'auto', overscrollBehavior: 'contain',\n"
        "        background: 'var(--scrim,rgba(20,24,14,.32))',\n"
        "        animation: 'fp-fade .18s cubic-bezier(.2,0,0,1)'\n"
        "      },\n"
        "      sheetBodyStyle: tight ? { overflowY: 'auto', minHeight: 0 } : null,\n"
        "      /* On a phone the row rides at the foot of the scroll, over the\n"
        "         card's own surface and clear of the home indicator. Every\n"
        "         other thing about it — its layout, its rule, its buttons — is\n"
        "         the card's own stylesheet. */\n"
        "      sheetActionsStyle: tight ? {\n"
        "        position: 'sticky', insetBlockEnd: 0,\n"
        "        paddingBottom: mob ? 'calc(16px + env(safe-area-inset-bottom))' : '16px',\n"
        "        background: 'var(--surf)'\n"
        "      } : null,",
        "sheet on a phone")

    # Day labels that were written into strings.
    src = sub_once(src, r"'Flow Festival 2026 · Sat 15 August\\n'",
                   "(%s + ' · ' + this.DAY_WINDOW.label + '\\n')"
                   % js(fest.f["name"] + " " + fest.f["year"]), "clipboard header")
    src = sub_once(src, r"' · Sat 15 August'",
                   "' · ' + this.DAY_WINDOW.label", "sheet time line")
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

    return patch_nav(patch_card(patch_sheet(patch_rows(patch_cards(patch_grid(patch_viewport(
        patch_stage_colours(patch_weather(patch_map(src, fest), fest), fest))))))))


# ── the destination indicator ─────────────────────────
# M3 draws one indicator for a navigation list, not one per destination, and it
# travels: the tonal container leaves the destination you were on and arrives
# at the new one. The design paints a background on whichever destination is
# active instead, so the mark appears and disappears rather than moving.
#
# Two things are added here. The indicator becomes a single element behind the
# list, placed by measuring the active destination — so the drawer's 56dp row,
# the rail's 56×32 pill and the phone bar's 54×30 pill are all drawn from what
# is on screen rather than from three sets of numbers — and it moves on M3's
# emphasised spring, which overshoots slightly and settles.
#
# And it follows the page. On a pointer device the festival card and the
# programme are one scroll, so reaching the programme is arriving at it: the
# indicator moves as the controls bar passes under the header, and moves back
# on the way up. On a phone each destination is its own screen and nothing
# spies on anything.
NAV_JS = """
  /* Swapping shells — drawer to rail, rail to the phone bar — moves every
     destination and takes about a third of a second to settle, because the
     bar itself is animating into place. Measured once, at the moment of the
     swap, the pill would take the box the row is leaving. So it is measured
     now, on the next frame, and once the shell's own motion has finished. */
  scheduleNavPill() {
    this.measureNavPill();
    cancelAnimationFrame(this.navPillRaf || 0);
    this.navPillRaf = requestAnimationFrame(() => this.measureNavPill());
    clearTimeout(this.navPillTimer);
    this.navPillTimer = setTimeout(() => this.measureNavPill(), 340);
  }

  /* The indicator's box, measured off the destination that is current. */
  measureNavPill() {
    const wrap = this.navListEl;
    if (!wrap) return;
    const btn = wrap.querySelector('[aria-current="page"]');
    if (!btn) { if (this.state.navPill) this.setState({ navPill: null }); return; }
    /* In the drawer the whole row is the container; in the rail and the bar it
       is the smaller pill behind the icon. */
    const target = this.navShown === 'drawer' ? btn : (btn.firstElementChild || btn);
    const box = wrap.getBoundingClientRect(), r = target.getBoundingClientRect();
    if (!r.width) return;
    const next = {
      x: Math.round(r.left - box.left), y: Math.round(r.top - box.top),
      w: Math.round(r.width), h: Math.round(r.height),
      r: this.navShown === 'drawer' ? 28 : 16
    };
    const cur = this.state.navPill;
    if (!cur || cur.x !== next.x || cur.y !== next.y || cur.w !== next.w ||
        cur.h !== next.h || cur.r !== next.r) this.setState({ navPill: next });
  }

  /* Which destination the page is on: the festival card and the weather are
     Info, and the programme underneath them is Programme. While any of the
     cards is still standing below the header the reader is in Info; once they
     have gone up under it — scrolled past, or folded away — the programme is
     what is on screen. Folding them back open returns the page to the top, so
     the indicator travels back on its own. */
  navSpy() {
    if (this.navShown === 'bar' || this.state.view === 'map') return;
    /* Info is the festival card and the weather. While either of them still
       stands below the header the reader is on Info; once they have gone up
       under it — scrolled past, or folded away — the programme has the screen.
       Unfolding them returns the page to the top, which brings them back and
       the indicator with it. */
    const el = this.spyEls && this.spyEls[0];
    if (!el) return;
    const at = el.getBoundingClientRect().bottom - ((this.state.headerH || 0) + 8) > 24
      ? 'info' : 'timetable';
    if (at !== this.state.spy) this.setState({ spy: at });
  }

  /* The row can change shape without the page changing state — a font
     arriving, the bar compacting to icons, a label wrapping at 320px — and the
     pill would be left measuring the row it used to be. So it watches the box
     as well as every update. */
  navBoxWatch() {
    const el = this.navListEl;
    if (el === this.navBoxEl) return;
    if (this.navRO) { this.navRO.disconnect(); this.navRO = null; }
    this.navBoxEl = el;
    if (!el || !('ResizeObserver' in window)) return;
    this.navRO = new ResizeObserver(() => this.measureNavPill());
    this.navRO.observe(el);
  }

  /* What wakes it. Observers on the cards and on the programme rather than a
     scroll listener alone: the same answer whether the page was scrolled, a
     card was folded, the window was resized or a destination was tapped — and
     it costs nothing while nothing moves. */
  navWatch(els) {
    const live = els.filter(Boolean);
    const same = this.spyEls && this.spyEls.length === live.length
      && this.spyEls.every((el, i) => el === live[i]);
    if (same) return;
    if (this.heroSpy) { this.heroSpy.disconnect(); this.heroSpy = null; }
    this.spyEls = live;
    if (!live.length || !('IntersectionObserver' in window)) return;
    const steps = [];
    for (let i = 0; i <= 20; i++) steps.push(i / 20);
    this.heroSpy = new IntersectionObserver(() => this.navSpy(), { threshold: steps });
    live.forEach(el => this.heroSpy.observe(el));
    this.navSpy();
  }
"""


# ── which viewport the shell is laid out in ───────────
# The design chooses its navigation — drawer, rail or bottom bar — from
# window.innerWidth, read at mount and on the window's own resize event. That
# is not the width the page is laid out at: a device toolbar, a pinch-zoom, an
# embedded frame or a browser that reports its chrome can all leave innerWidth
# saying one thing while the layout viewport says another, and a phone then
# gets the tablet's rail with a 300px column beside it. Worse, a viewport can
# change without any resize event reaching the page at all.
#
# The layout viewport is what CSS media queries use, so it is what the shell
# reads too — document.documentElement.clientWidth — and it is watched with a
# ResizeObserver, which fires however the change arrived, alongside the resize,
# orientationchange and visualViewport events.
def patch_viewport(src: str) -> str:
    src = sub_once(
        src,
        r"    this\.onResize = \(\) => \{\n"
        r"      this\.setState\(\{ w: window\.innerWidth, vh: window\.innerHeight \}\);",
        "    /* The layout viewport, which is the one the page is drawn in. */\n"
        "    this.viewport = () => ({\n"
        "      w: Math.round(document.documentElement.clientWidth || window.innerWidth || 0),\n"
        "      vh: Math.round(document.documentElement.clientHeight || window.innerHeight || 0)\n"
        "    });\n"
        "    this.onResize = () => {\n"
        "      this.setState(this.viewport());",
        "viewport measure")

    src = sub_once(
        src,
        r"    window\.addEventListener\('resize', this\.onResize\);",
        "    window.addEventListener('resize', this.onResize);\n"
        "    window.addEventListener('orientationchange', this.onResize);\n"
        "    if (window.visualViewport) {\n"
        "      window.visualViewport.addEventListener('resize', this.onResize);\n"
        "    }\n"
        "    /* Fires for every way a viewport can change, including the ones\n"
        "       that send no resize event — a device toolbar being switched on,\n"
        "       a frame being resized around the page. */\n"
        "    if ('ResizeObserver' in window) {\n"
        "      this.viewRO = new ResizeObserver(() => this.onResize());\n"
        "      this.viewRO.observe(document.documentElement);\n"
        "    }",
        "viewport observers")

    src = sub_once(
        src,
        r"    window\.removeEventListener\('resize', this\.onResize\);",
        "    window.removeEventListener('resize', this.onResize);\n"
        "    window.removeEventListener('orientationchange', this.onResize);\n"
        "    if (window.visualViewport) {\n"
        "      window.visualViewport.removeEventListener('resize', this.onResize);\n"
        "    }\n"
        "    if (this.viewRO) { this.viewRO.disconnect(); this.viewRO = null; }",
        "viewport teardown")

    src = sub_once(
        src,
        r"    this\.setState\(\{ w: window\.innerWidth, vh: window\.innerHeight \}\);\n  \}",
        "    this.setState(this.viewport());\n  }",
        "viewport at mount")
    return src


# ── the cell is the name ──────────────────────────────
# A cell in the grid says one thing — who is playing — and it has never had
# much room to say it. Three changes give it what there is:
#
# The margin each cell keeps from its lane. The design leaves 10px on both
# sides, which on a phone column is a fifth of the cell; it keeps 2, enough to
# read as a card standing in its lane rather than as the lane itself.
#
# The genres. They were printed as outlined chips in any cell tall enough to
# hold them, which is a second and a third line of text in a box that had not
# finished the first. The act's own card lists them, and so does every row of
# the list view.
#
# The star. It sat in the top-right corner, over the corner the name starts
# from, so every starrable cell reserved 24px of its first line for it. It
# stands in the bottom-left corner now and the name has the full width above
# it — clamped to whole lines, because a clamp that lands mid-line shows the
# top halves of the letters underneath it.
def patch_grid(src: str) -> str:
    src = sub_once(
        src,
        r"          const pxh = dur \* min;\n",
        "          const pxh = dur * min;\n"
        "          /* What the cell has to give: the margin it keeps in its\n"
        "             lane, and — the star standing in the bottom-left corner\n"
        "             now — how many whole lines of the name fit above it.\n"
        "             Three at the most, which is the clamp the design set. */\n"
        "          const gut = mob ? 2 : 10;\n"
        "          const hasStar = (mob ? pxh >= 44 : dur >= 40) && ev._lanes < 2;\n"
        "          const starBox = mob ? 20 : 24, starGap = mob ? 2 : 5;\n"
        "          const lineH = (mob ? (pxh < 48 ? 11 : 11.5)\n"
        "                             : (pxh < 48 ? 12 : 12.5)) * 1.22;\n"
        "          /* The shortest cell that carries a star is a 45-minute set\n"
        "             on a phone, 39px tall, where one line and the star leave\n"
        "             3px over: there the inset gives way rather than the star\n"
        "             sitting under the name. */\n"
        "          const padY = hasStar\n"
        "            ? Math.min(mob ? 3 : 9,\n"
        "                Math.max(2, (pxh - 10) - starGap - starBox - lineH))\n"
        "            : (mob ? 5 : (pxh < 48 ? 5 : 9));\n"
        "          const lines = Math.max(1, Math.min(3, Math.floor(\n"
        "            ((pxh - 10) - padY - starGap - starBox - 1) / lineH)));\n",
        "cell geometry")
    src = sub_once(
        src,
        r"            showTags: pxh >= 118 && ev\.genres\.length > 0,\n"
        r"            showStar: \(mob \? pxh >= 44 : dur >= 40\) && ev\._lanes < 2,",
        "            showTags: false,\n"
        "            showStar: hasStar,",
        "cell tags and star")
    src = sub_once(
        src,
        r"              left: 'calc\(' \+ \(ev\._lane / ev\._lanes\) \* 100 \+ '% \+ 10px\)',\n"
        r"              width: 'calc\(' \+ 100 / ev\._lanes \+ '% - 20px\)'",
        "              left: 'calc(' + (ev._lane / ev._lanes) * 100 + '% + ' + gut + 'px)',\n"
        "              width: 'calc(' + 100 / ev._lanes + '% - ' + (2 * gut) + 'px)'",
        "cell margin")
    # The cell's own inset counts as margin to the eye as much as the gap
    # outside it does: 9px of it on a phone is another sixth of the column.
    src = sub_once(
        src,
        r"              padding: pxh < 48 \? '5px 9px' : '9px 11px',"
        r" border: 0, borderRadius: mob \? '12px' : '14px',",
        "              padding: padY + 'px ' + (mob ? 7 : (pxh < 48 ? 9 : 11)) + 'px',"
        " border: 0, borderRadius: mob ? '12px' : '14px',",
        "cell inset")
    src = sub_once(
        src,
        r"              position: 'absolute', top: '6px', insetInlineEnd: '6px',"
        r" display: 'grid', placeItems: 'center',\n"
        r"              width: '26px', height: '26px', border: 0, borderRadius: '50%',",
        "              position: 'absolute', bottom: starGap + 'px',"
        " insetInlineEnd: starGap + 'px',\n"
        "              display: 'grid', placeItems: 'center',\n"
        "              width: starBox + 'px', height: starBox + 'px',"
        " border: 0, borderRadius: '50%',",
        "star corner")
    # The tick a planned cell carries stood in that same corner; it takes the
    # other end of the row, where the star used to leave a hole.
    src = sub_once(
        src,
        r"            checkStyle: \{ position: 'absolute', bottom: '8px',"
        r" insetInlineEnd: '8px', width: '15px', height: '15px',"
        r" fill: 'currentColor', opacity: \.9 \},",
        "            checkStyle: { position: 'absolute',"
        " bottom: (starGap + (starBox - 15) / 2) + 'px',\n"
        "              insetInlineStart: starGap + 'px', width: '15px',"
        " height: '15px', fill: 'currentColor', opacity: .9 },",
        "planned tick")
    src = sub_once(
        src,
        r"              whiteSpace: \(pxh < 48 \|\| ev\._lanes > 1\) \? 'nowrap' : 'normal',\n"
        r"              textOverflow: 'ellipsis',\n"
        r"              maxHeight: \(pxh < 48 \|\| ev\._lanes > 1\) \? 'none' : '3\.7em',\n"
        r"              paddingInlineEnd: \(\(mob \? pxh >= 44 : dur >= 40\)"
        r" && ev\._lanes < 2\) \? '24px' : '0px'",
        "              whiteSpace: (pxh < 48 || ev._lanes > 1"
        " || (hasStar && lines === 1)) ? 'nowrap' : 'normal',\n"
        "              textOverflow: 'ellipsis',\n"
        "              maxHeight: hasStar ? (lines * lineH).toFixed(1) + 'px'\n"
        "                : (pxh < 48 || ev._lanes > 1) ? 'none' : '3.7em',\n"
        "              /* Nothing is reserved at the end of the line any more:\n"
        "                 the star is out of the name's way, and the tick a\n"
        "                 planned cell carries is in the star's row. */\n"
        "              paddingInlineEnd: '0px'",
        "name in the cell")
    return src


# ── the two cards leave the way they arrive ───────────
# The weather card springs in on the emphasised spring and then, when it is
# folded away, is simply gone — the element unmounts on the same frame the
# state changes. The festival card beside it neither arrives nor leaves.
#
# Both get the pair: in on the design's own spring, out on the same movement
# reversed and quicker, which is what M3 asks for — a container leaves along
# the path it came in by, on the accelerating curve. The card is held in the
# page until its exit has finished playing.
CARD_IN = "'fp-weather-in 480ms cubic-bezier(.42,1.67,.21,.9) both'"
CARD_OUT = "'fp-card-out 320ms cubic-bezier(.3,0,.8,.15) both'"
CARD_OUT_MS = 320


def patch_cards(src: str) -> str:
    # ---- both cards stay in the page while they are leaving ----
    src = sub_once(src, r"      showHeroCard: S\.heroOpen !== false,",
                   "      showHeroCard: S.heroOpen !== false || !!S.heroClosing,",
                   "hero card while closing")
    src = sub_once(
        src,
        r"    const weatherShown = this\.props\.showWeather !== false && !!S\.wx"
        r" && S\.weatherOpen !== false;",
        "    const weatherShown = this.props.showWeather !== false && !!S.wx\n"
        "      && (S.weatherOpen !== false || !!S.wxClosing);",
        "weather while closing")
    src = sub_once(
        src,
        r"      showWeather: this\.props\.showWeather !== false && !!S\.wx"
        r" && S\.weatherOpen !== false,",
        "      showWeather: this.props.showWeather !== false && !!S.wx\n"
        "        && (S.weatherOpen !== false || !!S.wxClosing),",
        "weather prop while closing")

    # ---- the toggles: open at once, close after the animation ----
    src = sub_once(
        src,
        r"      toggleHero: \(\) => this\.scrollTop\(\(\) => this\.setState"
        r"\(s => \(\{ heroOpen: s\.heroOpen === false \}\)\)\),",
        "      toggleHero: () => this.foldCard('hero'),",
        "hero toggle")
    src = sub_once(
        src,
        r"      toggleWeather: \(\) => this\.scrollTop\(\(\) => this\.setState"
        r"\(s => \(\{ weatherOpen: s\.weatherOpen === false \}\)\)\),",
        "      toggleWeather: () => this.foldCard('weather'),",
        "weather toggle")

    src = sub_once(
        src,
        r"  /\* Folding either card returns the page to the top",
        "  /* Folding a card away plays its exit first and takes it out of the\n"
        "     page after — unfolding is immediate, because there is nothing to\n"
        "     wait for. Either way the page returns to the top, which is what\n"
        "     the design does. */\n"
        "  foldCard(which) {\n"
        "    const open = which === 'hero' ? 'heroOpen' : 'weatherOpen';\n"
        "    const shut = which === 'hero' ? 'heroClosing' : 'wxClosing';\n"
        "    if (this.state[open] === false) {\n"
        "      clearTimeout(this.foldT && this.foldT[which]);\n"
        "      this.scrollTop(() => this.setState({ [open]: true, [shut]: false }));\n"
        "      return;\n"
        "    }\n"
        "    this.scrollTop(() => this.setState({ [shut]: true }));\n"
        "    this.foldT = this.foldT || {};\n"
        "    const done = () => {\n"
        "      clearTimeout(this.foldT[which]);\n"
        "      this.setState({ [open]: false, [shut]: false });\n"
        "    };\n"
        "    /* Taken out of the page when its exit actually ends. The timer is\n"
        "       only the backstop — for a reader who has asked for no motion,\n"
        "       where there is no animation to end, and for a tab in the\n"
        "       background, where it fires late and nothing is on screen to\n"
        "       care. */\n"
        "    requestAnimationFrame(() => {\n"
        "      const el = which === 'hero'\n"
        "        ? document.querySelector('[data-fp-card]:not(#fp-weather)')\n"
        "        : document.getElementById('fp-weather');\n"
        "      if (el) el.addEventListener('animationend', done, { once: true });\n"
        "    });\n"
        "    clearTimeout(this.foldT[which]);\n"
        "    this.foldT[which] = setTimeout(done, %d);\n"
        "  }\n\n"
        "  /* Folding either card returns the page to the top" % (CARD_OUT_MS + 90),
        "fold a card")

    # ---- the movement itself ----
    src = sub_once(
        src,
        r"        animation: 'fp-weather-in 480ms cubic-bezier\(\.42,1\.67,\.21,\.9\) both'\n"
        r"      \},",
        "        animation: S.wxClosing ? %s : %s\n      }," % (CARD_OUT, CARD_IN),
        "weather card motion")
    src = sub_once(
        src,
        r"        background: 'var\(--card,#F2F0EB\)', borderRadius: '28px', padding: '12px'\n"
        r"      \},",
        "        background: 'var(--card,#F2F0EB)', borderRadius: '28px', padding: '12px',\n"
        "        transformOrigin: 'top left', willChange: 'transform, opacity',\n"
        "        animation: S.heroClosing ? %s : %s\n      }," % (CARD_OUT, CARD_IN),
        "festival card motion")
    return src


# ── the act sheet opens out of the cell it came from ──
# M3's container transform: the thing you pressed grows into the thing you
# opened, so the page never cuts. The cell's own rectangle is measured as the
# press lands — every way in goes through a press, so nothing has to be
# threaded through the six places that open a sheet — and the sheet is played
# from that rectangle to its own with the Web Animations API.
#
# On a phone the sheet is then the whole page rather than a card in the middle
# of one, with its close button in the corner and its actions at the foot.
#
# And it is thrown away rather than dismissed: a drag from anywhere carries the
# sheet with the finger and past 110px, or a flick, it leaves in the direction
# it was going. Under that it springs back. Vertical drags are only taken when
# the body is already at its top, so the introduction can still be scrolled.
SHEET_JS = """
  /* The rectangle of whatever was pressed, kept for the next sheet that
     opens. Capture phase, so a cell that stops the event still reports. */
  markTap = (e) => {
    if (!e.target || !e.target.closest) return;
    /* Nothing pressed while a sheet is open is what that sheet grew out of —
       not the sheet, not the scrim behind it, which is a button the size of
       the screen and would leave the arc with nowhere to travel. The cell is
       remembered until the sheet is done with it. */
    if (this.state.sheet) return;
    if (e.target.closest('[role="dialog"]')) return;
    /* The cell rather than the star inside it: the cell is the container that
       opens, and it is the one carrying the role. */
    const el = e.target.closest('[role="button"]') || e.target.closest('button,li');
    if (!el) return;
    const r = el.getBoundingClientRect();
    if (r.width && r.height) this.tapRect = r;
  };

  setSheetEl = (el) => {
    if (this.sheetEl === el) return;
    if (this.sheetEl) this.sheetDragOff();
    this.sheetEl = el;
    this.sheetBodyEl = el ? el.querySelector('[style*="overflow-y: auto"], [style*="overflow-y:auto"]') : null;
    if (el) this.sheetDragOn();
  };

  /* The page behind steps back while a sheet is up — the class is on the body
     so the shell's own rule does the moving. Read on every update rather than
     only when the sheet arrives, because the shell that has to step back
     depends on the width as much as on the sheet, and it is dropped as the
     sheet starts leaving so the two movements play together. */
  syncSheetShell() {
    const on = !!this.state.sheet && !this.sheetLeaving && this.mode() === 'bar';
    document.body.classList.toggle('fp-sheet', on);
  }

  /* A phone gets the modal bottom sheet; everything wider keeps the container
     transform out of the cell that was pressed. */
  sheetIsBottom() { return this.mode() === 'bar'; }
  sheetScrimEl() {
    const el = this.sheetEl;
    return el ? el.closest('[style*="z-index: 70"]') : null;
  }

  /* ---- container transform ---- */
  /* A cubic-bezier read as a function of time, by bisection — eighteen
     samples do not need the analytic solution. */
  bez(x1, y1, x2, y2) {
    const cx = 3 * x1, bx = 3 * (x2 - x1) - cx, ax = 1 - cx - bx;
    const cy = 3 * y1, by = 3 * (y2 - y1) - cy, ay = 1 - cy - by;
    const fx = (t) => ((ax * t + bx) * t + cx) * t;
    const fy = (t) => ((ay * t + by) * t + cy) * t;
    return (x) => {
      let lo = 0, hi = 1, t = x;
      for (let i = 0; i < 22; i++) { t = (lo + hi) / 2; if (fx(t) < x) lo = t; else hi = t; }
      return fy(t);
    };
  }

  /* M3 moves a container along an arc, not along the diagonal between two
     points, and it does not move at one speed. Both are built here as a list
     of samples: the path is a quadratic Bézier whose control point is the
     corner the motion turns through — it leaves vertically when the travel is
     mostly vertical and horizontally when it is not — and the samples are
     taken at eased times, so the box drifts away, hurries through the middle
     and settles. The box grows on its own slightly springy curve, a little
     ahead of the travel, which is what makes it read as opening rather than
     as sliding.
     One list of samples serves both directions: played in reverse it is the
     same arc walked backwards, so the sheet shrinks into the cell along the
     line it grew out of. */
  sheetArc(from, to, endRadius) {
    const sx = Math.max(.04, from.width / to.width);
    const sy = Math.max(.04, from.height / to.height);
    const tx = (from.left + from.width / 2) - (to.left + to.width / 2);
    const ty = (from.top + from.height / 2) - (to.top + to.height / 2);
    const vertical = Math.abs(ty) > Math.abs(tx);
    const cx = vertical ? tx : 0, cy = vertical ? 0 : ty;
    const move = this.bez(.2, 0, 0, 1), grow = this.bez(.34, 1.16, .32, 1);
    const N = 18, out = [];
    for (let i = 0; i <= N; i++) {
      const t = i / N, p = move(t), g = grow(t), q = 1 - p;
      /* quadratic Bézier from (tx,ty) through the corner to (0,0) */
      const x = q * q * tx + 2 * q * p * cx;
      const y = q * q * ty + 2 * q * p * cy;
      out.push({
        offset: t,
        transform: 'translate(' + x.toFixed(2) + 'px,' + y.toFixed(2) + 'px) scale('
          + (sx + (1 - sx) * g).toFixed(4) + ',' + (sy + (1 - sy) * g).toFixed(4) + ')',
        borderRadius: (14 + (endRadius - 14) * g).toFixed(1) + 'px',
        opacity: Math.min(1, .4 + p * 1.8).toFixed(3),
        easing: 'linear'
      });
    }
    return out;
  }

  sheetGeometry() {
    const el = this.sheetEl, from = this.tapRect;
    if (!el || !el.animate || !from) return null;
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return null;
    const to = el.getBoundingClientRect();
    if (!to.width || !to.height) return null;
    const radius = parseFloat(getComputedStyle(el).borderTopLeftRadius) || 0;
    return { el: el, frames: this.sheetArc(from, to, radius) };
  }

  playSheetOpen() {
    const el = this.sheetEl;
    if (!el || !el.animate) return;
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    /* The sheet rises from the edge it will be dragged back to, on M3's
       emphasised decelerate: quick away from the edge, settling into place. */
    if (this.sheetIsBottom()) {
      el.animate([{ transform: 'translateY(100%)' }, { transform: 'none' }],
        { duration: 420, easing: 'cubic-bezier(.05,.7,.1,1)' });
      return;
    }
    const g = this.sheetGeometry();
    /* Opened by a keyboard, or from something with no box to grow out of:
       the design's own rise, which is what this replaces. */
    if (!g) {
      el.animate([
        { opacity: 0, transform: 'translateY(14px) scale(.97)' },
        { opacity: 1, transform: 'none' }
      ], { duration: 280, easing: 'cubic-bezier(.2,0,0,1)' });
      return;
    }
    g.el.animate(g.frames, { duration: 460, easing: 'linear', fill: 'backwards' });
    /* The contents arrive a beat later, so the box reads as the thing that
       grew and the text as what was inside it all along. */
    const body = el.children[el.children.length - 1];
    if (body && body.animate) {
      body.animate([{ opacity: 0 }, { opacity: 0, offset: .38 }, { opacity: 1 }],
        { duration: 460, easing: 'cubic-bezier(.2,0,0,1)' });
    }
  }

  /* Closing walks the arc back: same path, same shape, mirrored in time and
     quicker, which is what M3 asks an exit to be. */
  dismissSheet(held) {
    const el = this.sheetEl;
    const shut = () => {
      clearTimeout(this.closeT);
      this.sheetLeaving = false;
      this.setState({ sheet: null });
    };
    if (!el) { shut(); return; }
    /* The sheet leaves the way it came, down past the edge, on the
       accelerating curve — and from wherever the finger left it, so a drag
       that becomes a dismissal is one movement rather than two. */
    if (this.sheetIsBottom()) {
      const h = el.getBoundingClientRect().height || 1;
      const from = (held && held.dy > 0 ? held.dy : 0);
      const rest = Math.max(0, h - from);
      const ms = Math.max(140, Math.min(260, Math.round(260 * rest / h)));
      const scrim = this.sheetScrimEl();
      this.sheetLeaving = true;
      this.syncSheetShell();
      el.style.transition = 'none';
      if (el.animate) {
        el.animate([
          { transform: 'translateY(' + from + 'px)' },
          { transform: 'translateY(' + h + 'px)' }
        ], { duration: ms, easing: 'cubic-bezier(.3,0,.8,.15)', fill: 'forwards' });
      }
      if (scrim && scrim.animate) {
        scrim.animate([{ opacity: Number(scrim.style.opacity || 1) }, { opacity: 0 }],
          { duration: ms, easing: 'linear', fill: 'forwards' });
      }
      clearTimeout(this.closeT);
      this.closeT = setTimeout(shut, ms + 20);
      return;
    }
    /* Measured with any drag undone, or the arc would start from wherever the
       finger left the sheet. What the finger did is put back on top of it
       below, as its own movement. */
    el.style.transition = 'none';
    el.style.transform = 'none';
    el.style.opacity = '1';
    const g = this.sheetGeometry();
    if (!g) { shut(); return; }
    const a = g.el.animate(g.frames, {
      duration: 380, easing: 'linear', direction: 'reverse', fill: 'forwards'
    });
    /* Added to the arc rather than replacing it: the offset the throw ended
       on eases away while the sheet is already on its way home, so it curves
       out of the throw instead of snapping back first. */
    if (held && el.animate) {
      try {
        el.animate([
          { transform: 'translate(' + held.dx + 'px,' + held.dy + 'px) rotate('
            + held.rot + 'deg)' },
          { transform: 'translate(0px,0px) rotate(0deg)' }
        ], { duration: 300, easing: 'cubic-bezier(.2,0,0,1)', composite: 'add' });
      } catch (err) { /* no additive composition here; the arc still plays */ }
    }
    const body = el.children[el.children.length - 1];
    if (body && body.animate) {
      body.animate([{ opacity: 1 }, { opacity: 0, offset: .45 }, { opacity: 0 }],
        { duration: 380, easing: 'cubic-bezier(.3,0,.8,.15)' });
    }
    a.onfinish = shut;
    clearTimeout(this.closeT);
    this.closeT = setTimeout(shut, 520);
  }

  /* ---- drag the sheet down to close it ----
     Downwards only, and only from the top of what it holds: a drag over the
     introduction reads the introduction, and one that has scrolled the card
     is scrolling the card. Once the gesture is taken the sheet is under the
     finger — no threshold to cross before it starts moving, and the scrim
     fades with it — and it is let go at the finger's own speed: far enough
     down, or thrown down, and it carries on out; short of that it springs
     back to the edge it rose from. */
  sheetDragOnBottom() {
    const el = this.sheetEl, scrim = this.sheetScrimEl();
    const atTop = () => {
      const b = this.sheetBodyEl;
      return !b || b.scrollTop <= 0;
    };
    this.onSheetDown = (e) => {
      if (e.button != null && e.button !== 0) return;
      this.drag = { y: e.clientY, t: performance.now(), on: false, top: atTop(), dy: 0 };
    };
    this.onSheetMove = (e) => {
      const d = this.drag;
      if (!d) return;
      const dy = e.clientY - d.y;
      if (!d.on) {
        if (dy < 6) { if (dy < -4) this.drag = null; return; }
        /* The card may have been scrolled between the press and the move. */
        if (!d.top || !atTop()) { this.drag = null; return; }
        d.on = true;
        el.style.transition = 'none';
        if (el.setPointerCapture && e.pointerId != null) {
          try { el.setPointerCapture(e.pointerId); } catch (err) { /* not ours */ }
        }
      }
      if (e.cancelable) e.preventDefault();
      d.dy = Math.max(0, dy);
      const h = el.getBoundingClientRect().height || 1;
      el.style.transform = 'translateY(' + d.dy + 'px)';
      if (scrim) scrim.style.opacity = String(Math.max(0, 1 - (d.dy / h) * .9));
    };
    this.onSheetUp = (e) => {
      const d = this.drag;
      this.drag = null;
      if (!d || !d.on) return;
      const dy = Math.max(0, e.clientY - d.y);
      const speed = dy / Math.max(1, performance.now() - d.t);
      const h = el.getBoundingClientRect().height || 1;
      if (dy > Math.min(150, h * .28) || (dy > 24 && speed > .55)) {
        this.dismissSheet({ dy: dy });
        return;
      }
      el.style.transition = 'transform .38s cubic-bezier(.2,0,0,1)';
      el.style.transform = 'none';
      if (scrim) {
        scrim.style.transition = 'opacity .2s linear';
        scrim.style.opacity = '1';
      }
    };
    el.addEventListener('pointerdown', this.onSheetDown);
    el.addEventListener('pointermove', this.onSheetMove, { passive: false });
    el.addEventListener('pointerup', this.onSheetUp);
    el.addEventListener('pointercancel', this.onSheetUp);
  }

  /* ---- what you starred goes to where it is kept ----
     Pressing the star turned a cell dark and put a number up somewhere else on
     the screen, and the two were not connected by anything the eye could
     follow. So the cell itself goes: a copy of it leaves the grid, travels to
     the button that counts your picks, and shrinks into it.

     The path is the card's own arc, from the same sampler — a quadratic
     Bézier with its control point above the line, so the copy lifts up and
     out the way something picked up leaves the place it was picked up from,
     and comes down into the button. The samples are taken at eased times, so
     the speed is not constant either: standard for the travel, accelerating
     for the collapse.

     The shape is the desktop's minimise: a window going to the dock stretches
     toward it, necks down and is drawn through it. A single box cannot warp
     the way that one does — there is no mesh here, only a transform — but the
     two things that read are the stretch along the line of travel and the
     necking across it, and both of those a transform can do: the scale is put
     between a rotation to the travel angle and its inverse, so one axis works
     along the path and the other across it, whatever direction the button
     happens to be in.

     The whole thing is one container transform at the duration M3 gives one,
     and the button answers with a beat of its own, which is what says the two
     are the same thing. */
  flyToPlan(host) {
    if (!host || !host.animate) return;
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    const target = document.querySelector('[data-fp-picks]');
    if (!target) return;
    const from = host.getBoundingClientRect(), to = target.getBoundingClientRect();
    if (!from.width || !to.width) return;
    const ghost = host.cloneNode(true);
    ghost.removeAttribute('id');
    ghost.setAttribute('aria-hidden', 'true');
    const skin = getComputedStyle(host);
    ghost.style.cssText = 'position:fixed;margin:0;z-index:94;pointer-events:none;'
      + 'left:' + from.left.toFixed(1) + 'px;top:' + from.top.toFixed(1) + 'px;'
      + 'width:' + from.width.toFixed(1) + 'px;height:' + from.height.toFixed(1) + 'px;'
      + 'border-radius:' + skin.borderRadius + ';overflow:hidden;'
      + 'transform-origin:50% 50%;will-change:transform,opacity;'
      + 'box-shadow:0 8px 24px rgba(20,24,14,.18)';
    document.body.appendChild(ghost);
    const dx = (to.left + to.width / 2) - (from.left + from.width / 2);
    const dy = (to.top + to.height / 2) - (from.top + from.height / 2);
    /* The corner the arc turns through, and it is above the line: the copy
       lifts up and out of the grid first, the way something picked up leaves
       the place it was picked up from, and comes down into the button at the
       end. The rise is a share of the distance, held between 80 and 220 so a
       short throw still arcs and a long one does not loop. */
    const dist = Math.hypot(dx, dy);
    const lift = Math.max(80, Math.min(220, dist * .45));
    const cx = dx * .58, cy = -lift;
    const move = this.bez(.2, 0, 0, 1), shrink = this.bez(.3, 0, .8, .15);
    const neck = this.bez(.2, 0, 0, 1);
    /* The shape is drawn through the path rather than shrunk on it — the
       minimise a desktop does when a window goes to the dock, as near as a
       single box can come to it without a mesh to warp. Two scales are put on
       either side of the travel angle, so one of them works along the line to
       the button and the other across it: along, the copy stretches as it is
       pulled away and then collapses; across, it necks down the whole way, so
       it reads as being drawn through the button rather than parked in front
       of it. The corners round to a circle over the same stretch, which is
       the shape it is going into. */
    const ang = Math.atan2(dy, dx) * 180 / Math.PI;
    const short = Math.min(from.width, from.height);
    const endAlong = Math.max(.05, (to.width * .8) / Math.max(from.width, 1));
    const endAcross = Math.max(.05, (to.height * .8) / Math.max(short, 1));
    const r0 = parseFloat(skin.borderTopLeftRadius) || 0, r1 = short / 2;
    const N = 26, frames = [];
    for (let i = 0; i <= N; i++) {
      const t = i / N, p = move(t), s = shrink(t), q = 1 - p;
      const x = 2 * q * p * cx + p * p * dx;
      const y = 2 * q * p * cy + p * p * dy;
      /* Pulled long first — a fifth again by a third of the way — then let go
         of, which is the stretch a window makes as it leaves the desktop. */
      const pull = t < .34 ? 1 + .22 * neck(t / .34) : 1.22 + (endAlong - 1.22) * shrink((t - .34) / .66);
      const across = 1 + (endAcross - 1) * neck(t);
      const m = neck(Math.min(1, t / .5));
      frames.push({
        offset: t, easing: 'linear',
        opacity: t < .72 ? 1 : Math.max(0, 1 - (t - .72) / .28),
        borderRadius: (r0 + (r1 - r0) * m).toFixed(1) + 'px',
        transform: 'translate3d(' + x.toFixed(1) + 'px,' + y.toFixed(1) + 'px,0) '
          + 'rotate(' + ang.toFixed(2) + 'deg) '
          + 'scale(' + pull.toFixed(4) + ',' + across.toFixed(4) + ') '
          + 'rotate(' + (-ang).toFixed(2) + 'deg)'
      });
    }
    ghost.animate(frames, { duration: 500, fill: 'forwards' });
    setTimeout(() => ghost.remove(), 560);
    /* And the button takes it in. */
    if (target.animate) {
      target.animate([
        { transform: 'scale(1)' },
        { transform: 'scale(1.18)', offset: .45 },
        { transform: 'scale(1)' }
      ], { duration: 300, easing: 'cubic-bezier(.2,0,0,1)', delay: 380 });
    }
  }

  /* ---- one blast per press, however fast they come ----
     The blast was a single slot in the state — one id, one set of sparks, one
     timer — so a second star pressed while the first was still going took the
     slot from it, and the sparks, being the same elements re-rendered with new
     values, never restarted their animations: the second press looked like
     nothing happened. Each press gets its own layer now, built from the same
     parts, played by the browser and thrown away when it is done. Nothing is
     shared, so nothing has to wait. */
  spawnBurst(rect, palette, colour) {
    if (!rect || !rect.width) return;
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    const layer = document.createElement('div');
    layer.setAttribute('aria-hidden', 'true');
    layer.style.cssText = 'position:fixed;z-index:90;width:40px;height:40px;'
      + 'pointer-events:none;color:' + colour + ';left:'
      + (rect.left + rect.width / 2 - 20).toFixed(1) + 'px;top:'
      + (rect.top + rect.height / 2 - 20).toFixed(1) + 'px';
    this.makeBurst(palette).forEach(p => {
      const el = document.createElement('i');
      Object.keys(p.style).forEach(k => {
        const v = p.style[k];
        if (k.charAt(0) === '-') el.style.setProperty(k, v);
        else el.style[k] = v;
      });
      layer.appendChild(el);
    });
    document.body.appendChild(layer);
    setTimeout(() => layer.remove(), 1300);
  }

  /* ---- throw to dismiss ---- */
  sheetDragOn() {
    const el = this.sheetEl;
    if (this.sheetIsBottom()) { this.sheetDragOnBottom(); return; }
    this.onSheetDown = (e) => {
      if (e.button != null && e.button !== 0) return;
      this.drag = { x: e.clientX, y: e.clientY, t: performance.now(), on: false };
    };
    this.onSheetMove = (e) => {
      const d = this.drag;
      if (!d) return;
      const dx = e.clientX - d.x, dy = e.clientY - d.y;
      if (!d.on) {
        if (Math.abs(dx) < 8 && Math.abs(dy) < 8) return;
        /* Sideways always; downwards only when there is nothing left to
           scroll, so a drag over the introduction still reads it. */
        const body = this.sheetBodyEl;
        const canPull = Math.abs(dx) > Math.abs(dy) || (dy > 0 && (!body || body.scrollTop <= 0));
        if (!canPull) { this.drag = null; return; }
        d.on = true;
        el.style.transition = 'none';
        if (el.setPointerCapture && e.pointerId != null) {
          try { el.setPointerCapture(e.pointerId); } catch (err) { /* not ours */ }
        }
      }
      if (e.cancelable) e.preventDefault();
      const far = Math.hypot(dx, dy);
      el.style.transform = 'translate(' + dx + 'px,' + dy + 'px) rotate(' + (dx * .02) + 'deg)';
      el.style.opacity = String(Math.max(.35, 1 - far / 520));
    };
    this.onSheetUp = (e) => {
      const d = this.drag;
      this.drag = null;
      if (!d || !d.on) return;
      const dx = e.clientX - d.x, dy = e.clientY - d.y;
      const far = Math.hypot(dx, dy);
      const speed = far / Math.max(1, performance.now() - d.t);
      /* Far enough to mean it, or a flick that went far enough to be one.
         It goes home the way every other dismissal does — down the arc, into
         the cell — carrying the offset the finger left it at, which decays as
         it goes so the two movements are one. */
      if (far > 110 || (far > 40 && speed > .8)) {
        this.dismissSheet({ dx: dx, dy: dy, rot: dx * .02 });
        return;
      }
      el.style.transition = 'transform .42s cubic-bezier(.42,1.67,.21,.9), opacity .2s linear';
      el.style.transform = 'none';
      el.style.opacity = '1';
    };
    el.addEventListener('pointerdown', this.onSheetDown);
    el.addEventListener('pointermove', this.onSheetMove, { passive: false });
    el.addEventListener('pointerup', this.onSheetUp);
    el.addEventListener('pointercancel', this.onSheetUp);
  }

  sheetDragOff() {
    const el = this.sheetEl;
    if (!el) return;
    el.removeEventListener('pointerdown', this.onSheetDown);
    el.removeEventListener('pointermove', this.onSheetMove);
    el.removeEventListener('pointerup', this.onSheetUp);
    el.removeEventListener('pointercancel', this.onSheetUp);
    this.drag = null;
  }
"""


def patch_card(src: str) -> str:
    """The act sheet becomes the artist card: a hero with the act's name over
    the artwork, a player that fetches nothing until it is pressed, the
    introduction, the links, the tags and the two actions."""
    # ---- the card takes its colours from the stage, not from a strand ----
    # The design ships three themes — music, art, film. This planner colours
    # by stage, and the blast, the chip, the plan button and the accent all
    # have to agree with the cell the card grew out of.
    src = sub_once(
        src,
        r"        onStar: \(e\) => this\.starToggle\(sev\.id, e\.currentTarget\.getBoundingClientRect\(\)\),",
        "        /* One stage, one set of colours, for every part of the card\n"
        "           that carries any. */\n"
        "        /* The reference's own strand class, so its stylesheet themes\n"
        "           the card exactly as written; the stage's colours are laid\n"
        "           over it as variables, which is the same set of names. */\n"
        "        cardClass: 'ac t-' + sev.cat,\n"
        "        artLabel: sev.title + ' artwork',\n"
        "        /* The corner says where, not what: the stage's own name. */\n"
        "        chipLabel: st.name,\n"
        "        listenClass: srcKeys.length ? 'listen' : 'listen listen--empty',\n"
        "        embedClass: 'listen__embed listen__embed--'\n"
        "          + (playSrc === 'youtube' ? 'yt' : 'sp')\n"
        "          + (S.playerOpen ? ' is-open' : ''),\n"
        "        /* Spotify draws two cards from the one URL: 152px of the act,\n"
        "           its Follow and its play button, or 352 with the first three\n"
        "           tracks under them. The tall one is most of a phone screen\n"
        "           before the introduction has started, so a phone opens the\n"
        "           short one and the chevron under it asks for the rest. */\n"
        "        showPlayerToggle: mob && playSrc === 'spotify',\n"
        "        playerOpen: String(!!S.playerOpen),\n"
        "        playerLabel: S.playerOpen\n"
        "          ? 'Hide the track list' : 'Show the track list',\n"
        "        onPlayerToggle: (e) => {\n"
        "          e.stopPropagation();\n"
        "          this.setState(s => ({ playerOpen: !s.playerOpen }));\n"
        "        },\n"
        "        /* The introduction is clipped to three lines and opens to its\n"
        "           own height, measured off the paragraph — the reference\n"
        "           animates max-block-size, which needs a number to animate to. */\n"
        "        bioClass: S.bioOpen ? 'bio is-open' : 'bio',\n"
        "        bioRef: this.setBioClip,\n"
        "        bioClipStyle: { maxBlockSize: S.bioOpen\n"
        "          ? ((S.bioFull || 800) + 'px') : 'calc(3 * 1.55em)' },\n"
        "        vars: Object.assign({\n"
        "          '--surf': A.surf,\n"
        "          '--chip': c.bg, '--on-chip': c.fg,\n"
        "          '--plan-bg': c.bg, '--plan-fg': c.fg,\n"
        "          '--plan-on': c.planBg, '--plan-on-fg': c.planFg,\n"
        "          '--accent': c.planBg, '--hero-tint': c.hero\n"
        "        }, {\n"
        "          '--art-bg': c.artBg, '--art-1': c.art1, '--art-2': c.art2,\n"
        "          '--art-3': c.art3, '--art-ink': c.artInk\n"
        "        }),\n"
        "        onStar: (e) => this.starToggle(sev.id, e.currentTarget.getBoundingClientRect()),",
        "card colours")

    src = sub_once(
        src,
        r"  /\* ---- container transform ---- \*/",
        "  /* The reference measures the paragraph to decide whether Read more\n"
        "     is needed at all, and how far the clip opens. Same measurement. */\n"
        "  setBioClip = (el) => {\n"
        "    if (this.bioClipEl === el) return;\n"
        "    this.bioClipEl = el;\n"
        "    if (el) requestAnimationFrame(() => this.measureBio());\n"
        "  };\n\n"
        "  measureBio() {\n"
        "    const clip = this.bioClipEl;\n"
        "    if (!clip || !clip.firstElementChild) return;\n"
        "    const full = clip.firstElementChild.scrollHeight;\n"
        "    const fits = !this.state.bioOpen && full <= clip.clientHeight + 2;\n"
        "    if (this.state.bioFull !== full || this.state.bioFits !== fits) {\n"
        "      this.setState({ bioFull: full, bioFits: fits });\n"
        "    }\n"
        "  }\n\n"
        "  srcIcon(kind) {\n"
        "    return {\n"
        "      flex: 'none', inlineSize: '15px', blockSize: '15px',\n"
        "      fill: kind === 'youtube' ? 'currentColor' : 'none',\n"
        "      stroke: kind === 'youtube' ? 'none' : 'currentColor'\n"
        "    };\n"
        "  }\n\n"
        "  /* ---- container transform ---- */",
        "source icon")

    # ---- what there is to play ----
    src = sub_once(
        src,
        r"      const media = this\.MEDIA\[sev\.title\];",
        "      /* Spotify embeds an artist page; YouTube needs a video, and the\n"
        "         records hold channels. So a card plays what it can and links\n"
        "         to the rest — no control appears for a source that has\n"
        "         nothing behind it. */\n"
        "      const media = sev.media || {};\n"
        "      /* Spotify first where an act has both: it plays the act's own\n"
        "         top tracks in place, where the YouTube embed is one video. */\n"
        "      const srcKeys = ['spotify', 'youtube'].filter(k => media[k]);\n"
        "      const playSrc = srcKeys[0];",
        "sheet media")

    src = sub_once(
        src,
        r"        hasPlayer: !!media, noPlayer: false,",
        "        hasSources: srcKeys.length > 0, noSources: srcKeys.length === 0,\n"
        "        /* The player is the card Spotify draws — the row of cover,\n"
        "           name and play button that used to stand over it said the\n"
        "           same three things a second time, in our own hand. */\n"
        "        embedTitle: sev.title,\n"
        "        embedOpen: srcKeys.length > 0,\n"
        "        /* The indicator stands until the frame reports itself loaded. */\n"
        "        embedLoading: srcKeys.length > 0 && !S.embedReady,\n"
        "        onEmbedLoad: () => this.setState({ embedReady: true }),\n"
        "        navLabel: 'Go to ' + st.name + ' on the map',\n"
        "        embedSrc: !playSrc ? ''\n"
        "          : (playSrc === 'youtube'\n"
        "            ? 'https://www.youtube-nocookie.com/embed/' + media.youtube + '?rel=0'\n"
        "            : 'https://open.spotify.com/embed/' + media.spotify\n"
        "              + '?utm_source=generator'),",
        "listen values")

    # The next card starts with its own introduction folded and waits for its
    # own player.
    src = sub_once(src, r"      if \(this\.state\.bioOpen\) this\.setState\(\{ bioOpen: false \}\);",
                   "      if (this.state.bioOpen || this.state.bioFits || this.state.embedReady) {\n"
                   "        this.setState({ bioOpen: false, bioFits: false, bioFull: 0,\n"
                   "          embedReady: false });\n"
                   "      }",
                   "fold the introduction again")

    # ---- the blast takes the stage's own tones ----
    src = sub_once(src, r"        next\.burstParts = this\.makeBurst\(\);",
                   "        /* The sparks are the stage's colours, so the blast belongs\n"
                   "           to the cell it came from rather than to a fixed green. */\n"
                   "        const sp = this.stageColor(ev.s);\n"
                   "        next.burstParts = this.makeBurst(\n"
                   "          [sp.dot, sp.bg, sp.planBg, sp.planFg, sp.dot]);",
                   "blast colours")
    return src


# ── the list row on a phone ───────────────────────────
# M3's list item, at the sizes M3 states for one. The design draws the row for
# a screen with room in it: a 96×72 picture, a 17px name — the same size as the
# name of the festival in the bar above it, and heavier — a 14px time and a
# 13.5px line under that, which on a phone is four sizes inside 72px and the
# name of the act with 150px to say itself in.
#
# What a row is for is who is playing, when and where. So: the picture is the
# 56dp leading image of an M3 list item, square and rounded to 16; the type —
# DJ, Live, Performance — is a label about the act rather than the act, and it
# is gone (a wide screen still carries it on the chip over the artwork); and
# the three lines take the type scale's own steps rather than sizes of their
# own — Title Small for the name, Body Small for the time and the place, which
# leaves the name a step below the bar's own title rather than level with it.
#
# The artwork takes the stage's palette, the one the card's hero takes, rather
# than the category's: two acts on the same stage look like it in the row, in
# the cell and on the card, and the row is where the reader meets them first.
def patch_rows(src: str) -> str:
    src = sub_once(
        src,
        r"        meta: \(narrow \? ev\.type \+ ' · ' : ''\) \+ st\.name"
        r" \+ \(ev\.genres\.length \? ' · ' \+ ev\.genres\.join\(', '\) : ''\),",
        "        /* On a phone the line under the time is where the act is\n"
        "           playing, and nothing else: the type and the genres are\n"
        "           what an act is, which its own card says at length and this\n"
        "           row can only say in an ellipsis. */\n"
        "        meta: mob ? st.name\n"
        "          : (narrow ? ev.type + ' · ' : '') + st.name\n"
        "            + (ev.genres.length ? ' · ' + ev.genres.join(', ') : ''),",
        "row without the type")
    src = sub_once(
        src,
        r"        style: \{\n"
        r"          position: 'relative', display: 'flex', alignItems: 'center',\n"
        r"          gap: narrow \? '10px' : '14px', padding: narrow \? '10px' : '12px',\n"
        r"          borderRadius: narrow \? '24px' : '28px', background: A\.surf,"
        r" color: 'var\(--on,#191D13\)',\n"
        r"          cursor: 'pointer', transition: 'box-shadow \.18s ease'\n"
        r"        \},\n"
        r"        mediaStyle: \{\n"
        r"          position: 'relative', flex: 'none', width: narrow \? '96px' : '148px',\n"
        r"          aspectRatio: narrow \? '4 / 3' : '3 / 2',\n"
        r"          borderRadius: narrow \? '14px' : '16px', overflow: 'hidden',"
        r" background: A\.bg\n"
        r"        \},",
        "        style: {\n"
        "          position: 'relative', display: 'flex', alignItems: 'center',\n"
        "          gap: mob ? '12px' : narrow ? '10px' : '14px',\n"
        "          padding: mob ? '8px' : narrow ? '10px' : '12px',\n"
        "          minBlockSize: mob ? '72px' : undefined,\n"
        "          borderRadius: mob ? '20px' : narrow ? '24px' : '28px',\n"
        "          background: A.surf, color: 'var(--on,#191D13)',\n"
        "          cursor: 'pointer', transition: 'box-shadow .18s ease'\n"
        "        },\n"
        "        mediaStyle: {\n"
        "          position: 'relative', flex: 'none',\n"
        "          width: mob ? '56px' : narrow ? '96px' : '148px',\n"
        "          height: mob ? '56px' : undefined,\n"
        "          aspectRatio: mob ? undefined : narrow ? '4 / 3' : '3 / 2',\n"
        "          borderRadius: mob ? '16px' : narrow ? '14px' : '16px',\n"
        "          overflow: 'hidden', background: A.bg\n"
        "        },\n"
        "        /* The type scale's own steps: title-small over body-small,\n"
        "           which is the pair M3 gives a list item's headline and its\n"
        "           supporting text one size down. */\n"
        "        rowTitleStyle: mob\n"
        "          ? { fontSize: '14px', fontWeight: 600, lineHeight: '20px',\n"
        "              letterSpacing: '.1px', overflow: 'hidden',\n"
        "              textOverflow: 'ellipsis', whiteSpace: 'nowrap' }\n"
        "          : { fontSize: '17px', fontWeight: 700, lineHeight: 1.25,\n"
        "              letterSpacing: '-.012em', overflow: 'hidden',\n"
        "              textOverflow: 'ellipsis', whiteSpace: 'nowrap' },\n"
        "        rowWhenStyle: mob\n"
        "          ? { fontSize: '12px', fontWeight: 400, lineHeight: '16px',\n"
        "              letterSpacing: '.4px', overflow: 'hidden',\n"
        "              textOverflow: 'ellipsis', whiteSpace: 'nowrap' }\n"
        "          : { fontSize: '14px', fontWeight: 450, overflow: 'hidden',\n"
        "              textOverflow: 'ellipsis', whiteSpace: 'nowrap' },\n"
        "        rowMetaStyle: mob\n"
        "          ? { display: 'inline-flex', alignItems: 'center', gap: '6px',\n"
        "              minWidth: 0, fontSize: '12px', lineHeight: '16px',\n"
        "              letterSpacing: '.4px', color: 'var(--on-var,#494E42)' }\n"
        "          : { display: 'inline-flex', alignItems: 'center', gap: '7px',\n"
        "              minWidth: 0, fontSize: '13.5px', opacity: .78 },\n"
        "        rowTextStyle: { flex: '1 1 auto', minWidth: 0, display: 'grid',\n"
        "          gap: mob ? '2px' : '5px' },",
        "row measurements")
    # An act that is on right now says so. Only on the day it is on: off the
    # festival the clock is parked at the start of the day, and every act at
    # noon would claim to be playing.
    src = sub_once(
        src,
        r"      const starred = !!S\.star\[ev\.id\], planned = starred,"
        r" dur = ev\.b - ev\.a;\n"
        r"      g\.rows\.push\(Object\.assign\(\{\n"
        r"        title: ev\.title,",
        "      const starred = !!S.star[ev.id], planned = starred,"
        " dur = ev.b - ev.a;\n"
        "      const liveAt = this.LIVE_AT;\n"
        "      const isLive = liveAt != null && ev.a <= liveAt && liveAt < ev.b;\n"
        "      g.rows.push(Object.assign({\n"
        "        live: isLive,\n"
        "        /* M3's own suggestion chip at its own size — full round, its\n"
        "           label in Label Small — in the stage's own dark container,\n"
        "           the tone its artwork beside it is drawn in, so the chip\n"
        "           belongs to the act rather than to the app. The bars beside\n"
        "           the word rise and fall on the standard curve, a second to\n"
        "           the cycle, each a third of a cycle behind the last. */\n"
        "        liveStyle: {\n"
        "          display: 'inline-flex', alignItems: 'center', gap: '5px',\n"
        "          justifySelf: 'start', blockSize: '20px',\n"
        "          padding: '0 8px 0 6px',\n"
        "          borderRadius: '10px', background: c.planBg, color: c.planFg,\n"
        "          fontSize: '11px',\n"
        "          lineHeight: '16px', letterSpacing: '.5px', fontWeight: 600\n"
        "        },\n"
        "        liveBarStyle: this.liveBar(0),\n"
        "        liveBar2Style: this.liveBar(1),\n"
        "        liveBar3Style: this.liveBar(2),\n"
        "        title: ev.title,",
        "the row knows it is on")
    # The head of each hour, holding at the top until the next one arrives.
    src = sub_once(
        src,
        r"    groups\.forEach\(g => \{ g\.count = g\.rows\.length === 1 \? '1 start'"
        r" : g\.rows\.length \+ ' starts'; \}\);",
        "    groups.forEach(g => {\n"
        "      g.count = g.rows.length === 1 ? '1 start' : g.rows.length + ' starts';\n"
        "      g.headStyle = {\n"
        "        position: 'sticky', zIndex: 3,\n"
        "        /* The list scrolls the page rather than a pane of its own, so\n"
        "           the hour holds under the title bar rather than under the\n"
        "           top of the screen, which is where the title bar is. */\n"
        "        insetBlockStart: mob ? ((S.headerH || 56) - 1) + 'px' : 0,\n"
        "        display: 'flex', alignItems: 'baseline', gap: '10px',\n"
        "        margin: '0 -4px', padding: mob ? '6px 8px 8px' : '0 4px 8px',\n"
        "        /* The bar it holds under, so the two read as one surface when\n"
        "           they meet and as nothing at all when they do not. */\n"
        "        background: mob ? 'var(--bar,rgba(255,255,255,.94))' : 'transparent',\n"
        "        WebkitBackdropFilter: mob ? 'blur(10px)' : undefined,\n"
        "        backdropFilter: mob ? 'blur(10px)' : undefined\n"
        "      };\n"
        "      g.timeStyle = { fontSize: '15px', fontWeight: 700,\n"
        "        letterSpacing: '-.01em' };\n"
        "      g.countStyle = { fontSize: '12.5px', color: 'var(--on-var,#494E42)' };\n"
        "    });",
        "the hour holds at the top")
    src = sub_once(
        src,
        r"      \}, this\.mediaParts\(ev\.cat\), this\.starParts\(ev\.id, starred\)\)\);",
        "      }, this.mediaParts(ev.cat), mob ? {\n"
        "        /* The stage's palette rather than the category's, so the\n"
        "           thumbnail, the cell and the card's hero are one colour. */\n"
        "        artStyle: {\n"
        "          display: 'block', width: '100%', height: '100%',\n"
        "          '--art-bg': c.artBg, '--art-1': c.art1, '--art-2': c.art2,\n"
        "          '--art-3': c.art3, '--art-ink': c.artInk\n"
        "        }\n"
        "      } : null, this.starParts(ev.id, starred)));",
        "row artwork in the stage's colour")
    return src


def patch_sheet(src: str) -> str:
    # The star's clip path is named after the act, and the act appears twice at
    # once — once in the list behind the card, once in the card. Two elements
    # then carry the same id, the first wins, and the card's own disc is inert.
    # The reference mints one id per card for exactly this reason.
    src = sub_once(src, r"    const cid = 'fav-' \+ id;",
                   "    const cid = 'fav-' + id + '-'"
                   " + (this.cidSeq = (this.cidSeq || 0) + 1);",
                   "one clip path per star")

    # Back walks out of the planner. It closes what is open first — the card
    # on its arc, then the filters — then retraces the destinations it was
    # given, and when there is nothing left to retrace it does what the arrow
    # says and leaves for the festival list. Relative, so it works from a
    # directory on a phone and from the published site alike.
    src = sub_once(
        src,
        r"    const prev = h\.length \? h\[h\.length - 1\] : 'timetable';",
        "    if (!h.length) { this.leavePlanner(); return; }\n"
        "    const prev = h[h.length - 1];",
        "back leaves for the list")
    # Where the button goes when the planner has nothing left to go back
    # through, and what it is drawn as. A reader who arrived from somewhere on
    # this site has a page to be returned to, and the arrow returns them to it.
    # A reader who opened the link cold has nothing behind them: the arrow
    # would be a lie, so the button is the mark instead, and the mark goes
    # where the mark always goes.
    src = sub_once(
        src,
        r"  goBack = \(\) => \{",
        "  /* Read once: the referrer does not change while the page is open. */\n"
        "  get FROM_SITE() {\n"
        "    if (this._fromSite === undefined) {\n"
        "      const r = document.referrer || '';\n"
        "      this._fromSite = !!r && r.indexOf(location.origin) === 0\n"
        "        && r.replace(/[?#].*$/, '') !== location.href.replace(/[?#].*$/, '');\n"
        "    }\n"
        "    return this._fromSite;\n"
        "  }\n"
        "  leavePlanner() {\n"
        "    if (this.FROM_SITE && history.length > 1) history.back();\n"
        "    else window.location.href = '../index.html';\n"
        "  }\n"
        "  goBack = () => {",
        "what the button leaves for")

    # Back is a way out of the card like any other, and takes the same arc.
    src = sub_once(src,
                   r"    if \(this\.state\.sheet\) \{ this\.setState\(\{ sheet: null \}\); return; \}",
                   "    if (this.state.sheet) { this.dismissSheet(); return; }",
                   "back closes the card")

    src = sub_once(src, r"  /\* ---------- map ---------- \*/", SHEET_JS + "\n  /* ---------- map ---------- */",
                   "sheet methods")

    # Every way out of the sheet plays the arc backwards — the close button,
    # the scrim behind it and Escape. A throw is the exception: it has its own
    # direction and keeps it.
    src = sub_once(src, r"      closeSheet: \(\) => this\.setState\(\{ sheet: null \}\),",
                   "      closeSheet: () => this.dismissSheet(),", "close the sheet")
    src = sub_once(
        src,
        r"    this\.onKeyEsc = \(e\) => \{ if \(e\.key === 'Escape'\) "
        r"this\.setState\(\{ sheet: null, overlap: null, navOpen: false \}\); \};",
        "    this.onKeyEsc = (e) => {\n"
        "      if (e.key !== 'Escape') return;\n"
        "      if (this.state.sheet) { this.dismissSheet(); return; }\n"
        "      this.setState({ sheet: null, overlap: null, navOpen: false });\n"
        "    };",
        "escape closes the sheet")

    # The press that opens a sheet is also the measurement it opens from.
    src = sub_once(src, r"    window\.addEventListener\('keydown', this\.onKeyEsc\);",
                   "    window.addEventListener('keydown', this.onKeyEsc);\n"
                   "    document.addEventListener('pointerdown', this.markTap, true);",
                   "tap capture")
    src = sub_once(src, r"    window\.removeEventListener\('keydown', this\.onKeyEsc\);",
                   "    window.removeEventListener('keydown', this.onKeyEsc);\n"
                   "    document.removeEventListener('pointerdown', this.markTap, true);\n"
                   "    this.sheetDragOff();\n"
                   "    clearTimeout(this.throwT);",
                   "tap capture teardown")

    # A sheet that has just opened plays out of the cell it came from.
    src = sub_once(
        src,
        r"    this\.syncFilterDismiss\(\);\n",
        "    this.syncFilterDismiss();\n"
        "    /* The runtime calls this hook with no arguments on one of its\n"
        "       paths, so prevState cannot be trusted to say what changed —\n"
        "       every guard written against it is dead on that path. The sheet\n"
        "       keeps its own last value. The element is found rather than\n"
        "       referenced: it is the one dialog on the page. */\n"
        "    const openSheet = this.state.sheet || null;\n"
        "    if (openSheet !== this.lastSheet) {\n"
        "      this.lastSheet = openSheet;\n"
        "      const el = openSheet ? document.querySelector('[role=\"dialog\"]') : null;\n"
        "      this.setSheetEl(el);\n"
        "      if (el) requestAnimationFrame(() => this.playSheetOpen());\n"
        "      if (this.state.bioOpen) this.setState({ bioOpen: false });\n"
        "      /* And with the short player, whatever the last card was left\n"
        "         showing. */\n"
        "      if (this.state.playerOpen) this.setState({ playerOpen: false });\n"
        "    }\n"
        "    this.syncSheetShell();\n",
        "sheet open animation")

    # ---- the sheet is the page on a phone ----
    src = sub_once(
        src,
        r"      \}, tight \? \{\n"
        r"        display: 'flex', flexDirection: 'column', overflow: 'hidden',\n",
        "      }, sheet ? sheet.vars : null, mob ? {\n"
        "        /* A phone opens it as a modal bottom sheet: the width of the\n"
        "           screen, standing on its bottom edge, as tall as what is in\n"
        "           it and never taller than the screen less the strip that\n"
        "           keeps the page behind it in view. The card stays a grid —\n"
        "           its columns are decided by its own container queries and\n"
        "           nothing here may take that. */\n"
        "        gridTemplateRows: 'auto minmax(0, 1fr)', overflow: 'hidden',\n"
        "        width: '100%', height: 'auto',\n"
        "        maxHeight: 'calc(100dvh - var(--sheet-gap))',\n"
        "        borderRadius: '28px 28px 0 0',\n"
        "        boxShadow: '0 -8px 40px rgba(20,24,14,.28)',\n"
        "        touchAction: 'pan-y'\n"
        "      } : tight ? {\n"
        "        gridTemplateRows: 'auto minmax(0, 1fr)', overflow: 'hidden',\n"
        "        touchAction: 'pan-y',\n",
        "sheet as a page")
    src = sub_once(
        src,
        r"        maxHeight: mob \? 'calc\(100dvh - 150px\)' : 'calc\(100dvh - 48px\)'\n",
        "        maxHeight: 'calc(100dvh - 48px)'\n",
        "sheet height")

    # The rise is played by the container transform now, from the cell.
    src = sub_once(
        src,
        r", animation: 'fp-rise \.28s cubic-bezier\(\.2,0,0,1\)'\n",
        "\n",
        "sheet rise")

    # Surface, corner and elevation belong to the card's own stylesheet. Set
    # here they were inline, and an inline value beats a stylesheet: the dark
    # theme's elevation never arrived, and the card was lit rather than lifted
    # against a dark page.
    src = sub_once(
        src,
        r"        borderRadius: '28px', background: sev \? this\.ART\[sev\.cat\]\.surf"
        r" : 'var\(--card,#F2F0EB\)',\n"
        r"        boxShadow: '0 12px 48px rgba\(20,24,14,\.24\)'\n",
        "",
        "sheet surface")

    # The body scrolls, so a downward drag has to know whether it is at its
    # top before it takes the gesture as a dismissal.
    src = sub_once(
        src,
        r"      sheetBodyStyle: tight \? \{ overflowY: 'auto', minHeight: 0 \} : null,\n",
        "      /* The reference's own wrapper: the size container lives here,\n"
        "         not on the card, or the card's own @container rules for .ac\n"
        "         could never match and every threshold would be out by its\n"
        "         padding. A length, not a percentage — a percentage would have\n"
        "         to resolve against a track that is waiting on the card. */\n"
        "      sheetHostStyle: Object.assign({\n"
        "        containerType: 'inline-size', containerName: 'ac',\n"
        "        width: (S.w || 1440) >= 1000\n"
        "          ? 'min(860px, calc(100vw - 48px))' : 'min(480px, calc(100vw - 48px))'\n"
        "      }, mob ? { width: '100%', height: 'auto', display: 'grid',\n"
        "        alignContent: 'end',\n"
        "        maxHeight: 'calc(100dvh - var(--sheet-gap))' } : null),\n"
        "      sheetRef: this.setSheetEl,\n"
        "      sheetBodyRef: (el) => { this.sheetBodyEl = el; },\n"
        "      sheetBodyStyle: tight ? { overflowY: 'auto', minHeight: 0 } : null,\n",
        "sheet refs")
    src = sub_once(
        src,
        r"        padding: mob \? '16px 16px 124px' : '24px',",
        "        padding: mob ? '0px' : '24px',\n"
        "        overflow: mob ? 'hidden' : undefined,",
        "scrim as a page")
    src = sub_once(
        src,
        r"        justifyItems: 'center', placeContent: 'safe center',",
        "        justifyItems: mob ? 'stretch' : 'center',\n"
        "        /* The sheet stands on the bottom edge of the screen. */\n"
        "        placeContent: mob ? 'end stretch' : 'safe center',",
        "scrim placement")
    return src


def patch_nav(src: str) -> str:
    # One rail across the site. The festival list draws a 96px rail with a
    # 48×32 indicator; the design's is 88 with 56×32. Same numbers here, so
    # moving between the list and a planner does not move the column the page
    # starts at or resize the mark inside it.
    src = sub_once(src, r"      top: 0, bottom: 0, left: 0, width: '88px', flexDirection: 'column',",
                   "      top: 0, bottom: 0, left: 0, width: '96px', flexDirection: 'column',",
                   "rail width")
    # And the same shell at every width. The list runs the rail from 600px up;
    # the design expanded to a 280px drawer past 1240, so the two pages put
    # their content at different columns on the same screen. The rail stands
    # everywhere now and the drawer is what the menu button opens — which is
    # what it already did on narrower screens.
    src = sub_once(src,
                   r"    return w >= 1240 \? \(this\.state\.collapsed \? 'rail' : 'drawer'\) : w >= 640 \? 'rail' : 'bar';",
                   "    return w >= 640 ? 'rail' : 'bar';",
                   "one shell")

    # Scrolling the programme forward cleared every floating thing off the
    # screen: the title bar, the bottom navigation, the back button and the
    # control card with the day, the stars and the filters in it. Reading this
    # page means dragging the grid in two directions, and those controls are
    # what you are dragging it to reach — taking them away on the view that
    # uses them most is the one place that gesture costs something. The title
    # bar still goes, because it names the festival you are already looking
    # at; nothing else does.
    src = sub_once(
        src,
        r"    const chromeOff = mob && !!S\.chromeHidden"
        r" && !S\.navOpen && !S\.filtersOpen && !S\.searchOpen;",
        "    const chromeOff = mob && !!S.chromeHidden"
        " && !S.navOpen && !S.filtersOpen && !S.searchOpen;\n"
        "    /* What the controls do instead, which is stay. */\n"
        "    const barOff = false;",
        "chrome that stays")
    for what in ("bar stays", "back button stays"):
        src = sub_once(
            src,
            r"transform: chromeOff \? 'translateY\(calc\(100% \+ 28px\)\)' : 'none',\n"
            r"(\s*)opacity: chromeOff \? 0 : 1, pointerEvents: chromeOff \? 'none' : 'auto',",
            "transform: barOff ? 'translateY(calc(100% + 28px))' : 'none',\n"
            "          opacity: barOff ? 0 : 1, pointerEvents: barOff ? 'none' : 'auto',",
            what)
    src = sub_once(
        src,
        r"          transform: chromeOff \? 'translate\(-50%, calc\(100% \+ 40px\)\)'"
        r" : 'translateX\(-50%\)',\n"
        r"          opacity: chromeOff \? 0 : 1, pointerEvents: chromeOff \? 'none' : 'auto',",
        "          transform: barOff ? 'translate(-50%, calc(100% + 40px))'"
        " : 'translateX(-50%)',\n"
        "          opacity: barOff ? 0 : 1, pointerEvents: barOff ? 'none' : 'auto',",
        "control card stays")

    # And they arrive where they belong rather than flying in. The three
    # floating things at the foot — the bar, the back button and the control
    # card — animated their size, their offset and their opacity, which on a
    # page you land on is an entrance played every time you arrive and every
    # time the bar changes height under it. M3 asks motion to explain a change
    # the reader made; nothing here is a change the reader made.
    src = sub_once(
        src,
        r"      transition: 'height \.3s cubic-bezier\(\.2,0,0,1\),"
        r" padding \.3s cubic-bezier\(\.2,0,0,1\), width \.3s cubic-bezier\(\.2,0,0,1\),"
        r" left \.3s cubic-bezier\(\.2,0,0,1\), transform \.22s cubic-bezier\(\.3,0,\.8,\.15\),"
        r" opacity \.14s cubic-bezier\(\.3,0,\.8,\.15\)',",
        "      transition: 'none',",
        "bar arrives in place")
    src = sub_once(
        src,
        r"          transition: 'height \.3s cubic-bezier\(\.2,0,0,1\),"
        r" width \.3s cubic-bezier\(\.2,0,0,1\), transform \.22s cubic-bezier\(\.3,0,\.8,\.15\),"
        r" opacity \.14s cubic-bezier\(\.3,0,\.8,\.15\)'",
        "          transition: 'none'",
        "back button arrives in place")
    src = sub_once(
        src,
        r"          transition: 'bottom \.3s cubic-bezier\(\.2,0,0,1\),"
        r" transform \.22s cubic-bezier\(\.3,0,\.8,\.15\),"
        r" opacity \.14s cubic-bezier\(\.3,0,\.8,\.15\)'",
        "          transition: 'none'",
        "control card arrives in place")

    # And the button is drawn as what it does: an arrow for a reader with a
    # page behind them, the mark for one who arrived cold.
    src = sub_once(
        src,
        r"        backIconStyle: \{ width: mini \? '22px' : '24px',"
        r" height: mini \? '22px' : '24px', fill: 'currentColor' \},",
        "        backIcon: this.FROM_SITE ? '#i-back' : '#i-logo',\n"
        "        backLabel: this.FROM_SITE ? 'Go back' : 'Flanner — all festivals',\n"
        "        backIconStyle: this.FROM_SITE\n"
        "          ? { width: mini ? '22px' : '24px', height: mini ? '22px' : '24px',\n"
        "              fill: 'currentColor' }\n"
        "          : { width: mini ? '24px' : '26px', height: mini ? '24px' : '26px',\n"
        "              fill: 'none', color: 'var(--primary,#4C662B)' },",
        "the button is drawn as what it does")

    # The compact design is a page rather than a card: its hero sits on the
    # page's own surface and the only card in it is the About block. So on a
    # phone the container that used to be the card is a plain block, and keeps
    # nothing but the movement it arrives and leaves by.
    src = sub_once(
        src,
        r"      heroCardStyle: \{\n"
        r"        flex: split \? '0 0 ' \+ basis : '2 1 460px', minWidth: 0,"
        r" display: 'flex', flexWrap: 'nowrap',\n"
        r"        flexDirection: heroStack \? 'column' : 'row',\n"
        r"        background: 'var\(--card,#F2F0EB\)', borderRadius: '28px',"
        r" padding: '12px',\n",
        "      heroCardStyle: {\n"
        "        flex: split ? '0 0 ' + basis : '2 1 460px', minWidth: 0,"
        " display: 'flex', flexWrap: 'nowrap',\n"
        "        flexDirection: heroStack ? 'column' : 'row',\n"
        "        background: mob ? 'none' : 'var(--card,#F2F0EB)',\n"
        "        borderRadius: mob ? 0 : '28px', padding: mob ? 0 : '12px',\n",
        "the compact card is a page")

    # What the compact festival design needs to work: which of the two cards
    # is drawn, the state its About block keeps, whether the festival is on
    # right now, and a clip path of its own for its heart — the wide card's is
    # in the page at the same time, and two elements cannot share an id.
    src = sub_once(
        src,
        r"      showHeroFold: true, showControls: true, filterScrim: false,",
        "      phoneCard: mob, deskCard: !mob,\n"
        "      festLive: (function (n) {\n"
        "        return n != null && n >= this.DAY_START && n < this.DAY_END;\n"
        "      }).call(this, this.LIVE_AT),\n"
        "      toProgramme: () => this.setState({ view: 'timetable', prog: 'timetable' }),\n"
        "      aboutClass: S.aboutOpen ? 'about is-open' : 'about',\n"
        "      aboutOpen: String(!!S.aboutOpen),\n"
        "      aboutMoreLabel: S.aboutOpen ? 'Show less' : 'Read more',\n"
        "      aboutClipStyle: { maxBlockSize: S.aboutOpen\n"
        "        ? ((S.aboutFull || 800) + 'px') : 'calc(3 * 1.45em)' },\n"
        "      /* Whether the introduction is longer than the three lines\n"
        "         the card shows. It cannot be known before it is laid out,\n"
        "         so it is measured on the frame after each render and only\n"
        "         written back when the answer changes — which also catches a\n"
        "         rotation, since the page re-renders on one. Until the first\n"
        "         measurement the button is there: taking a control away is\n"
        "         cheaper to the eye than putting one in. */\n"
        "      aboutFolds: S.aboutFolds !== false,\n"
        "      aboutClipRef: (el) => {\n"
        "        this.aboutClipEl = el;\n"
        "        if (!el) return;\n"
        "        requestAnimationFrame(() => {\n"
        "          const p = el.firstElementChild;\n"
        "          if (!p) return;\n"
        "          /* against three lines of its own leading, not against\n"
        "             the box: the box is what opens, and measuring it\n"
        "             during the 340ms it takes answers for a height it is\n"
        "             halfway through leaving. */\n"
        "          const lh = parseFloat(getComputedStyle(p).lineHeight) || 19;\n"
        "          const folds = p.scrollHeight > lh * 3 + 2;\n"
        "          if (folds !== (this.state.aboutFolds !== false))\n"
        "            this.setState({ aboutFolds: folds });\n"
        "        });\n"
        "      },\n"
        "      toggleAbout: () => {\n"
        "        const el = this.aboutClipEl;\n"
        "        const p = el && el.firstElementChild;\n"
        "        this.setState(s => ({ aboutOpen: !s.aboutOpen,\n"
        "          aboutFull: p ? p.scrollHeight : s.aboutFull }));\n"
        "      },\n"
        "      heartClipId2: 'fest-heart-2',\n"
        "      heartClipUrl2: 'url(#fest-heart-2)',\n"
        "      /* The Lineup row. An act is its artwork in the stage's own\n"
        "         tones — the tones its cell, its row and its card are drawn\n"
        "         in — its name, and when it plays; a starred act wears the\n"
        "         ring and the tick. Pressing one opens that act's card, the\n"
        "         same card the timetable opens. */\n"
        "      lineupTotal: this.EVENTS.length,\n"
        "      seeAll: () => this.setState({ view: 'list', prog: 'list' }),\n"
        "      lineup: this.LINEUP.map(ev => {\n"
        "        const c = this.stageColor(ev.s), A = this.ART[ev.cat];\n"
        "        const st = this.STAGES[ev.s], planned = !!S.star[ev.id];\n"
        "        const day = this.DAYS.length > 1\n"
        "          ? (this.DAYS.find(d => d.id === ev.d) || {}).short + ' ' : '';\n"
        "        return {\n"
        "          name: ev.title, when: day + ev.from, planned: planned,\n"
        "          motif: A.motif,\n"
        "          aria: ev.title + ', ' + day + ev.from + ' at ' + st.name\n"
        "            + (planned ? ', in your plan' : ''),\n"
        "          avatarClass: planned ? 'avatar avatar--on' : 'avatar',\n"
        "          avatarStyle: { background: c.artBg, '--accent': c.art2 },\n"
        "          artStyle: {\n"
        "            '--art-bg': c.artBg, '--art-1': c.art1, '--art-2': c.art2,\n"
        "            '--art-3': c.art3, '--art-ink': c.artInk\n"
        "          },\n"
        "          onOpen: () => this.setState({ sheet: ev.id })\n"
        "        };\n"
        "      }),\n"
        "      showHeroFold: true, showControls: true, filterScrim: false,",
        "the compact card's own state")

    # ---- one bar height, everywhere ----
    # The bar was 76 tall with its labels and 50 without, and the home page's
    # was 80: three heights for one component. M3's navigation bar is 80dp on
    # a handset, but this one floats over the page rather than sitting on its
    # edge — it is a capsule with air under it, and at 80 it took a fifth of a
    # phone's height for four words. 64 and 48, and the home page states the
    # same two.
    src = sub_once(
        src,
        r"      height: mini \? '50px' : '76px', padding: mini \? '5px' : '6px',",
        "      height: mini ? '48px' : '64px', padding: mini ? '5px' : '6px',",
        "bar height")
    src = sub_once(
        src,
        r"          left: clusterLeft, width: backW \+ 'px', height: \(mini \? 50 : 76\) \+ 'px',",
        "          left: clusterLeft, width: backW + 'px', height: (mini ? 48 : 64) + 'px',",
        "back button height")

    # ---- a phone opens on Info ----
    # The grid is what the planner is for, and it is also the last thing you
    # want first: a wall of cells with no idea which festival it is, when it
    # opens or what the weather will do. A phone lands on Info — the festival
    # card and the forecast, one screen of it — and the programme is the tap
    # the bar is there to make. A wide screen still opens on the programme,
    # because it shows both at once.
    src = sub_once(
        src,
        r"    const view = S\.view \|\| this\.props\.startView \|\| 'timetable';",
        "    const view = S.view\n"
        "      || (mob ? 'info' : (this.props.startView || 'timetable'));",
        "a phone opens on Info")

    # ---- the bar switches the view ----
    # The grid and the list are the same programme in two shapes, and the
    # shape was chosen from a pair of icon buttons riding on the day switcher
    # while the bar underneath held one destination for both. They are two
    # destinations now — Schedule for the grid, Programme for the list — which
    # is what the bar is for, and the pair of buttons is gone from the card,
    # leaving it the day, the stars and the filters, which both views keep.
    src = sub_once(
        src,
        r"    const destDefs = \[\n"
        r"      \{ id: 'info', label: 'Info', icon: '#i-info' \},\n"
        r"      \{ id: 'timetable', label: 'Programme', icon: '#i-cal',"
        r" badge: shown\.length \},\n"
        r"      \{ id: 'map', label: 'Map', icon: '#i-pin',"
        r" badge: this\.STAGES\.length \}\n"
        r"    \];",
        "    const destDefs = mob\n"
        "      ? [\n"
        "        { id: 'info', label: 'Info', icon: '#i-info' },\n"
        "        { id: 'timetable', label: 'Schedule', icon: '#i-cal',"
        " badge: shown.length },\n"
        "        { id: 'list', label: 'Programme', icon: '#i-list',"
        " badge: shown.length },\n"
        "        { id: 'map', label: 'Map', icon: '#i-pin',"
        " badge: this.STAGES.length }\n"
        "      ]\n"
        "      : [\n"
        "        { id: 'info', label: 'Info', icon: '#i-info' },\n"
        "        { id: 'timetable', label: 'Programme', icon: '#i-cal',"
        " badge: shown.length },\n"
        "        { id: 'map', label: 'Map', icon: '#i-pin',"
        " badge: this.STAGES.length }\n"
        "      ];",
        "two programme destinations")
    # Pressing the list destination puts the programme in that shape.
    src = sub_once(
        src,
        r"          const toProg = d\.id === 'timetable', toInfo = d\.id === 'info';\n"
        r"          const next = \{ view: d\.id, navOpen: false, sheet: null,"
        r" filtersOpen: false \};",
        "          const toProg = d.id === 'timetable' || d.id === 'list';\n"
        "          const toInfo = d.id === 'info';\n"
        "          const next = { view: d.id, navOpen: false, sheet: null,\n"
        "            filtersOpen: false };\n"
        "          if (d.id === 'timetable' || d.id === 'list') next.prog = d.id;",
        "the destination sets the shape")
    # The pair of buttons leaves the card with the day and the two filters.
    src = sub_once(
        src,
        r"    \]\.filter\(t => !\(\(split \|\| mob\) && t\.id === 'map'\)\)\.map\(t => \{",
        "    ].filter(t => !((split || mob) && t.id === 'map'))\n"
        "      .filter(t => !mob)\n"
        "      .map(t => {",
        "no view tabs on the phone")

    # And the bar carries destinations only. Its fourth cell opened the rail as
    # a drawer, which on this page is a panel of the three destinations already
    # standing beside it plus the utilities — so the cell spent a quarter of
    # the bar on a second way to reach what the bar already reaches.
    src = sub_once(
        src,
        r"    const utils = navShown === 'bar'\n"
        r"      \? \[\{\n"
        r"        label: 'More', icon: '#i-more', style: utilStyle,"
        r" iconStyle: utilIcon, showLabel: true,\n"
        r"        labelStyle: \{\n"
        r"          whiteSpace: 'nowrap', height: mini \? '0px' : '14px',"
        r" opacity: mini \? 0 : 1, overflow: 'hidden',\n"
        r"          transition: 'height \.3s cubic-bezier\(\.2,0,0,1\),"
        r" opacity \.2s cubic-bezier\(\.2,0,0,1\)'\n"
        r"        \},\n"
        r"        onClick: \(\) => this\.setState\(\{ navOpen: true \}\)\n"
        r"      \}\]\n",
        "    const utils = navShown === 'bar'\n"
        "      ? []\n",
        "bar without More")
    # One row, not two. The day, the stars and the filters are the same
    # decision — which of the programme am I looking at — so they stand
    # together on one line, the way the shape switch used to stand beside the
    # day: the pills take the room, the two controls close the pill at its end.
    src = sub_once(
        src,
        r"          gridTemplateAreas: '\"picks picks\" \"days view\"',",
        "          gridTemplateAreas: '\"days picks\"',",
        "one control row")
    # And one surface under the row, not two boxes meeting: joined skins left a
    # seam down the middle, and each carried its own border and its own shadow
    # to draw it with. The card is the row; what stands in it is transparent.
    src = sub_once(
        src,
        r"          rowGap: '8px', columnGap: 0,\n"
        r"          padding: 0, background: 'none', border: 0, boxShadow: 'none'\n"
        r"        \},",
        "          rowGap: 0, columnGap: 0, alignItems: 'center',\n"
        "          padding: '5px', borderRadius: '28px'\n"
        "        }, cardSkin),",
        "one surface for the row")
    src = sub_once(
        src,
        r"        controlsBarStyle: \{\n"
        r"          display: 'grid', gridTemplateColumns: 'minmax\(0,1fr\) auto',",
        "        controlsBarStyle: Object.assign({\n"
        "          display: 'grid', gridTemplateColumns: 'minmax(0,1fr) auto',",
        "the row is the card")
    src = sub_once(
        src,
        r"        actionsGroupStyle: Object\.assign\(\{\n"
        r"          gridArea: 'picks', justifySelf: 'end', display: 'flex',\n"
        r"          alignItems: 'center', gap: '12px',\n"
        r"          width: 'auto', marginInline: 0, padding: '5px', borderRadius: '28px'\n"
        r"        \}, cardSkin\),",
        "        actionsGroupStyle: {\n"
        "          gridArea: 'picks', display: 'flex', alignItems: 'center',\n"
        "          gap: '2px', width: 'auto', marginInline: 0, padding: 0,\n"
        "          background: 'none', border: 0, boxShadow: 'none'\n"
        "        },",
        "the two controls close the row")
    src = sub_once(
        src,
        r"        daysGroupStyle: Object\.assign\(\{\}, cardSkin, \{\n"
        r"          gridArea: 'days', position: 'relative', display: 'flex',"
        r" gap: '4px', minWidth: 0,\n"
        r"          padding: '5px', borderStartStartRadius: '28px',"
        r" borderEndStartRadius: '28px',\n"
        r"          borderStartEndRadius: 0, borderEndEndRadius: 0, borderInlineEnd: 0\n"
        r"        \}\),",
        "        daysGroupStyle: {\n"
        "          gridArea: 'days', position: 'relative', display: 'flex',\n"
        "          gap: '4px', minWidth: 0, padding: 0,\n"
        "          background: 'none', border: 0, boxShadow: 'none'\n"
        "        },",
        "the day group has no skin of its own")
    # The puck was measured off a group that carried 5px of padding on every
    # side; the padding belongs to the row now, so the puck starts at the
    # group's own corner and each day is a clean third of it.
    src = sub_once(
        src,
        r"        daysPuckStyle: \{\n"
        r"          position: 'absolute', top: '5px', left: '5px', zIndex: 0,"
        r" pointerEvents: 'none',\n"
        r"          width: 'calc\(\(100% - ' \+ \(10 \+ \(this\.DAYS\.length - 1\) \* 4\)"
        r" \+ 'px\) / '\n"
        r"            \+ this\.DAYS\.length \+ '\)', height: '40px', borderRadius: '20px',",
        "        daysPuckStyle: {\n"
        "          position: 'absolute', top: 0, left: 0, zIndex: 0,"
        " pointerEvents: 'none',\n"
        "          width: 'calc((100% - ' + ((this.DAYS.length - 1) * 4) + 'px) / '\n"
        "            + this.DAYS.length + ')', height: '40px', borderRadius: '20px',",
        "the puck sits on the day")
    # A button keeps the browser's own padding unless it is told not to, and a
    # 20px chip with 6px of it either side has 8px of content box for a 15px
    # glyph — which overflows, and an overflowing item is aligned to the start
    # rather than centred, so the star sat 3.5px right of its circle.
    src = sub_once(
        src,
        r"      position: 'absolute', bottom: starGap \+ 'px',"
        r" insetInlineEnd: starGap \+ 'px',\n"
        r"              display: 'grid', placeItems: 'center',\n",
        "      position: 'absolute', bottom: starGap + 'px',"
        " insetInlineEnd: starGap + 'px',\n"
        "              display: 'grid', placeItems: 'center', padding: 0,\n",
        "the star sits in the middle of its circle")
    src = sub_once(
        src,
        r"      flex: 'none', display: 'grid', placeItems: 'center',"
        r" width: '40px', height: '40px',\n"
        r"      border: 0, borderRadius: '50%',",
        "      flex: 'none', display: 'grid', placeItems: 'center',"
        " width: '40px', height: '40px',\n"
        "      border: 0, padding: 0, borderRadius: '50%',",
        "the icon buttons keep no padding")
    # The weather chip in the title bar goes to the weather. It took the reader
    # to Info and unfolded the card, and then left them at the top of the page
    # with the festival card in the way — on a phone the two cards are stacked,
    # so the one that was asked for has to be brought up. The frame after the
    # state lands is when the card exists to be scrolled to.
    src = sub_once(
        src,
        r"        toggleWeather: \(\) => this\.setState\(\{ view: 'info',"
        r" weatherOpen: true, note: 'Festival info' \}\),",
        "        toggleWeather: () => this.setState(\n"
        "          { view: 'info', weatherOpen: true, note: 'Weather' },\n"
        "          () => requestAnimationFrame(() => {\n"
        "            const el = document.getElementById('fp-weather');\n"
        "            if (!el) return;\n"
        "            const top = el.getBoundingClientRect().top + window.scrollY\n"
        "              - ((this.state.headerH || 0) + 12);\n"
        "            window.scrollTo({ top: Math.max(0, top), behavior: 'smooth' });\n"
        "          })\n"
        "        ),",
        "the weather chip goes to the weather")

    # The starred cell flies to the button that counts it. The two call sites
    # are the same line — the cell in the grid and the row in the list — so
    # they are taken one at a time.
    for what in ("cell flies to the plan", "row flies to the plan"):
        src = sub_once(
            src,
            r"onStar: \(e\) => \{ e\.stopPropagation\(\);"
            r" this\.starToggle\(ev\.id, e\.currentTarget\.getBoundingClientRect\(\)\); \}",
            "onStar: (e) => {\n"
            "          e.stopPropagation();\n"
            "          this.starToggle(ev.id, e.currentTarget.getBoundingClientRect(),\n"
            "            e.currentTarget);\n"
            "        }",
            what)
    src = sub_once(
        src,
        r"  starToggle\(id, rect\) \{\n"
        r"    const ev = this\.EVENTS\.find\(x => x\.id === id\);",
        "  starToggle(id, rect, srcEl) {\n"
        "    const ev = this.EVENTS.find(x => x.id === id);\n"
        "    /* The cell the star was pressed in, which is what travels to the\n"
        "       plan — measured before the state changes it. The grid only: a\n"
        "       row in the list is the width of the screen, and a thing that\n"
        "       wide being drawn through a 40px button is a curtain closing\n"
        "       rather than an act being put somewhere. */\n"
        "    const host = srcEl && srcEl.closest\n"
        "      ? srcEl.closest('[role=\"button\"]') : null;\n"
        "    const inGrid = host && !host.closest('li');\n"
        "    if (inGrid && !this.state.star[id]) this.flyToPlan(host);",
        "the star knows what cell it was pressed in")

    # Each press throws its own sparks, in its own layer.
    src = sub_once(
        src,
        r"        next\.burst = id;\n"
        r"        /\* The sparks are the stage's colours, so the blast belongs\n"
        r"           to the cell it came from rather than to a fixed green\. \*/\n"
        r"        const sp = this\.stageColor\(ev\.s\);\n"
        r"        next\.burstParts = this\.makeBurst\(\n"
        r"          \[sp\.dot, sp\.bg, sp\.planBg, sp\.planFg, sp\.dot\]\);\n"
        r"        /\* The burst lives in a fixed layer over the page, so it escapes the\n"
        r"           scrolling panes and the dialog instead of being clipped by them\. \*/\n"
        r"        next\.burstAt = rect\n"
        r"          \? \{ x: Math\.round\(rect\.left \+ rect\.width / 2\),"
        r" y: Math\.round\(rect\.top \+ rect\.height / 2\) \}\n"
        r"          : null;\n"
        r"        next\.burstColor = this\.stageColor\(ev\.s\)\.planBg;",
        "        next.burst = id;\n"
        "        /* The sparks are the stage's colours, so the blast belongs\n"
        "           to the cell it came from rather than to a fixed green — and\n"
        "           they are thrown into a layer of their own, over the page,\n"
        "           clear of the scrolling panes and of each other. */\n"
        "        const sp = this.stageColor(ev.s);\n"
        "        this.spawnBurst(rect, [sp.dot, sp.bg, sp.planBg, sp.planFg, sp.dot],\n"
        "          sp.planBg);",
        "a layer per star")
    src = sub_once(
        src,
        r"      next\.burstParts = this\.makeBurst\(this\.HEART_COLORS\);\n"
        r"      next\.burstAt = rect \? \{ x: Math\.round\(rect\.left \+ rect\.width / 2\),"
        r" y: Math\.round\(rect\.top \+ rect\.height / 2\) \} : null;\n"
        r"      next\.burstColor = 'var\(--heart,#8F4C0A\)';",
        "      this.spawnBurst(rect, this.HEART_COLORS, 'var(--heart,#8F4C0A)');",
        "a layer for the festival heart")
    src = sub_once(
        src,
        r"      burstOpen: !!S\.burst && !!S\.burstAt,",
        "      /* The old single-slot layer is inert: every blast now brings\n"
        "         its own. */\n"
        "      burstOpen: false,",
        "the old burst layer stands down")

    # ---- the title bar stays ----
    # It hid itself on the way down and came back on the way up, which is a
    # pattern for a page of text rather than for a grid you drag in two
    # directions: every diagonal drag read as forward, and hiding it changed
    # the height of the page, which fired the scroll that brought it back. It
    # is 56px, it names the festival and it holds the weather and the search.
    # It stays, and the rule below is what is left of the mechanism — the bar
    # at the foot still compacts itself, which costs nothing and moves nothing.
    src = sub_once(
        src,
        r"    const chromeOff = mob && !!S\.chromeHidden"
        r" && !S\.navOpen && !S\.filtersOpen && !S\.searchOpen;\n"
        r"    /\* What the controls do instead, which is stay\. \*/\n"
        r"    const barOff = false;",
        "    /* Both of them stay: the title bar at the top and the three\n"
        "       floating things at the foot. */\n"
        "    const chromeOff = false, barOff = false;",
        "the title bar stays")

    # ---- the title bar hides once, not once a frame ----
    # Hiding it changes the height of the page, which fires a scroll of its
    # own, which arrives as a scroll in the other direction and brings it back
    # — and at the end of the grid, where the scroll position is clamped, the
    # two take turns for as long as the finger is down. That is the shudder.
    # Three things settle it: the echo is ignored for as long as the bar takes
    # to move, the thresholds are a real gesture rather than 2px, and at the
    # end of the scroll the bar is left where it is, since there is nothing
    # further to clear it for.
    src = sub_once(
        src,
        r"  scrollSignal\(key, y\) \{\n"
        r"    if \(!this\.lastPos\) this\.lastPos = \{\};\n"
        r"    const last = this\.lastPos\[key\] \|\| 0;\n"
        r"    const d = y - last;\n"
        r"    /\* A small nudge is enough: 2px forward clears the chrome, 2px back brings\n"
        r"       it straight down again\. \*/\n"
        r"    if \(Math\.abs\(d\) < 2\) return;\n"
        r"    this\.lastPos\[key\] = y;\n"
        r"    const mini = y > 12 && d > 0;\n"
        r"    /\* On the programme page the chrome clears out entirely once you are\n"
        r"       reading forward, and slides back the moment you scroll back\. \*/\n"
        r"    const prog = this\.state\.view === 'timetable' \|\| this\.state\.view === 'list'"
        r" \|\| this\.state\.view == null;\n"
        r"    const hide = prog && y > 16 && d > 0;\n"
        r"    const next = \{\};\n"
        r"    if \(mini !== this\.state\.barMini\) next\.barMini = mini;\n"
        r"    if \(hide !== !!this\.state\.chromeHidden\) next\.chromeHidden = hide;\n"
        r"    if \(Object\.keys\(next\)\.length\) this\.setState\(next\);\n"
        r"  \}",
        "  scrollSignal(key, y, el) {\n"
        "    if (!this.lastPos) this.lastPos = {};\n"
        "    const last = this.lastPos[key] || 0;\n"
        "    const d = y - last;\n"
        "    if (Math.abs(d) < 2) return;\n"
        "    this.lastPos[key] = y;\n"
        "    /* The scroll the bar's own movement fires, arriving in the other\n"
        "       direction: ignored for as long as that movement lasts. */\n"
        "    const now = performance.now();\n"
        "    if (this.chromeAt && now - this.chromeAt < 320) return;\n"
        "    /* At the end of the scroll the position is clamped and every\n"
        "       further event is that echo, so the bar stays as it is. */\n"
        "    const atEnd = !!el\n"
        "      && (el.scrollTop + el.clientHeight >= el.scrollHeight - 16);\n"
        "    const mini = y > 12 && d > 0;\n"
        "    const prog = this.state.view === 'timetable' || this.state.view === 'list'"
        " || this.state.view == null;\n"
        "    /* A gesture, not a nudge: 10px of travel each way. */\n"
        "    let hide = !!this.state.chromeHidden;\n"
        "    if (prog && !atEnd) {\n"
        "      if (d > 10 && y > 24) hide = true;\n"
        "      else if (d < -10) hide = false;\n"
        "    }\n"
        "    const next = {};\n"
        "    if (mini !== this.state.barMini) next.barMini = mini;\n"
        "    if (hide !== !!this.state.chromeHidden) {\n"
        "      next.chromeHidden = hide;\n"
        "      this.chromeAt = now;\n"
        "    }\n"
        "    if (Object.keys(next).length) this.setState(next);\n"
        "  }",
        "the title bar hides once")
    src = sub_once(
        src,
        r"  onScrollerScroll = \(e\) => \{ this\.scrollSignal\('grid',"
        r" e\.currentTarget\.scrollTop\); \};",
        "  onScrollerScroll = (e) => {\n"
        "    const el = e.currentTarget;\n"
        "    this.scrollSignal('grid', el.scrollTop, el);\n"
        "  };",
        "the scroller reports its end")
    src = sub_once(
        src,
        r"        switcherStyle: Object\.assign\(\{\}, cardSkin, \{\n"
        r"          gridArea: 'view', position: 'relative', display: 'flex',"
        r" alignItems: 'center', gap: '12px',\n"
        r"          marginInlineStart: 0, padding: '5px 5px 5px 10px',\n"
        r"          borderStartEndRadius: '28px', borderEndEndRadius: '28px',\n"
        r"          borderStartStartRadius: 0, borderEndStartRadius: 0,"
        r" borderInlineStart: 0, boxShadow: 'none'\n"
        r"        \}\),",
        "        switcherStyle: { display: 'none' },",
        "no switcher on the phone")
    # And the two of them are glyphs until they are on. A resting tonal circle
    # under each says something is set when nothing is; the container arrives
    # with the state, which is the M3 order — a toggle is unselected until it
    # is selected, and then it fills.
    src = sub_once(
        src,
        r"        picksBtnStyle: Object\.assign\(\{\}, V\.picksBtnStyle,"
        r" \{ width: '40px', height: '40px' \}\),\n"
        r"        filterBtnStyle: Object\.assign\(\{\}, V\.filterBtnStyle,"
        r" \{ width: '40px', height: '40px' \}\),",
        "        picksBtnStyle: Object.assign({}, V.picksBtnStyle, {\n"
        "          width: '40px', height: '40px',\n"
        "          background: S.onlyPicks ? 'var(--sec,#DCE8C0)' : 'transparent',\n"
        "          color: S.onlyPicks\n"
        "            ? 'var(--on-sec,#1F2D0A)' : 'var(--on-var,#494E42)'\n"
        "        }),\n"
        "        filterBtnStyle: Object.assign({}, V.filterBtnStyle, {\n"
        "          width: '40px', height: '40px',\n"
        "          background: (S.filtersOpen || hasFilters)\n"
        "            ? 'var(--sec,#DCE8C0)' : 'transparent',\n"
        "          color: (S.filtersOpen || hasFilters)\n"
        "            ? 'var(--on-sec,#1F2D0A)' : 'var(--on-var,#494E42)'\n"
        "        }),",
        "quiet until they are on")

    # The bar keeps its compact height for the whole of the programme. It
    # already compacted itself the moment you scrolled the grid and came back
    # to full height the moment you scrolled the other way, which on a page
    # you read by dragging in two directions is a bar that changes size under
    # your thumb. Reading the timetable is the one thing this page is for, so
    # there it is small; Info and Map, which you land on rather than scroll
    # through, stand at full height until you push them up — the design's own
    # behaviour, and all that is wrong with it there is where it starts. Which
    # page you are on is resolved the way the view itself resolves it, a
    # phone's default being Info: taking the design's own default here left
    # the bar compact on the page a phone lands on.
    src = sub_once(
        src,
        r"    const mini = mob && S\.barMini;",
        "    const progNow = S.view\n"
        "      || (mob ? 'info' : (this.props.startView || 'timetable'));\n"
        "    const mini = mob && (S.barMini"
        " || progNow === 'timetable' || progNow === 'list');",
        "bar height on the programme")

    src = sub_once(src,
                   r"width: navShown === 'rail' \? '56px' : '54px', height: navShown === 'rail' \? '32px' : '30px'",
                   "width: navShown === 'rail' ? '48px' : '54px',"
                   " height: navShown === 'rail' ? '32px' : '30px'",
                   "rail indicator")
    src = sub_once(
        src,
        r"      paddingInlineStart: navShown === 'bar' \? '0px' : navShown === 'rail' && !overlay \? '88px'"
        r" : isDrawer \? '280px' : mode === 'rail' \? '88px' : '0px',",
        "      paddingInlineStart: navShown === 'bar' ? '0px'"
        " : navShown === 'rail' && !overlay ? '96px'\n"
        "        : isDrawer ? '280px' : mode === 'rail' ? '96px' : '0px',",
        "rail gutter")

    # The runtime calls componentDidUpdate with no arguments on one of its
    # paths, and the design's first line reads prevState.searchOpen — which
    # throws, and takes the rest of the method with it: the map never
    # re-measures, the filter dismissal never syncs, and now the indicator
    # would never move. Reading it defensively costs nothing and the design's
    # own behaviour is unchanged.
    src = sub_once(src,
                   r"if \(this\.state\.searchOpen && !prevState\.searchOpen && this\.searchEl\)",
                   "if (this.state.searchOpen && !(prevState && prevState.searchOpen)"
                   " && this.searchEl)",
                   "update guard")

    src = sub_once(src, r"  scrollTop\(mutate\) \{", NAV_JS + "\n  scrollTop(mutate) {",
                   "nav indicator methods")

    # ---- when it is measured, and when it moves ----
    src = sub_once(src, r"      this\.scrollSignal\('win', y\);",
                   "      this.scrollSignal('win', y);\n      this.navSpy();",
                   "nav spy on scroll")
    src = sub_once(src, r"      this\.mapDo\(m => m\.invalidateSize\(\)\);\n    \};",
                   "      this.mapDo(m => m.invalidateSize());\n"
                   "      this.scheduleNavPill();\n    };",
                   "nav pill on resize")
    src = sub_once(src,
                   r"    this\.setState\(this\.viewport\(\)\);\n  \}",
                   "    this.setState(this.viewport());\n"
                   "    requestAnimationFrame(() => {\n"
                   "      this.navWatch([document.getElementById('fp-hero'),\n"
                   "      document.getElementById('fp-views')]);\n"
                   "      this.navBoxWatch();\n"
                   "      this.scheduleNavPill();\n"
                   "    });\n  }",
                   "nav pill on mount")
    src = sub_once(src,
                   r"  componentDidUpdate\(prevProps, prevState\) \{\n    this\.loadWeather\(\);",
                   "  componentDidUpdate(prevProps, prevState) {\n    this.loadWeather();\n"
                   "    this.navWatch([document.getElementById('fp-hero'),\n"
                   "      document.getElementById('fp-views')]);\n"
                   "    this.navBoxWatch();\n"
                   "    this.scheduleNavPill();\n    this.navSpy();\n"
                   "    this.measureBio();",
                   "nav pill on update")
    src = sub_once(src,
                   r"    if \(this\.heroRO\) \{ this\.heroRO\.disconnect\(\); this\.heroRO = null; \}",
                   "    if (this.heroRO) { this.heroRO.disconnect(); this.heroRO = null; }\n"
                   "    if (this.heroSpy) { this.heroSpy.disconnect(); this.heroSpy = null; }\n"
                   "    if (this.navRO) { this.navRO.disconnect(); this.navRO = null; }\n"
                   "    cancelAnimationFrame(this.navPillRaf || 0);\n"
                   "    clearTimeout(this.navPillTimer);",
                   "nav spy teardown")

    # ---- the destination that is current ----
    src = sub_once(src, r"    const activeDest = view === 'list' \? 'timetable' : view;",
                   "    this.navShown = navShown;\n"
                   "    const activeDest = (navShown !== 'bar' && view !== 'map' && S.spy)\n"
                   "      ? S.spy\n"
                   "      /* On a phone the list is a destination of its own,\n"
                   "         so it lights its own cell rather than the grid's. */\n"
                   "      : (view === 'list' ? (mob ? 'list' : 'timetable') : view);",
                   "active destination")

    # ---- the mark itself moves, so no destination carries one ----
    # Until it has been measured — and if this browser has no observer to
    # measure it with — the design's own per-destination fill stands, so the
    # current destination is never left unmarked.
    src = sub_once(src,
                   r"        background: on \? 'var\(--sec,#DCE8C0\)' : 'transparent', color: on \? 'var\(--on-sec,#1F2D0A\)'",
                   "        background: on && !S.navPill ? 'var(--sec,#DCE8C0)' : 'transparent',"
                   " zIndex: 1, color: on ? 'var(--on-sec,#1F2D0A)'",
                   "drawer destination fill")
    src = sub_once(src,
                   r"        border: 0, background: 'none', color: on \? 'var\(--on-sec,#1F2D0A\)'",
                   "        border: 0, background: 'none', position: 'relative', zIndex: 1,"
                   " color: on ? 'var(--on-sec,#1F2D0A)'",
                   "rail destination fill")
    src = sub_once(src,
                   r"        flex: '1 1 0', minWidth: 0, height: '100%', border: 0, background: 'none', borderRadius: '22px',",
                   "        flex: '1 1 0', minWidth: 0, height: '100%', border: 0, background: 'none',"
                   " borderRadius: '22px', position: 'relative', zIndex: 1,",
                   "bar destination fill")
    src = sub_once(src,
                   r"borderRadius: '16px', background: on \? 'var\(--sec,#DCE8C0\)' : 'transparent', transition: 'background \.2s cubic-bezier\(\.2,0,0,1\)' \};",
                   "borderRadius: '16px',"
                   " background: on && !S.navPill ? 'var(--sec,#DCE8C0)' : 'transparent',"
                   " transition: 'background .2s cubic-bezier(.2,0,0,1)' };",
                   "icon indicator fill")

    # ---- the element, and the box it is placed in ----
    src = sub_once(
        src,
        r"      navScrollStyle: navShown === 'drawer'\n"
        r"        \? \{ display: 'grid', gap: '4px', flexShrink: 0, minBlockSize: 'auto' \}\n"
        r"        : navShown === 'rail'\n"
        r"          \? \{ display: 'grid', gap: '8px', justifyItems: 'center', width: '100%' \}\n"
        r"          : \{ display: 'flex', flex: '1 1 auto', minWidth: 0, height: '100%' \},",
        "      navListRef: (el) => { this.navListEl = el; },\n"
        "      /* Emphasised spring for the travel, standard easing for the\n"
        "         shape it arrives in — M3 moves and morphs on different\n"
        "         curves. Hidden until it has been measured, so it never\n"
        "         appears at the top-left corner first. */\n"
        "      navPillStyle: S.navPill ? {\n"
        "        position: 'absolute', insetInlineStart: 0, top: 0, zIndex: 0,\n"
        "        width: S.navPill.w + 'px', height: S.navPill.h + 'px',\n"
        "        transform: 'translate(' + S.navPill.x + 'px,' + S.navPill.y + 'px)',\n"
        "        borderRadius: S.navPill.r + 'px',\n"
        "        background: 'var(--sec,#DCE8C0)', pointerEvents: 'none',\n"
        "        transition: 'transform .42s cubic-bezier(.42,1.67,.21,.9),'\n"
        "          + ' width .3s cubic-bezier(.2,0,0,1), height .3s cubic-bezier(.2,0,0,1),'\n"
        "          + ' border-radius .3s cubic-bezier(.2,0,0,1)'\n"
        "      } : { display: 'none' },\n"
        "      navScrollStyle: Object.assign({ position: 'relative' }, navShown === 'drawer'\n"
        "        ? { display: 'grid', gap: '4px', flexShrink: 0, minBlockSize: 'auto' }\n"
        "        : navShown === 'rail'\n"
        "          ? { display: 'grid', gap: '8px', justifyItems: 'center', width: '100%' }\n"
        "          : { display: 'flex', flex: '1 1 auto', minWidth: 0, height: '100%' }),",
        "nav indicator style")
    return src


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
# Each stage gets both of the design's schemes. Its own three palettes are
# stated twice — once for the light theme and once under [data-theme=dark],
# where a container drops to tone 30 and its text rises to 85 — so the grid
# follows the theme the way every other colour on the page does. The tones are
# read off the design's own pairs: light 90/16, 28/95 and a 79 for the pin;
# dark 30/85, 85/16 and a 62.
ROLES = (
    #  key       light (chroma, tone)   dark (chroma, tone)
    ("bg",      (21, 90),              (24, 30)),
    ("fg",      (23, 16),              (30, 85)),
    ("dot",     (39, 79),              (30, 62)),
    ("planBg",  (36, 28),              (30, 85)),
    ("planFg",  (15, 95),              (23, 16)),
    # The artwork. The drawing is ours — an SVG reading five variables — so it
    # takes the stage's hue at the tones the design drew it in, which is what
    # M3 means by adjusting an existing colour: hold the tonal relationships,
    # move the hue. Read off the design's own music artwork: 93/89/40/79/27 in
    # the light theme, 17/41/81/61/89 in the dark.
    #
    # It is drawn in the dark scheme under both themes — see ALWAYS_DARK. The
    # hero is a dark surface whichever theme the page is in, because a 46%
    # wash sits over it and the name on top is white; painting the ground in
    # the light scheme meant tinting a light picture down to something with no
    # colour left in it, which is the grey the card used to open with. Dark
    # tones under the same wash keep the stage's hue.
    ("artBg",   (12, 93),              (14, 17)),
    ("art1",    (28, 89),              (26, 41)),
    ("art2",    (36, 40),              (30, 81)),
    ("art3",    (39, 79),              (25, 61)),
    ("artInk",  (40, 27),              (30, 89)),
    # The line over the artwork. Light in both themes, because the hero is
    # dark in both: a 46% scrim sits over every artwork.
    ("hero",    (18, 95),              (30, 88)),
)

# Roles that take their dark value in both themes: the five the artwork reads.
ALWAYS_DARK = {"artBg", "art1", "art2", "art3", "artInk"}



# ── the festival's own hue ────────────────────────────
# The design is drawn in one green, and that green is the card system's, not
# any festival's. A planner is one festival, so it is drawn in that festival's
# colour instead — data/festivals.json carries the accent each organiser
# publishes, and the whole scheme turns to its hue.
#
# What turns is the hue and only the hue. Every token keeps the lightness and
# the chroma the design gave it, so every contrast pair the design was drawn
# against still holds; the page changes colour without changing tone. And only
# what is in the seed's own hue turns: the warm heart, the pink plan sheet,
# the amber and violet strands are deliberate second colours, and a rotation
# that swept them up would flatten the scheme into one hue.
SEED_HUE = 124.4          # the LCh hue of #4C662B, the design's own green
SEED_SPAN = 45.0          # how far from it still counts as "the seed's hue"


def _lch(hexstr: str) -> tuple[float, float, float]:
    import m3color, math
    L, a, b = m3color.hex_to_lab(hexstr)
    return L, math.hypot(a, b), math.degrees(math.atan2(b, a)) % 360


def _turn(value: str, hue: float, force: bool = False) -> str:
    """One colour, turned to the hue given.

    Takes a hex or an rgba(); anything else, and anything too grey to have a
    hue, comes back untouched. Unless `force`, so does anything too far from
    the design's own seed to be the design's own colour."""
    import m3color, re as _re
    v = value.strip()
    m = _re.fullmatch(r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*(?:,\s*([\d.]+)\s*)?\)", v)
    if m:
        r, g, b = (int(m.group(i)) for i in (1, 2, 3))
        base, alpha = "#%02x%02x%02x" % (r, g, b), m.group(4)
    elif _re.fullmatch(r"#[0-9a-fA-F]{6}", v):
        base, alpha = v, None
    else:
        return value
    L, C, h = _lch(base)
    if C < 3 or (not force and abs((h - SEED_HUE + 180) % 360 - 180) > SEED_SPAN):
        return value
    turned = m3color.tone(hue, C, L)
    if alpha is None:
        return turned
    r, g, b = (int(turned[i:i + 2], 16) for i in (1, 3, 5))
    return "rgba(%d,%d,%d,%s)" % (r, g, b, alpha)


def _decls(block: str) -> dict:
    """The custom properties in one CSS block, in order."""
    import re as _re
    out, i = {}, 0
    while True:
        m = _re.compile(r"(--[a-z0-9-]+)\s*:").search(block, i)
        if not m:
            return out
        j, depth = m.end(), 0
        while j < len(block) and not (depth == 0 and block[j] in ";}"):
            depth += 1 if block[j] == "(" else -1 if block[j] == ")" else 0
            j += 1
        out[m.group(1)] = block[m.end():j].strip()
        i = j + 1


def theme_css(accent: str, design_css: str, *more: str) -> str:
    """The whole scheme, in the festival's hue, both themes.

    The values are read out of the design rather than restated here, because
    the design keeps them in three places and only one of them is a stylesheet:
    39 of the light tokens are declared in the card's own block, 26 exist
    nowhere but as the fallback written beside each use — `var(--heart,#8F4C0A)`
    — and the dark ones are declared once, by the design itself. A re-theme
    that missed the 26 would turn the dark page and leave the light one green.
    """
    import re as _re
    hue = _lch(accent)[2]
    dark_block = _re.search(r'\[data-theme="dark"\]\s*{([^}]*)}', design_css)
    light_block = _re.search(r':root:not\(\[data-theme="dark"\]\)\s*{([^}]*)}', CARD_CSS)
    dark = _decls(dark_block.group(1)) if dark_block else {}
    light = _decls(light_block.group(1)) if light_block else {}
    # the ones with no light declaration anywhere: the fallback is the value
    for src in (design_css, CARD_CSS, SHEET_CSS, FEST_CSS) + more:
        for name, fb in _re.findall(r"var\((--[a-z0-9-]+),\s*([^()]*?(?:\([^()]*\))?[^()]*?)\)", src):
            if name in dark and name not in light:
                light[name] = fb.strip()
    # Two families the design drew in colours of their own — the forecast's
    # pink, and the amber a plan is starred in — go to the festival's hue as
    # well. Dynamic colour would put roles like those at tertiary, sixty
    # degrees off, but a page carrying its festival's colour plus two others
    # is a page of three colours, and these two are not saying anything the
    # festival's own hue cannot. They keep their own tones, so each is still a
    # surface of its own rather than the About card again. The names stay
    # `--pink-*` and `--heart-*`; every use site says so.
    OTHERS = ("--pink", "--heart", "--on-heart", "--warm-plan", "--on-warm")

    def turn(d):
        out = []
        for k, v in d.items():
            out.append("%s:%s" % (k, _turn(v, hue, force=k.startswith(OTHERS))))
        return ";".join(out)
    # The hero's tint is declared on the strand class rather than on the root,
    # so it is not in either block above; it is stated here at the same weight
    # and later, and it takes its light tone under both themes because the
    # line it colours always stands on the picture's own wash.
    return ("/* %s's own hue — every tone the design chose, turned to it */\n"
            ":root:not([data-theme=\"dark\"]){%s}\n"
            "[data-theme=\"dark\"]{%s}\n"
            ".fest{--hero-tint:%s}\n"
            % (accent, turn(light), turn(dark), _turn("#CDEDA3", hue)))

def stage_palette(n: int, hue: float = SEED_HUE) -> tuple[list[dict], str]:
    """Hues by the golden angle rather than in equal steps.

    Ten stages spaced evenly are 36° apart, and 36° at these tones is the
    difference between one green and another — stage 1 and stage 2 read as the
    same colour, which is the one thing this palette exists to prevent. The
    golden angle puts consecutive stages most of the wheel apart while still
    filling it evenly however many stages there turn out to be.

    Returns what the component reads — a variable per role — and the stylesheet
    that gives those variables their two values."""
    import m3color
    ref, light, dark = [], [], []
    for i in range(n):
        h = (hue + i * 137.507) % 360
        ref.append({k: "var(--st%d-%s)" % (i, k.lower()) for k, _l, _d in ROLES})
        for k, lt, dk in ROLES:
            here = dk if k in ALWAYS_DARK else lt
            light.append("--st%d-%s:%s" % (i, k.lower(), m3color.tone(h, *here)))
            dark.append("--st%d-%s:%s" % (i, k.lower(), m3color.tone(h, *dk)))
    css = (":root{%s}\n[data-theme=\"dark\"]{%s}\n"
           "/* The exit the two cards leave by: fp-weather-in, which is how\n"
           "   they arrive, played backwards. */\n"
           "@keyframes fp-card-out{"
           "0%%{opacity:1;transform:none}"
           "100%%{opacity:0;transform:translateY(-12px) scale(.94)}}\n"
           "/* Someone who has asked for less motion still gets the indicator\n"
           "   and the cards, they just do not get the journey. */\n"
           "@media (prefers-reduced-motion: reduce){"
           "[data-fp-nav-pill]{transition:none!important}"
           "[data-fp-card]{animation:none!important}}"
           % (";".join(light), ";".join(dark)))
    return ref, css


def patch_stage_colours(src: str, fest: Festival) -> str:
    pal = stage_palette(len(fest.stages))[0]
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
         "const st = this.STAGES[i], c = this.stageColor(i);", "focus ring"),
        # The stage list beside the map: its number badge is the stage's own
        # colour, and its count is for the day on screen rather than all of them.
        (r"const c = C\[st\.cat\], n = this\.EVENTS\.filter\(e => e\.s === i\)\.length;",
         "const c = this.stageColor(i), n = this.EVENTS.filter("
         "e => e.s === i && e.d === this.state.day).length;", "stage card"),
        (r"this\.EVENTS\.filter\(e => e\.s === i\)\.length \+ ' acts on '",
         "this.EVENTS.filter(e => e.s === i && e.d === this.state.day).length + ' acts on '",
         "map popup count"),
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
        # The rule under a column head when the grid is scrolled, the dot on a
        # stage's own filter chip, and the rows behind a "+N" of overlapping
        # acts — the last three places the category colour still showed.
        (r"boxShadow: 'inset 0 -3px 0 0 ' \+ C\[this\.STAGES\[i\]\.cat\]\.dot",
         "boxShadow: 'inset 0 -3px 0 0 ' + this.stageColor(i).dot",
         "column head rule"),
        (r"count: this\.EVENTS\.filter\(e => e\.s === i\)\.length, dot: C\[st\.cat\]\.dot",
         "count: this.EVENTS.filter(e => e.s === i && e.d === this.state.day).length,"
         " dot: this.stageColor(i).dot", "stage facet"),
        (r"const cc = C\[ev\.cat\], on = !!S\.star\[ev\.id\];",
         "const cc = this.stageColor(ev.s), on = !!S.star[ev.id];", "overlap rows"),
        # The sheet's first chip names the kind of act. It was reading that
        # name off the palette, which now belongs to the stage and carries no
        # name at all — an empty chip beside the genres.
        (r"tags: \[c\.label\]\.concat\(sev\.genres\),",
         "tags: [C[sev.cat].label].concat(sev.genres),", "sheet category chip"),
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
    src = sub_once(src, r"  componentDidUpdate\((prevProps, prevState)?\) \{",
                   "  componentDidUpdate(prevProps, prevState) {\n    this.loadWeather();",
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

    # Every one of these is the design saying "there is always weather". There
    # is not: until the forecast answers, the card and its toggle stay away.
    for old, new, what in [
        (r"this\.props\.showWeather !== false && S\.weatherOpen !== false;",
         "this.props.showWeather !== false && !!S.wx && S.weatherOpen !== false;", "weather shown"),
        (r"showWeather: this\.props\.showWeather !== false && S\.weatherOpen !== false,",
         "showWeather: this.props.showWeather !== false && !!S.wx && S.weatherOpen !== false,", "weather prop"),
        (r"showWeatherBrief: this\.props\.showWeather !== false,",
         "showWeatherBrief: this.props.showWeather !== false && !!S.wx,", "weather brief"),
        (r"weatherToggleLabel: S\.weatherOpen !== false \? 'Hide the weather' : 'Weather: 21°, overcast',",
         "weatherToggleLabel: S.weatherOpen !== false ? 'Hide the weather'\n"
         "        : ('Weather: ' + (S.wx ? S.wx.temp + ', ' + S.wx.word.toLowerCase() : 'not available')),",
         "weather label"),
        # The caption under the artwork names the festival's own site, not a
        # city picked from a list of three.
        (r"weatherPlace: \(this\.PLACES\.find\(p => p\.id === S\.place\) \|\| this\.PLACES\[0\]\)\.site \+ ' · illustrative',",
         "weatherPlace: %s," % js("%s · illustrative" % fest.f["city"].split(",")[0]),
         "artwork label"),
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

    # ---- the pin ----
    # A 32px disc ringed in 2px of white and dropped on an 8px shadow, which is
    # how a map pin was drawn when the basemaps were still beige. The ring and
    # the blur are gone: the shape comes off the shape scale — a 20dp corner on
    # three sides and a 4dp one at the point — and it sits on M3's level-2
    # elevation.
    #
    # The colour is the cell's: the container the timetable draws a set in,
    # with the ink it writes the name in. A pin and the column it belongs to
    # are then the same colour, which is the one thing colour has to say here.
    # The one you have just asked for takes the plan colour while it beats,
    # which is colour spent on state — what M3 spends it on.
    src = sub_once(
        src,
        r"      const html = '<div style=\"width:32px;height:32px;"
        r"border-radius:50% 50% 50% 0;transform:rotate\(-45deg\);background:' \+ c\.dot \+\n"
        r"        ';border:2px solid #fff;box-shadow:0 3px 8px rgba\(20,24,14,\.35\);"
        r"display:grid;place-items:center\">' \+\n"
        r"        '<span style=\"transform:rotate\(45deg\);"
        r"font:700 14px Inter,system-ui,sans-serif;color:' \+ c\.fg \+ '\">' \+ st\.n"
        r" \+ '</span></div>';",
        "      /* The resting colour is set through a variable, not written in:\n"
        "         the state below sets an inline background and clears it\n"
        "         again, and a cleared inline style has to fall back to\n"
        "         something. */\n"
        "      const html = '<div data-fp-pin=\"\" style=\"width:34px;height:34px;"
        "border-radius:20px 20px 20px 4px;transform:rotate(-45deg);"
        "box-shadow:0 1px 2px rgba(20,24,14,.30),"
        "0 2px 6px 2px rgba(20,24,14,.15);"
        "--pin:' + c.bg + ';--pin-on:' + c.fg + ';"
        "display:grid;place-items:center\">' +\n"
        "        '<span style=\"transform:rotate(45deg);"
        "font:600 14px/20px Inter,system-ui,sans-serif;letter-spacing:.1px;"
        "color:inherit\">' + st.n + '</span></div>';",
        "map pin")
    src = sub_once(
        src,
        r"        icon: L\.divIcon\(\{ html: html, className: '', iconSize: \[32, 32\],"
        r" iconAnchor: \[16, 32\], popupAnchor: \[0, -30\] \}\)",
        "        icon: L.divIcon({ html: html, className: '', iconSize: [34, 34],"
        " iconAnchor: [17, 34], popupAnchor: [0, -32] })",
        "map pin box")
    # The popup is the map's own card: the stage in Title Small over its count
    # in Body Small, which is the pair every other list on the page uses.
    src = sub_once(
        src,
        r"      mk\.bindPopup\('<strong style=\"font:650 14px Inter,sans-serif\">'"
        r" \+ st\.name \+ '</strong><br><span style=\"font:400 12\.5px Inter,sans-serif;"
        r"color:var\(--on-var,#494E42\)\">' \+",
        "      mk.bindPopup('<strong style=\"font:500 14px/20px Inter,sans-serif;"
        "letter-spacing:.1px\">' + st.name + '</strong><br>"
        "<span style=\"font:400 12px/16px Inter,sans-serif;letter-spacing:.4px;"
        "color:var(--on-var,#494E42)\">' +",
        "map popup type")

    # Pressing the row does what pressing the arrow beside a set does — it
    # takes the map to the stage and the pin answers — and it opens the row,
    # which is where the address is and the two ways of leaving with it. One
    # row is open at a time; pressing it again closes it.
    src = sub_once(
        src,
        r"        onClick: \(\) => this\.focusStage\(i\)\n      \};\n    \}\);",
        "        open: S.stageOpen === i,\n"
        "        /* A pin belongs in front of a place, not in front of a\n"
        "           sentence: where the organiser published a street the panel\n"
        "           shows it as an address, and where they published only a\n"
        "           description it shows that as what it is. */\n"
        "        hasAddr: !!st.where, where: st.where || '',\n"
        "        panelNote: st.where ? '' : (st.note || ''),\n"
        "        panelStyle: {\n"
        "          overflow: 'hidden', borderRadius: '0 0 16px 16px',\n"
        "          maxBlockSize: S.stageOpen === i ? '200px' : '0px',\n"
        "          opacity: S.stageOpen === i ? 1 : 0,\n"
        "          transition: 'max-block-size .4s cubic-bezier(.2,0,0,1),"
        " opacity .2s cubic-bezier(.2,0,0,1)'\n"
        "        },\n"
        "        /* One column under the name: the supporting line starts where\n"
        "           the name starts — 10 of inset, the 32 disc, 12 between —\n"
        "           and the actions take the card's own 16, which is where a\n"
        "           card's actions sit. */\n"
        "        panelInnerStyle: {\n"
        "          display: 'grid', gap: '12px', padding: '0 16px 16px'\n"
        "        },\n"
        "        whereStyle: {\n"
        "          display: 'flex', alignItems: 'flex-start', gap: '8px',\n"
        "          margin: 0, marginInlineStart: '38px',\n"
        "          fontSize: '14px', lineHeight: '20px', letterSpacing: '.25px',\n"
        "          color: 'var(--on-var,#494E42)'\n"
        "        },\n"
        "        noteStyle2: {\n"
        "          margin: 0, marginInlineStart: '38px',\n"
        "          fontSize: '14px', lineHeight: '20px', letterSpacing: '.25px',\n"
        "          color: 'var(--on-var,#494E42)'\n"
        "        },\n"
        "        actionsStyle: { display: 'flex', flexWrap: 'wrap', gap: '8px' },\n"
        "        /* M3 buttons at the sizes M3 states: a tonal one for the\n"
        "           action you are most likely to want, an outlined one beside\n"
        "           it, both 40 tall on a full-round corner. */\n"
        "        openMapStyle: {\n"
        "          display: 'inline-flex', alignItems: 'center', gap: '8px',\n"
        "          height: '40px', padding: '0 16px', border: 0,\n"
        "          borderRadius: '20px', background: 'var(--sec,#DCE8C0)',\n"
        "          color: 'var(--on-sec,#1F2D0A)', fontFamily: 'inherit',\n"
        "          fontSize: '14px', lineHeight: '20px', letterSpacing: '.1px',\n"
        "          fontWeight: 500, cursor: 'pointer'\n"
        "        },\n"
        "        walkStyle: {\n"
        "          display: 'inline-flex', alignItems: 'center', gap: '8px',\n"
        "          height: '40px', padding: '0 16px',\n"
        "          border: '1px solid var(--outline,#C7CBBA)',\n"
        "          borderRadius: '20px', background: 'none',\n"
        "          color: 'var(--on,#191D13)', fontFamily: 'inherit',\n"
        "          fontSize: '14px', lineHeight: '20px', letterSpacing: '.1px',\n"
        "          fontWeight: 500, cursor: 'pointer'\n"
        "        },\n"
        "        onOpenMap: (e) => { e.stopPropagation(); this.mapLink(i, false); },\n"
        "        onWalk: (e) => { e.stopPropagation(); this.mapLink(i, true); },\n"
        "        onClick: () => {\n"
        "          this.navigateTo(i);\n"
        "          this.setState(s => ({ stageOpen: s.stageOpen === i ? null : i }));\n"
        "        }\n      };\n    });",
        "stage row opens")

    # The two ways of leaving with an address. A phone's own map app is what
    # opens either one: Apple's on an Apple device, and everywhere else the
    # geo: scheme, which is the one Android hands to whichever map app the
    # reader has set as theirs. The https link is the fallback for a desktop
    # browser, which has no map app to hand it to.
    src = sub_once(
        src,
        r"  /\* Marker blast: an expanding ring at the stage plus a pop on the pin itself\. \*/",
        "  mapLink(i, walk) {\n"
        "    const st = this.STAGES[i];\n"
        "    if (!st) return;\n"
        "    const ll = st.lat + ',' + st.lng;\n"
        "    const label = encodeURIComponent(st.name);\n"
        "    const ua = navigator.userAgent || '';\n"
        "    const apple = /iPad|iPhone|iPod/.test(ua)\n"
        "      || (/Macintosh/.test(ua) && 'ontouchend' in document);\n"
        "    let url;\n"
        "    if (apple) {\n"
        "      url = walk\n"
        "        ? 'maps://?daddr=' + ll + '&dirflg=w'\n"
        "        : 'maps://?ll=' + ll + '&q=' + label;\n"
        "    } else if (/Android/.test(ua)) {\n"
        "      url = walk\n"
        "        ? 'google.navigation:q=' + ll + '&mode=w'\n"
        "        : 'geo:' + ll + '?q=' + ll + '(' + label + ')';\n"
        "    } else {\n"
        "      url = walk\n"
        "        ? 'https://www.google.com/maps/dir/?api=1&destination=' + ll\n"
        "          + '&travelmode=walking'\n"
        "        : 'https://www.google.com/maps/search/?api=1&query=' + ll;\n"
        "    }\n"
        "    try { window.open(url, '_blank', 'noopener'); }\n"
        "    catch (e) { location.href = url; }\n"
        "  }\n\n"
        "  /* Marker blast: an expanding ring at the stage plus a pop on the pin itself. */",
        "map links")

    # ---- pressing a stage takes the map to it ----
    # It jumped: setView with animate:true is a pan at one speed, and at a zoom
    # change it is a cut. flyTo is the movement M3 asks for on a spatial change
    # — it accelerates away and decelerates in, and the zoom rides with it —
    # and it never zooms out from where the reader already is.
    src = sub_once(
        src,
        r"      m\.setView\(\[st\.lat, st\.lng\], 17, \{ animate: true \}\);",
        "      const z = Math.max(m.getZoom() || 0, 17);\n"
        "      if (m.flyTo) m.flyTo([st.lat, st.lng], z,"
        " { duration: .85, easeLinearity: .25 });\n"
        "      else m.setView([st.lat, st.lng], z, { animate: true });",
        "map flies to the stage")
    # And it arrives without a speech bubble. The popup opened itself over the
    # pin it was pointing at, covering the map the reader had just asked to
    # see — and the pin now says which one it is by beating. Pressing the pin
    # still opens it, which is what a popup is for.
    src = sub_once(
        src,
        r"      if \(this\.markers && this\.markers\[i\]\) this\.markers\[i\]\.openPopup\(\);",
        "      m.closePopup();",
        "no bubble on arrival")
    # ---- and the pin says so ----
    # One filled disc expanding once and a single pop on the pin. It is a
    # heartbeat now — two beats to the round, three rounds — over three rings
    # leaving the pin half a second apart, which is what a ripple is. Both are
    # drawn in the stage's own dark container, the colour the pin is.
    src = sub_once(
        src,
        r"      icon: L\.divIcon\(\{\n"
        r"        className: '', iconSize: \[36, 36\], iconAnchor: \[18, 18\],\n"
        r"        html: '<div style=\"width:36px;height:36px;border-radius:50%;background:'"
        r" \+ c\.dot \+\n"
        r"          ';box-shadow:0 0 0 2px ' \+ c\.planBg \+ '55;"
        r"animation:fp-blast 1\.05s cubic-bezier\(\.2,0,0,1\) 2 both\"></div>'\n"
        r"      \}\)",
        "      icon: L.divIcon({\n"
        "        className: '', iconSize: [46, 46], iconAnchor: [23, 23],\n"
        "        html: '<div style=\"position:relative;width:46px;height:46px\">'\n"
        "          + [0, .5, 1].map(d => '<span style=\"position:absolute;inset:0;"
        "border-radius:50%;border:2px solid var(--plan,#2E4B12);opacity:0;"
        "animation:fp-ripple 1.5s cubic-bezier(.2,0,0,1) ' + d + 's 3 both\"></span>')"
        ".join('')\n"
        "          + '</div>'\n"
        "      })",
        "map ripple")
    src = sub_once(
        src,
        r"    this\.ringTimer = setTimeout\(\(\) => this\.mapDo\(m => m\.removeLayer\(ring\)\), 2200\);",
        "    this.ringTimer = setTimeout(() => this.mapDo(m => m.removeLayer(ring)), 4700);",
        "map ripple lifetime")
    src = sub_once(
        src,
        r"    if \(el\) \{ el\.style\.animation = 'none'; void el\.offsetWidth;"
        r" el\.style\.animation = 'fp-pop \.48s cubic-bezier\(\.2,0,0,1\) 2'; \}",
        "    if (el) {\n"
        "      el.style.animation = 'none'; void el.offsetWidth;\n"
        "      el.style.animation = 'fp-beat 1.1s cubic-bezier(.2,0,0,1) 3';\n"
        "      /* The one you asked for is the one in the plan colour, for as\n"
        "         long as it is beating. Every other pin stays as it was. */\n"
        "      const back = document.querySelectorAll('[data-fp-pin]');\n"
        "      for (let k = 0; k < back.length; k++) {\n"
        "        back[k].style.background = '';\n"
        "        back[k].style.color = '';\n"
        "      }\n"
        "      el.style.background = 'var(--plan,#2E4B12)';\n"
        "      el.style.color = 'var(--on-plan,#EDF6DA)';\n"
        "      clearTimeout(this.pinTimer);\n"
        "      this.pinTimer = setTimeout(() => {\n"
        "        el.style.background = '';\n"
        "        el.style.color = '';\n"
        "      }, 3400);\n"
        "    }",
        "map pin heartbeat")

    # ---- Street / Satellite ----
    # Two pills of different roundness inside a floating capsule, which is not
    # a component M3 has. What it has is the segmented button, and this is one:
    # 40 tall inside a 1dp outline, one corner radius for the pair, the chosen
    # segment filled with the secondary container and its label in Label
    # Large. The container itself is patched in the markup.
    src = sub_once(
        src,
        r"    const baseTabs = \[\{ id: 'street', label: 'Street' \},"
        r" \{ id: 'satellite', label: 'Satellite' \}\]\.map\(b => \{\n"
        r"      const on = S\.base === b\.id;\n"
        r"      return \{\n"
        r"        label: b\.label, pressed: String\(on\),\n"
        r"        style: \{[^\n]*\},\n"
        r"        onClick: \(\) => this\.setBase\(b\.id\)\n"
        r"      \};\n"
        r"    \}\);",
        "    const baseTabs = [{ id: 'street', label: 'Street' },"
        " { id: 'satellite', label: 'Satellite' }].map((b, i) => {\n"
        "      const on = S.base === b.id;\n"
        "      return {\n"
        "        label: b.label, pressed: String(on),\n"
        "        style: {\n"
        "          display: 'inline-flex', alignItems: 'center',"
        " justifyContent: 'center',\n"
        "          height: '38px', padding: '0 16px', border: 0,\n"
        "          borderInlineStart: i\n"
        "            ? '1px solid var(--outline,#C7CBBA)' : '0',\n"
        "          borderRadius: 0,\n"
        "          background: on ? 'var(--sec,#DCE8C0)' : 'transparent',\n"
        "          color: on ? 'var(--on-sec,#1F2D0A)' : 'var(--on-var,#494E42)',\n"
        "          fontFamily: 'inherit', fontSize: '14px', lineHeight: '20px',\n"
        "          letterSpacing: '.1px', fontWeight: 500, cursor: 'pointer',\n"
        "          transition: 'background .2s cubic-bezier(.2,0,0,1),"
        " color .2s cubic-bezier(.2,0,0,1)'\n"
        "        },\n"
        "        onClick: () => this.setBase(b.id)\n"
        "      };\n"
        "    });",
        "base map segments")

    # Where it stands. It was placed against the pane, which runs the full
    # width, while the map inside it keeps a 12px margin on a phone and a 28px
    # corner at every width — so the control sat on the map's edge with the
    # corner still curving away underneath it. It is placed against the map:
    # far enough in from both of its edges to clear that curve, which for a
    # 28px radius is 8px at the diagonal and 16 with room to spare.
    src = sub_once(
        src,
        r"      mapPaneStyle: split \?"
        r" \{ position: 'relative', width: '100%', flex: 'none' \}\n?"
        r"\s*: \{ flex: '2 1 460px', minWidth: 0, position: 'relative' \},",
        "      mapPaneStyle: split ? { position: 'relative', width: '100%', flex: 'none' }\n"
        "        : { flex: '2 1 460px', minWidth: 0, position: 'relative' },\n"
        "      mapToggleStyle: {\n"
        "        position: 'absolute', zIndex: 1, insetBlockStart: '16px',\n"
        "        insetInlineStart: mob ? '28px' : '16px',\n"
        "        display: 'flex', padding: 0,\n"
        "        border: '1px solid var(--outline,#C7CBBA)', borderRadius: '20px',\n"
        "        overflow: 'hidden',\n"
        "        background: 'color-mix(in srgb, var(--card,#F2F0EB) 88%, transparent)',\n"
        "        WebkitBackdropFilter: 'blur(8px)', backdropFilter: 'blur(8px)'\n"
        "      },",
        "base map toggle place")

    # ---- the stage beside the map ----
    # Same disc, same colours, and the three lines take the type scale's own
    # steps: Title Medium for the stage, Body Medium for what it is, Label
    # Large for the count.
    src = sub_once(
        src,
        r"        numStyle: \{ flex: 'none', display: 'grid', placeItems: 'center',"
        r" width: '28px', height: '28px', borderRadius: '10px', background: c\.dot,"
        r" color: c\.fg, fontSize: '13px', fontWeight: 700 \},",
        "        numStyle: { flex: 'none', display: 'grid', placeItems: 'center',\n"
        "          width: '32px', height: '32px', borderRadius: '12px',\n"
        "          /* One dark container down the list, so the numbers read as\n"
        "             a set rather than as ten separate colours; the stage's\n"
        "             own colour is on its pin and in its column. */\n"
        "          background: 'var(--on,#191D13)', color: 'var(--low,#F8F7F3)',\n"
        "          fontSize: '14px', lineHeight: '20px', letterSpacing: '.1px',\n"
        "          fontWeight: 600 },\n"
        "        nameStyle: mob\n"
        "          ? { fontSize: '14px', lineHeight: '20px',\n"
        "              letterSpacing: '.1px', fontWeight: 600 }\n"
        "          : { fontSize: '16px', lineHeight: '24px',\n"
        "              letterSpacing: '.15px', fontWeight: 500 },\n"
        "        noteStyle: { fontSize: '14px', lineHeight: '20px',\n"
        "          letterSpacing: '.25px', color: 'var(--on-var,#494E42)' },\n"
        "        /* On a phone the row is the stage and the way to it. What the\n"
        "           stage is like is two lines of prose per row and ten rows of\n"
        "           it under a map you are trying to read; the act's own card\n"
        "           carries it. The row becomes M3's one-line list item — 56dp,\n"
        "           its number leading, the arrow that says it goes somewhere\n"
        "           trailing. */\n"
        "        showNote: !mob, showGo: mob,\n"
        "        countStyle: { fontSize: '14px', lineHeight: '20px',\n"
        "          letterSpacing: '.1px', fontWeight: 500,\n"
        "          color: 'var(--primary,#4C662B)' },\n"
        "        /* The count is a third line about the day rather than about\n"
        "           the stage, and the programme two taps away is where it is\n"
        "           read. A phone keeps the stage and what it is. */\n"
        "        showCount: !mob,",
        "stage card type")
    # The row itself: a one-line list item on a phone, a card with a paragraph
    # in it above that.
    src = sub_once(
        src,
        r"        style: \{ display: 'flex', gap: '14px', alignItems: 'flex-start',"
        r" width: '100%', padding: '16px', border: 0, borderRadius: '24px',"
        r" background: 'var\(--card,#F2F0EB\)', fontFamily: 'inherit',"
        r" cursor: 'pointer', textAlign: 'start' \},",
        "        style: {\n"
        "          display: 'flex', gap: mob ? '12px' : '14px',\n"
        "          alignItems: mob ? 'center' : 'flex-start',\n"
        "          width: '100%', minBlockSize: mob ? '56px' : 'auto',\n"
        "          padding: mob ? '8px 8px 8px 10px' : '16px', border: 0,\n"
        "          /* On a phone the surface belongs to the wrapper, so the row\n"
        "             and the panel that opens under it are one card. */\n"
        "          borderRadius: mob ? '0px' : '24px',\n"
        "          background: mob ? 'transparent' : 'var(--card,#F2F0EB)',\n"
        "          fontFamily: 'inherit',\n"
        "          cursor: 'pointer', textAlign: 'start',\n"
        "          transition: 'background .2s cubic-bezier(.2,0,0,1)'\n"
        "        },\n"
        "        /* The surface for both, and no clipping on it: the row is a\n"
        "           grid item, and a grid item that hides its overflow is sized\n"
        "           from something other than its contents here. The panel does\n"
        "           its own clipping — it is the only part that needs it. */\n"
        "        wrapStyle: mob\n"
        "          ? { background: 'var(--card,#F2F0EB)', borderRadius: '16px' }\n"
        "          : null,\n"
        "        goStyle: { flex: 'none', marginInlineStart: 'auto',\n"
        "          inlineSize: '20px', blockSize: '20px', fill: 'currentColor',\n"
        "          color: 'var(--on-var,#494E42)', opacity: .7 },",
        "stage row")

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
    tpl = sub_once(tpl, r">Flow Festival 2026</h1>",
                   ">%s</h1>" % name, "hero title")
    tpl = sub_once(tpl, r">14–16 August 2026<", ">%s<" % f["dates"], "hero dates")
    tpl = sub_once(tpl, r">Gates 15:00, music until 01:00<",
                   ">%s<" % fest.hours_line, "hero fact 1")
    tpl = sub_once(tpl, r">Day ticket €99 · 3-day pass €249<",
                   ">%s<" % fest.facts[2], "hero fact 2")
    # The venue is a button that opens the map, so the place and what kind of
    # festival it is are two elements now rather than one line.
    tpl = sub_once(tpl, r'aria-label="Suvilahti, Sörnäinen — show the site map"',
                   'aria-label="%s — show the site map"' % f["city"],
                   "address chip label")
    tpl = sub_once(tpl, r">Suvilahti, Sörnäinen</span>",
                   ">%s</span>" % f["city"], "address chip")
    tpl = sub_once(tpl, r">· Metro to Kalasatama<", ">· %s<" % f["type"],
                   "address note")
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

    # The two cards that arrive and leave, marked so the reduced-motion rule
    # can find them.
    tpl = sub_once(tpl, r'    <article style="\{\{ heroCardStyle \}\}" ref="\{\{ heroCardRef \}\}">',
                   '    <article data-fp-card="" style="{{ heroCardStyle }}" '
                   'ref="{{ heroCardRef }}">', "festival card mark")

    # ---- the festival, at the compact breakpoint ----
    # festival-mobile.html's own markup, element for element: the hero and its
    # notch, the status chips, the headline, the meta list, the genre rail, the
    # actions and the About block. The festival's own words are written into
    # it here the way they are written into the design above; the parts that do
    # something — the plan button, the map, the set times, the About toggle —
    # are bound to what already does them.
    stats = f.get("stats") or {}
    strand = (f.get("category") or "music")
    days = int(stats.get("days") or 1)
    # The design's three facts under the rule, carrying what the meta list
    # above has not already said: how many stages, how long, how many acts.
    span = fest.days
    hours = round(sum(d["end"] - d["start"] for d in span) / 60)
    facts = [
        ("#i-pin-line", "%s stages" % stats.get("stages", "")),
        ("#i-time", ("%d days" % days) if days > 1 else "%d hours" % hours),
        ("#i-mic-line", "%s acts" % stats.get("acts", "")),
        ("#i-tag", fest.facts[2]),
    ]
    # The hero is the festival's own photograph and its own mark where there
    # is one — the picture the home page's card already shows, and the logo
    # the organiser publishes. A scrim between them, because a logo drawn for
    # paper has to hold over a daylit crowd. A festival with no picture keeps
    # the strand artwork the design generates.
    promo = ROOT / "assets" / "home" / f["promo"] if f.get("promo") else None
    logo = ROOT / "assets" / f["logo"] if f.get("logo") else None
    if promo and promo.exists():
        hero_art = ('          <img class="hero__photo" src="%s" alt="">\n'
                    '          <span class="hero__scrim"></span>\n' % data_uri(promo))
    else:
        hero_art = ('          <svg class="hero__art" sc-camel-view-box="0 0 400 250"'
                    ' sc-camel-preserve-aspect-ratio="xMidYMid slice" role="img"'
                    ' aria-label="%s strand artwork">\n'
                    '            <use href="#i-art"></use>'
                    '<use href="#i-motif-%s"></use>\n'
                    '          </svg>\n' % (strand.title(), strand))
    # Four chips: what the festival is, and the three things it plays. A
    # fifth only ever showed as a sliver at the screen edge.
    genres = "".join("<li>%s</li>" % g for g in (f.get("tags") or [])[:3])
    tickets = ('        <a class="act" href="%s" target="_blank" rel="noopener noreferrer"'
               ' aria-label="Tickets" title="Tickets">\n'
               '          <svg aria-hidden="true" style="fill:currentColor">'
               '<use href="#i-ticket"></use></svg><span>Tickets</span>\n'
               '        </a>\n' % f["tickets"]) if f.get("tickets") else ""
    compact = (
        '      <sc-if value="{{ phoneCard }}">\n'
        '      <div class="fest t-%(strand)s">\n'
        '        <section class="fcard">\n'
        '        <div class="hero">\n'
        '%(heroArt)s'
        '          <div class="hero__overlay">\n'
        '            <p class="hero__eyebrow">%(when)s</p>\n'
        '            <h1 class="hero__title">%(name)s</h1>\n'
        '            <button class="hero__where" type="button"'
        ' sc-camel-on-click="{{ openMap }}">\n'
        '              <svg aria-hidden="true"><use href="#i-pin"></use></svg>\n'
        '              <span>%(city)s · %(type)s</span>\n'
        '              <svg class="hero__where-go" aria-hidden="true">'
        '<use href="#i-near"></use></svg>\n'
        '            </button>\n'
        '          </div>\n'
        '        </div>\n'
        '\n'
        '        <sc-if value="{{ festLive }}">\n'
        '        <div class="status">\n'
        '          <span class="chip chip--live"><b aria-hidden="true"></b>Live now</span>\n'
        '        </div>\n'
        '        </sc-if>\n'
        '\n'
        '        <ul class="genres"><li class="strand">%(strandName)s</li>'
        '%(genres)s</ul>\n'
        '\n'
        '        <div class="actions">\n'
        '          <a class="act" href="%(official)s" target="_blank"'
        ' rel="noopener noreferrer" aria-label="Official site" title="Official site">\n'
        '            <svg aria-hidden="true"><use href="#i-ext"></use></svg>'
        '<span>Official</span>\n'
        '          </a>\n'
        '%(tickets)s'
        '          <button class="plan" type="button"'
        ' sc-camel-on-click="{{ toggleFestivalPlan }}"'
        ' aria-pressed="{{ festivalPlanned }}">\n'
        '            <svg sc-camel-view-box="0 0 24 24" aria-hidden="true"'
        ' style="{{ heartSvgStyle }}">\n'
        '              <defs><clipPath id="{{ heartClipId2 }}"'
        ' sc-camel-clip-path-units="userSpaceOnUse">\n'
        '                <circle cx="12" cy="12" r="19" style="{{ heartDiscStyle }}"></circle>\n'
        '              </clipPath></defs>\n'
        '              <use href="#i-heart-geo" style="{{ heartOutlineStyle }}"></use>\n'
        '              <g clip-path="{{ heartClipUrl2 }}">'
        '<use href="#i-heart-geo" style="fill:currentColor;stroke:none"></use></g>\n'
        '            </svg>\n'
        '            <span>{{ festivalPlanLabel }}</span>\n'
        '          </button>\n'
        '        </div>\n'
        '        </section>\n'
        '\n'
        '        <div class="sec-head">\n'
        '          <h2>Lineup</h2>\n'
        '          <button type="button" sc-camel-on-click="{{ seeAll }}">'
        'See all {{ lineupTotal }}</button>\n'
        '        </div>\n'
        '        <ul class="lineup" aria-label="Lineup">\n'
        '          <sc-for list="{{ lineup }}" as="a" hint-placeholder-count="6">\n'
        '            <li>\n'
        '              <button class="who" type="button"'
        ' sc-camel-on-click="{{ a.onOpen }}" aria-label="{{ a.aria }}">\n'
        '                <span class="{{ a.avatarClass }}" style="{{ a.avatarStyle }}">\n'
        '                  <svg class="who__art" sc-camel-view-box="0 0 400 250"'
        ' sc-camel-preserve-aspect-ratio="xMidYMid slice" aria-hidden="true"'
        ' style="{{ a.artStyle }}">\n'
        '                    <use href="#i-art"></use><use href="{{ a.motif }}"></use>\n'
        '                  </svg>\n'
        '                  <sc-if value="{{ a.planned }}"><b aria-hidden="true">'
        '<svg sc-camel-view-box="0 0 24 24"><use href="#i-star-fill"></use></svg>'
        '</b></sc-if>\n'
        '                </span>\n'
        '                <span class="who__name">{{ a.name }}</span>\n'
        '                <span class="who__role">{{ a.when }}</span>\n'
        '              </button>\n'
        '            </li>\n'
        '          </sc-for>\n'
        '        </ul>\n'
        '\n'
        '        <section class="{{ aboutClass }}">\n'
        '          <h2>About</h2>\n'
        '          <div class="about__clip" style="{{ aboutClipStyle }}"'
        ' ref="{{ aboutClipRef }}">\n'
        '            <p class="about__text">%(about)s</p>\n'
        '          </div>\n'
        '          <sc-if value="{{ aboutFolds }}">\n'
        '          <button class="about__more" type="button"'
        ' aria-expanded="{{ aboutOpen }}" sc-camel-on-click="{{ toggleAbout }}">\n'
        '            <span>{{ aboutMoreLabel }}</span>'
        '<svg aria-hidden="true"><use href="#i-chev"></use></svg>\n'
        '          </button>\n'
        '          </sc-if>\n'
        '          <ul class="about__facts">%(facts)s</ul>\n'
        '        </section>\n'
        '      </div>\n'
        '      </sc-if>\n'
        '      <sc-if value="{{ deskCard }}">\n'
    ) % {
        "strand": strand,
        "strandName": strand.title(),
        "heroArt": hero_art,
        "name": name,
        "when": ("%s · %s" % (f["dates"], fest.hours_line.split(" · ")[0])).upper(),
        "dates": f["dates"],
        # the hours alone: how many days it runs is a fact below, and a date
        # range with the count after it wraps this line in two.
        "hours": fest.hours_line.split(" · ")[0],
        "city": f["city"],
        "type": f["type"],
        "price": fest.facts[2],
        "genres": genres,
        "official": f["official"],
        "tickets": tickets,
        "about": f["description"],
        "facts": "".join(
            '<li><svg aria-hidden="true"><use href="%s"></use></svg>%s</li>' % (i, t)
            for i, t in facts),
    }
    tpl = sub_once(
        tpl,
        r'    <article data-fp-card="" style="\{\{ heroCardStyle \}\}"'
        r' ref="\{\{ heroCardRef \}\}">\n',
        '    <article data-fp-card="" style="{{ heroCardStyle }}"'
        ' ref="{{ heroCardRef }}">\n' + compact,
        "the compact festival card")
    tpl = sub_once(
        tpl,
        r'      </sc-if>\n    </article>',
        '      </sc-if>\n      </sc-if>\n    </article>',
        "the wide festival card closes")

    # Where a starred act goes, and what counts it.
    tpl = sub_once(
        tpl,
        r'<button sc-camel-on-click="\{\{ togglePicks \}\}"',
        '<button data-fp-picks="" sc-camel-on-click="{{ togglePicks }}"',
        "the picks button")

    # The glyphs the compact festival design uses that the planner's sprite
    # does not carry, copied from it unchanged — and one more drawn to match,
    # because the design's third fact is about the festival's admission and
    # ours is about its line-up.
    tpl = sub_once(
        tpl,
        r'  <symbol id="i-chev"',
        '  <symbol id="i-pin-line" sc-camel-view-box="0 0 24 24" fill="none"'
        ' stroke="currentColor"><path d="M12 21s7-6.3 7-11a7 7 0 1 0-14 0c0 4.7 7 11'
        ' 7 11Z"></path><circle cx="12" cy="10" r="2.6"></circle></symbol>\n'
        '  <symbol id="i-tag" sc-camel-view-box="0 0 24 24" fill="none"'
        ' stroke="currentColor"><path d="M20.6 12.4 12.4 20.6a2 2 0 0 1-2.8 0l-6.2-6.2A2'
        ' 2 0 0 1 2.8 13V4.8A1.8 1.8 0 0 1 4.6 3h8.2a2 2 0 0 1 1.4.6l6.4 6.4a2 2 0 0 1 0'
        ' 2.4Z"></path><circle cx="7.6" cy="7.6" r="1.4"></circle></symbol>\n'
        '  <symbol id="i-mic-line" sc-camel-view-box="0 0 24 24" fill="none"'
        ' stroke="currentColor" stroke-linecap="round"><rect x="9" y="2.8" width="6"'
        ' height="11" rx="3"></rect><path d="M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V21m-3'
        ' 0h6"></path></symbol>\n'
        '  <symbol id="i-chev"',
        "the compact design's glyphs")

    # The button at the foot takes its glyph and its name from the model, so
    # it can be the arrow or the mark.
    tpl = sub_once(
        tpl,
        r'  <button sc-camel-on-click="\{\{ goBack \}\}" aria-label="Go back"'
        r' title="Go back" style="\{\{ backBtnStyle \}\}"',
        '  <button sc-camel-on-click="{{ goBack }}" aria-label="{{ backLabel }}"'
        ' title="{{ backLabel }}" style="{{ backBtnStyle }}"',
        "the back button's name")
    tpl = sub_once(
        tpl,
        r'    <svg aria-hidden="true" style="\{\{ backIconStyle \}\}">'
        r'<use href="#i-back"></use></svg>',
        '    <svg aria-hidden="true" style="{{ backIconStyle }}">'
        '<use href="{{ backIcon }}"></use></svg>',
        "the back button's glyph")

    # The page behind the sheet, marked so it can step back while one is open.
    tpl = sub_once(tpl, r'<div style="\{\{ shellStyle \}\}">',
                   '<div data-fp-shell="" style="{{ shellStyle }}">', "shell mark")

    # The segmented button's container: an outline and one corner for the
    # pair, not a floating capsule with two pills rattling inside it.
    tpl = sub_once(
        tpl,
        r'<div role="group" aria-label="Base map" style="position:absolute;top:14px;'
        r'left:14px;z-index:1;display:flex;gap:4px;padding:4px;border-radius:22px;'
        r'background:var\(--bar2,rgba\(255,255,255,\.92\)\);'
        r'-webkit-backdrop-filter:blur\(8px\);backdrop-filter:blur\(8px\);'
        r'box-shadow:0 2px 10px rgba\(20,24,14,\.14\)">',
        '<div role="group" aria-label="Base map" style="{{ mapToggleStyle }}">',
        "base map container")

    # ---- the hour stays until the next one arrives ----
    # The list is read by time, and the time it was reading scrolled away with
    # the acts under it. Each hour holds at the top of the list until the next
    # hour reaches it and pushes it out, which is what a sticky section header
    # is for. It carries the page's own surface so the rows do not show
    # through it, and it is Title Small over Body Small, which is the pair the
    # rows themselves take.
    tpl = sub_once(
        tpl,
        r'          <div style="display:flex;align-items:baseline;gap:10px;'
        r'padding:0 4px 8px">\n'
        r'            <span style="font-size:15px;font-weight:700;'
        r'letter-spacing:-\.01em">\{\{ g\.time \}\}</span>\n'
        r'            <span style="font-size:12\.5px;color:var\(--on-var,#494E42\)">'
        r'\{\{ g\.count \}\}</span>',
        '          <div style="{{ g.headStyle }}">\n'
        '            <span style="{{ g.timeStyle }}">{{ g.time }}</span>\n'
        '            <span style="{{ g.countStyle }}">{{ g.count }}</span>',
        "the hour sticks")

    # The stage beside the map: its three lines are the row's own now.
    tpl = sub_once(
        tpl,
        r'              <span style="font-size:15px;font-weight:650;'
        r'letter-spacing:-\.012em">\{\{ s\.name \}\}</span>\n'
        r'              <span style="font-size:13px;line-height:1\.45;'
        r'color:var\(--on-var,#494E42\);text-wrap:pretty">\{\{ s\.note \}\}</span>\n'
        r'              <span style="font-size:12\.5px;font-weight:500;'
        r'color:var\(--primary,#4C662B\)">\{\{ s\.count \}\}</span>',
        '              <span style="{{ s.nameStyle }}">{{ s.name }}</span>\n'
        '              <sc-if value="{{ s.showNote }}" hint-placeholder-val="{{ true }}">\n'
        '                <span style="{{ s.noteStyle }}">{{ s.note }}</span>\n'
        '              </sc-if>\n'
        '              <sc-if value="{{ s.showCount }}" hint-placeholder-val="{{ true }}">\n'
        '                <span style="{{ s.countStyle }}">{{ s.count }}</span>\n'
        '              </sc-if>',
        "stage card lines")

    # The arrow that says the row goes somewhere — the same glyph the row in
    # the programme uses for it.
    tpl = sub_once(
        tpl,
        r'            <span style="\{\{ s\.numStyle \}\}">\{\{ s\.n \}\}</span>',
        '            <span style="{{ s.numStyle }}">{{ s.n }}</span>',
        "stage row number")
    # The row and the panel under it are one item of the list, wrapped in one
    # element: the aside is a grid, and two items in two auto rows meant the
    # panel's row was sized from a box the animation had just set to zero — it
    # stayed zero however tall its contents were. Inside a block of its own it
    # is an ordinary box that opens.
    tpl = sub_once(
        tpl,
        r'        <sc-for list="\{\{ stageCards \}\}" as="s" hint-placeholder-count="5">\n'
        r'          <button',
        '        <sc-for list="{{ stageCards }}" as="s" hint-placeholder-count="5">\n'
        '          <div style="{{ s.wrapStyle }}">\n'
        '          <button',
        "stage row wrapper")
    tpl = sub_once(
        tpl,
        r'(            </span>\n)(          </button>\n        </sc-for>\n      </aside>)',
        '            </span>\n'
        '            <sc-if value="{{ s.showGo }}">\n'
        '              <svg aria-hidden="true" style="{{ s.goStyle }}">'
        '<use href="#i-near"></use></svg>\n'
        '            </sc-if>\n'
        '          </button>\n'
        '          <div style="{{ s.panelStyle }}">\n'
        '            <div style="{{ s.panelInnerStyle }}">\n'
        '              <sc-if value="{{ s.hasAddr }}" hint-placeholder-val="{{ true }}">\n'
        '                <p style="{{ s.whereStyle }}">\n'
        '                  <svg aria-hidden="true" style="flex:none;'
        'width:18px;height:18px;fill:currentColor;margin-top:1px">'
        '<use href="#i-pin"></use></svg>\n'
        '                  <span>{{ s.where }}</span>\n'
        '                </p>\n'
        '              </sc-if>\n'
        '              <sc-if value="{{ s.panelNote }}">\n'
        '                <p style="{{ s.noteStyle2 }}">{{ s.panelNote }}</p>\n'
        '              </sc-if>\n'
        '              <div style="{{ s.actionsStyle }}">\n'
        '                <button sc-camel-on-click="{{ s.onOpenMap }}" '
        'style="{{ s.openMapStyle }}">\n'
        '                  <svg aria-hidden="true" style="width:18px;height:18px;'
        'fill:currentColor"><use href="#i-pin"></use></svg>Open map\n'
        '                </button>\n'
        '                <button sc-camel-on-click="{{ s.onWalk }}" '
        'style="{{ s.walkStyle }}">\n'
        '                  <svg aria-hidden="true" style="width:18px;height:18px;'
        'fill:currentColor"><use href="#i-near"></use></svg>Walk there\n'
        '                </button>\n'
        '              </div>\n'
        '            </div>\n'
        '          </div>\n'
        '          </div>\n'
        '        </sc-for>\n      </aside>',
        "stage row panel")

    # The three lines of a list row were written at one size for every screen;
    # they are the row's own now, so a phone can take the scale down a step.
    tpl = sub_once(
        tpl,
        r'                  <div style="flex:1 1 auto;min-width:0;display:grid;gap:5px">\n'
        r'                    <span style="font-size:17px;font-weight:700;line-height:1\.25;'
        r'letter-spacing:-\.012em;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">'
        r'\{\{ r\.title \}\}</span>\n'
        r'                    <span style="font-size:14px;font-weight:450;overflow:hidden;'
        r'text-overflow:ellipsis;white-space:nowrap">\{\{ r\.when \}\}</span>\n'
        r'                    <span style="display:inline-flex;align-items:center;gap:7px;'
        r'min-width:0;font-size:13\.5px;opacity:\.78">',
        '                  <div style="{{ r.rowTextStyle }}">\n'
        '                    <span style="{{ r.rowTitleStyle }}">{{ r.title }}</span>\n'
        '                    <span style="{{ r.rowWhenStyle }}">{{ r.when }}</span>\n'
        '                    <span style="{{ r.rowMetaStyle }}">',
        "row type scale")

    # ---- and an act that is on says so ----
    tpl = sub_once(
        tpl,
        r'                    <span style="\{\{ r\.rowMetaStyle \}\}">',
        '                    <sc-if value="{{ r.live }}">\n'
        '                      <span style="{{ r.liveStyle }}">\n'
        '                        <i style="{{ r.liveBarStyle }}"></i>'
        '<i style="{{ r.liveBar2Style }}"></i>'
        '<i style="{{ r.liveBar3Style }}"></i>\n'
        '                        <span>Live</span>\n'
        '                      </span>\n'
        '                    </sc-if>\n'
        '                    <span style="{{ r.rowMetaStyle }}">',
        "the live badge")
    tpl = sub_once(tpl, r'      <aside id="fp-weather" style="\{\{ weatherCardStyle \}\}">',
                   '      <aside id="fp-weather" data-fp-card="" '
                   'style="{{ weatherCardStyle }}">', "weather card mark")

    # ---- the act sheet becomes the artist card ----
    # Everything the old sheet said is still said, in the card's own order: the
    # name over the artwork rather than under it, the player where the empty
    # promise of one used to be, and the introduction, links, tags and actions
    # in two columns once there is room for two.
    tpl = sub_once(
        tpl,
        r"    <article role=\"dialog\"[\s\S]*?\n    </article>\n",
        CARD_HTML, "the artist card")

    # The mark is the way home, as it is on the festival list: same mark,
    # same destination, so it can be pressed from either page.
    tpl = sub_once(
        tpl,
        r'      <span style="display:flex;align-items:center;gap:12px;min-width:0">\n'
        r'        <svg sc-camel-view-box="0 0 96 96" aria-hidden="true" '
        r'style="flex:none;width:34px;height:34px;color:var\(--primary,#4C662B\)">'
        r'<use href="#i-logo"></use></svg>',
        '      <a href="../index.html" aria-label="Flanner — all festivals" '
        'style="display:flex;align-items:center;gap:12px;min-width:0;'
        'color:inherit;text-decoration:none;border-radius:20px">\n'
        '        <svg sc-camel-view-box="0 0 96 96" aria-hidden="true" '
        'style="flex:none;width:34px;height:34px;color:var(--primary,#4C662B)">'
        '<use href="#i-logo"></use></svg>',
        "the mark goes home")
    tpl = sub_once(tpl,
                   r'<span style="font-size:19px;font-weight:700;letter-spacing:-\.025em;'
                   r'white-space:nowrap">Flanner</span>\n        </sc-if>\n      </span>',
                   '<span style="font-size:19px;font-weight:700;letter-spacing:-.025em;'
                   'white-space:nowrap">Flanner</span>\n        </sc-if>\n      </a>',
                   "the mark goes home, closed")

    # The scrim behind it is the component's too — it is a page on a phone and
    # a card in the middle of one everywhere else.
    tpl = sub_once(
        tpl,
        r'  <div data-hide-scrollbar="" style="position:fixed;inset:0;z-index:70;'
        r'display:grid;justify-items:center;place-content:safe center;padding:24px;'
        r'overflow-y:auto;overscroll-behavior:contain;background:var\(--scrim,rgba\(20,24,14,\.32\)\);'
        r'animation:fp-fade \.18s cubic-bezier\(\.2,0,0,1\)">',
        '  <div data-hide-scrollbar="" style="{{ sheetScrimStyle }}">',
        "sheet scrim")

    # Two marks the card needs that the sprite does not carry. The anchor is
    # written back out in full: sub_once replaces with a plain string, so a
    # backreference here would be inserted as the two characters it is.
    tpl = sub_once(
        tpl, r'<symbol id="i-play-circle"',
        '<symbol id="i-play" sc-camel-view-box="0 0 24 24">'
        '<path d="M8 5.2v13.6L19 12z"></path></symbol>'
        '<symbol id="i-stop" sc-camel-view-box="0 0 24 24">'
        '<rect x="6.5" y="6.5" width="11" height="11" rx="2.5"></rect></symbol>'
        '<symbol id="i-play-circle"', "play and stop marks", flags=0)

    # ---- the filter card's one action ----
    # The card's foot carried a count, "Copy starred", "Clear stars" and
    # "Clear all" — three of them about the plan rather than about filtering,
    # in the one place a reader is filtering. The card keeps the action that
    # belongs to it, at the top right where a dialog's dismissive action goes;
    # starring is undone from the stars themselves.
    clear_all = (
        '<button sc-camel-on-click="{{ clearAll }}" style="display:inline-flex;'
        'align-items:center;height:40px;padding:0 14px;border:0;border-radius:20px;'
        'background:none;color:var(--primary,#4C662B);font-family:inherit;'
        'font-size:13.5px;font-weight:550;cursor:pointer" '
        'style-hover="background:var(--state-primary,rgba(76,102,43,.12))">Clear all</button>')
    tpl = sub_once(
        tpl,
        r'      <div style="display:flex;flex-wrap:wrap;align-items:center;gap:8px 18px;'
        r'margin-top:12px;padding-top:14px;border-top:1px solid var\(--outline,#C7CBBA\)">'
        r'.*?\n      </div>\n',
        "", "filter card foot")
    tpl = sub_once(
        tpl,
        r'    <section style="\{\{ filterPanelStyle \}\}" ref="\{\{ filterPanelRef \}\}" '
        r'data-hide-scrollbar="">\n',
        '    <section style="{{ filterPanelStyle }}" ref="{{ filterPanelRef }}" '
        'data-hide-scrollbar="">\n'
        '      <div style="display:flex;justify-content:flex-end;'
        'margin-block-end:-8px;padding-block-start:6px">' + clear_all + '</div>\n',
        "filter card clear all")

    # The one travelling indicator, behind the destinations it moves between.
    tpl = sub_once(
        tpl,
        r'  <div style="\{\{ navScrollStyle \}\}">\n    <sc-for list="\{\{ dests \}\}"',
        '  <div style="{{ navScrollStyle }}" ref="{{ navListRef }}">\n'
        '    <span data-fp-nav-pill="" aria-hidden="true" style="{{ navPillStyle }}"></span>\n'
        '    <sc-for list="{{ dests }}"',
        "nav indicator element")

    # ---- weather: the sample reading becomes the fetched one ----
    for _ in range(2):
        tpl = sub_once(tpl, r">21°<", ">{{ wxTemp }}<", "weather temperature")
        tpl = sub_once(tpl, r">Overcast<", ">{{ wxWord }}<", "weather word")
        tpl = sub_once(tpl, r'<use href="#wi-overcast"></use>',
                       '<use href="{{ wxIcon }}"></use>', "weather icon")
    tpl = sub_once(tpl, r">Rain likely 18:00–20:00\. The yards are unsheltered\.<",
                   ">{{ wxNote }}<", "weather note")

    # The forecast's own sentence sat 12 further in than everything else the
    # page writes — its card pads 12 and the paragraph padded 12 again — so it
    # did not line up with the About copy beside it. The card's padding is the
    # inset; the paragraph keeps only the air under it.
    tpl = sub_once(
        tpl,
        r'<p style="margin:0;padding:0 12px 14px;font-size:13px;',
        '<p style="margin:0;padding:0 0 14px;font-size:13px;',
        "weather note inset")

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
        tpl, r'<symbol id="wi-cloudy"',
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
        '<symbol id="wi-cloudy"', "daytime icons", flags=0)

    # The line under the map counts the stages it is drawing.
    tpl = sub_once(tpl, r">Five stages inside the Suvilahti yards\..*?<",
                   ">%d stages across %s. Pins sit on the organiser's own map "
                   "marks — tap one to see what is on.<"
                   % (len(fest.stages), f["city"].split(",")[0]), "map blurb")
    return tpl


# ── an app's scale, not a document's ──────────────────
# `user-scalable=no` is enough everywhere except Safari, which has ignored it
# since iOS 10 — deliberately, because a document a reader cannot zoom is a
# document a reader may not be able to read. This is not a document: every
# size on the page is already set for a phone, the timetable is dragged in two
# directions, and a pinch on it did nothing except leave the page at 1.4× with
# the navigation bar off the edge.
#
# So the two-finger gestures are refused, and only those: one finger still
# drags, scrolls and swipes, the map keeps its own pinch (it is a map), and a
# pointer device is left entirely alone — browser zoom there is untouched.
CARD_HTML = """    <div class="ac-host" style="{{ sheetHostStyle }}">
    <article class="{{ sheet.cardClass }}" role="dialog" aria-modal="true" aria-label="{{ sheet.title }}" style="{{ sheetStyle }}" ref="{{ sheetRef }}">
      <div class="ac__hero">
        <svg class="ac__art" sc-camel-view-box="0 0 400 250" sc-camel-preserve-aspect-ratio="xMidYMid slice" role="img" aria-label="{{ sheet.artLabel }}">
          <use href="#i-art"></use><use class="motif" href="{{ sheet.motif }}"></use>
        </svg>
        <div class="ac__scrim" aria-hidden="true"></div>
        <div class="ac__grab" aria-hidden="true"></div>
        <div class="ac__tools">
          <button class="ac__tool" type="button" sc-camel-on-click="{{ closeSheet }}" aria-label="Close">
            <svg sc-camel-view-box="0 0 24 24" aria-hidden="true" style="fill:currentColor"><use href="#i-close"></use></svg>
          </button>
        </div>
        <div class="ac__overlay">
          <p class="ac__eyebrow">{{ sheet.timeLine }}</p>
          <h2 class="ac__title">{{ sheet.title }}</h2>
          <button class="ac__where" type="button" sc-camel-on-click="{{ sheet.onNav }}" aria-label="{{ sheet.navLabel }}">
            <svg sc-camel-view-box="0 0 24 24" aria-hidden="true"><use href="#i-pin"></use></svg>
            <span>{{ sheet.stageLine }}</span>
            <svg class="ac__where-go" sc-camel-view-box="0 0 24 24" aria-hidden="true"><use href="#i-near"></use></svg>
          </button>
        </div>
      </div>

      <div class="ac__body" style="{{ sheetBodyStyle }}" ref="{{ sheetBodyRef }}">
        <div class="ac__col ac__col--a">
          <section class="{{ sheet.listenClass }}" aria-label="Listen">
            <sc-if value="{{ sheet.hasSources }}" hint-placeholder-val="{{ true }}">
              <div class="{{ sheet.embedClass }}">
                <iframe src="{{ sheet.embedSrc }}" title="{{ sheet.embedTitle }}" loading="lazy" allow="autoplay; encrypted-media; clipboard-write; picture-in-picture" allowfullscreen sc-camel-referrer-policy="strict-origin-when-cross-origin" sc-camel-on-load="{{ sheet.onEmbedLoad }}"></iframe>
                <sc-if value="{{ sheet.embedLoading }}" hint-placeholder-val="{{ true }}">
                  <div class="wave" role="progressbar" aria-label="Loading the player">
                    <svg class="wave__svg" sc-camel-view-box="0 0 96 24" sc-camel-preserve-aspect-ratio="none" aria-hidden="true">
                      <path class="wave__track" d="M0 12h96"></path>
                      <path class="wave__line" d="M-48 12q6-7 12 0t12 0 12 0 12 0 12 0 12 0 12 0 12 0 12 0 12 0 12 0 12 0"></path>
                    </svg>
                  </div>
                </sc-if>
              </div>
              <sc-if value="{{ sheet.showPlayerToggle }}">
                <button class="embed__more" type="button" sc-camel-on-click="{{ sheet.onPlayerToggle }}" aria-expanded="{{ sheet.playerOpen }}" aria-label="{{ sheet.playerLabel }}" title="{{ sheet.playerLabel }}">
                  <svg sc-camel-view-box="0 0 24 24" aria-hidden="true"><use href="#i-chev"></use></svg>
                </button>
              </sc-if>
            </sc-if>
            <sc-if value="{{ sheet.noSources }}">
              <div class="listen__row">
                <span class="listen__cover" aria-hidden="true">
                  <svg sc-camel-view-box="0 0 24 24"><use href="#i-play-circle"></use></svg>
                </span>
                <div class="listen__meta">
                  <p class="listen__title">{{ sheet.title }}</p>
                  <p class="listen__none">No preview in the programme data yet.</p>
                </div>
              </div>
            </sc-if>
          </section>
          <div class="ac__row">
          <ul class="links">
            <sc-for list="{{ sheet.links }}" as="l" hint-placeholder-count="4">
              <li><a href="{{ l.href }}" target="_blank" rel="noopener noreferrer" aria-label="{{ l.label }}" title="{{ l.label }}">
                <svg sc-camel-view-box="0 0 24 24" style="{{ l.iconStyle }}"><use href="{{ l.icon }}"></use></svg></a></li>
            </sc-for>
          </ul>
          <button class="ac__fav-btn" type="button" sc-camel-on-click="{{ sheet.onStar }}" aria-pressed="{{ sheet.starred }}" aria-label="{{ sheet.starLabel }}">
            <svg class="star__svg" sc-camel-view-box="0 0 24 24" aria-hidden="true">
              <defs><clipPath class="star__clip" id="{{ sheet.clipId }}" sc-camel-clip-path-units="userSpaceOnUse">
                <circle class="star__disc" cx="12" cy="12" r="19"></circle></clipPath></defs>
              <use class="star__outline" href="#i-star-geo"></use>
              <g class="star__clipped" clip-path="{{ sheet.clipUrl }}"><use class="star__fill" href="#i-star-geo"></use></g>
            </svg>
          </button>
          </div>
        </div>

        <div class="ac__col ac__col--b">
          <div class="{{ sheet.bioClass }}">
            <div class="bio__clip" style="{{ sheet.bioClipStyle }}" ref="{{ sheet.bioRef }}"><p class="bio__text">{{ sheet.intro }}</p></div>
            <sc-if value="{{ sheet.showBioToggle }}" hint-placeholder-val="{{ true }}">
              <button class="bio__more" type="button" sc-camel-on-click="{{ sheet.toggleBio }}" aria-expanded="{{ sheet.bioExpanded }}">
                <span>{{ sheet.bioToggleLabel }}</span>
                <svg sc-camel-view-box="0 0 24 24" aria-hidden="true"><use href="#i-chev"></use></svg>
              </button>
            </sc-if>
          </div>
          <ul class="tags">
            <sc-for list="{{ sheet.tags }}" as="t" hint-placeholder-count="3">
              <li>{{ t }}</li>
            </sc-for>
          </ul>
        </div>

        <hr class="ac__rule">
        <div class="ac__actions" style="{{ sheetActionsStyle }}">
          <button class="btn btn--plan" type="button" sc-camel-on-click="{{ sheet.onPlan }}" aria-pressed="{{ sheet.planned }}">
            <svg sc-camel-view-box="0 0 24 24" aria-hidden="true"><use href="{{ sheet.planIcon }}"></use></svg><span>{{ sheet.planLabel }}</span>
          </button>
        </div>
      </div>
    </article>
    </div>
"""


# ── the artist card ───────────────────────────────────
# The reference's own stylesheet, as it was written, from the strand themes to
# the end of the adaptive block. The planner already defines every colour token
# it names — the same names, generated for both themes — so only the five the
# card adds for itself are declared here. Nothing else is retyped or condensed:
# the card is the card.
CARD_CSS = """/* The card's colour names in the light theme. The design declares these
   only under [data-theme="dark"] — everywhere else it writes them inline as
   var(--x, #hex) fallbacks — so a stylesheet that uses them bare, as the
   reference does, would find nothing and drop the declaration: borders and
   rules disappeared. These are the reference's own light values, scoped so
   the design's dark block still wins in the dark. */
:root:not([data-theme="dark"]) {
  --wash:#FFFFFF; --low:#F8F7F3; --card:#F2F0EB; --card-a:#F7F1E8; --card-f:#F4F0F7;
  --hover:#EAE8DF; --on:#191D13; --on-var:#494E42; --outline:#C7CBBA;
  --primary:#4C662B; --sec:#DCE8C0; --on-sec:#1F2D0A; --plan:#2E4B12; --on-plan:#EDF6DA;
  --sec-a:#F2DFC3; --on-sec-a:#2B1700; --plan-a:#6B4310; --on-plan-a:#FFEEDC;
  --sec-f:#E8DEF8; --on-sec-f:#1D192B; --plan-f:#4F378B; --on-plan-f:#EADDFF;
  --dot-m:#A9CE88; --dot-a:#E5C193; --dot-f:#CFC1E8;
  --art-m-bg:#E7F0CF; --art-m-1:#CDEDA3; --art-m-ink:#31490F;
  --art-a-bg:#FBEBD3; --art-a-1:#FFDDB3; --art-a-2:#855318; --art-a-ink:#4A2A02;
  --art-f-bg:#EFE6FA; --art-f-2:#6750A4; --art-f-ink:#341E73;
  --state6:rgba(25,29,19,.055); --state8:rgba(25,29,19,.08); --state10:rgba(25,29,19,.10);
  --scrim:rgba(20,24,14,.32);
}

/* the five tokens the card adds for itself */
:root {
  /* on-hero colours sit on the wash, which is dark in both themes */
  --on-hero:#FFFFFF; --on-hero-dim:rgb(255 255 255 / .84);

  --ease:cubic-bezier(.2,0,0,1);
  --spring:400ms cubic-bezier(.34,1.36,.28,1);
  --effects:200ms cubic-bezier(.34,.80,.34,1);
  --elev-3:0 12px 48px rgba(20,24,14,.24);
}
[data-theme="dark"] { --elev-3:0 12px 48px rgba(0,0,0,.6); }

/* Strand themes — one class recolours chip, artwork, plan button and
   the accent. Nothing else in the card changes. */
.t-music { --surf:var(--card); --chip:var(--sec); --on-chip:var(--on-sec); --accent:var(--primary);
  --plan-bg:var(--sec); --plan-fg:var(--on-sec); --plan-on:var(--plan); --plan-on-fg:var(--on-plan);
  --art-bg:var(--art-m-bg); --art-1:var(--art-m-1); --art-2:var(--primary); --art-3:var(--dot-m); --art-ink:var(--art-m-ink);
  --hero-tint:#CDEDA3; }
.t-art { --surf:var(--card-a); --chip:var(--sec-a); --on-chip:var(--on-sec-a); --accent:var(--art-a-2);
  --plan-bg:var(--sec-a); --plan-fg:var(--on-sec-a); --plan-on:var(--plan-a); --plan-on-fg:var(--on-plan-a);
  --art-bg:var(--art-a-bg); --art-1:var(--art-a-1); --art-2:var(--art-a-2); --art-3:var(--dot-a); --art-ink:var(--art-a-ink);
  --hero-tint:#FFDDB3; }
.t-film { --surf:var(--card-f); --chip:var(--sec-f); --on-chip:var(--on-sec-f); --accent:var(--art-f-2);
  --plan-bg:var(--sec-f); --plan-fg:var(--on-sec-f); --plan-on:var(--plan-f); --plan-on-fg:var(--on-plan-f);
  --art-bg:var(--art-f-bg); --art-1:var(--on-plan-f); --art-2:var(--art-f-2); --art-3:var(--dot-f); --art-ink:var(--art-f-ink);
  --hero-tint:#EADDFF; }
[data-theme="dark"] .t-art { --accent:var(--art-a-2); }
[data-theme="dark"] .t-film { --accent:var(--art-f-2); }

*, *::before, *::after { box-sizing: border-box; }

/* ============================================================
   2 · CARD
   ============================================================ */
.ac-host { container-type: inline-size; container-name: ac; }
.ac {
  display: grid;
  padding: 12px 12px 16px;
  border-radius: 28px;
  background: var(--surf);
  color: var(--on);
  font-family: "Inter", "Segoe UI", system-ui, -apple-system, sans-serif;
  font-size: 15px;
  box-shadow: var(--elev-3);
  -webkit-font-smoothing: antialiased;
}
.ac__body { padding: 0 8px; display: grid; min-inline-size: 0; }

/* ---------- hero ---------- */
/* Departure from the reference, which frames a photograph: 16/10 with a
   218px floor. There is no photograph here — the artwork is drawn from the
   act's own palette and reads at any height — so a picture's proportions
   bought nothing but empty tint between the close button and the name. The
   band is as tall as what stands in it: a row that keeps the close button
   clear, then the name block, then the padding under it. A one-line name on
   a phone comes to 159px where the frame gave 218. */
.ac__hero {
  position: relative; display: grid; align-content: end;
  padding-block-start: 60px; min-block-size: 152px;
  border-radius: 20px; overflow: hidden; background: var(--art-bg);
}
.ac__art { position: absolute; inset: 0; inline-size: 100%; block-size: 100%; }

/* A flat wash, not a gradient: an even tint darkens the whole picture
   by a known amount, so the name keeps its contrast wherever the
   image happens to be light. */
.ac__scrim { position: absolute; inset: 0; background: rgb(0 0 0 / .46); }

.ac__overlay { position: relative; z-index: 1; display: grid; gap: 7px; padding: 0 20px 18px; }
.ac__eyebrow {
  margin: 0; font-size: 12px; font-weight: 700; letter-spacing: .1em;
  /* white rather than the strand's tint: the picture already carries the
     festival's colour, and a third one over it was one too many */
  text-transform: uppercase; color: var(--on-hero-dim,rgb(255 255 255 / .84));
}
.ac__title {
  margin: 0; padding-inline-end: 4px; color: var(--on-hero);
  font-size: clamp(22px, 5.4cqi, 30px); font-weight: 700;
  line-height: 1.08; letter-spacing: -.03em; text-wrap: balance;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
}
/* The reference cuts a notch into the corner of the hero and stands a chip in
   it, and reserved this row's end for it. The chip named the stage, which the
   row itself names and links to, so it is gone from the markup and the row
   has its end back. */
.ac__where {
  display: flex; align-items: center; gap: 8px; margin: 1px 0 0;
  padding-inline-end: 4px;
  font-size: 13.5px; font-weight: 500; color: var(--on-hero-dim); min-inline-size: 0;
}
.ac__where span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ac__where svg { flex: none; inline-size: 17px; block-size: 17px; fill: currentColor; }

.ac__tools { position: absolute; inset-block-start: 10px; inset-inline-end: 10px; z-index: 2; display: flex; gap: 8px; }
.ac__tool {
  display: grid; place-items: center; inline-size: 44px; block-size: 44px;
  border: 0; border-radius: 50%; background: rgb(255 255 255 / .18);
  -webkit-backdrop-filter: blur(10px); backdrop-filter: blur(10px);
  color: #FFFFFF; cursor: pointer; transition: background var(--effects), color var(--effects);
}
.ac__tool svg { inline-size: 21px; block-size: 21px; }
.ac__tool:hover { background: rgb(255 255 255 / .30); }
.ac__tool:focus-visible { outline: 2px solid #FFFFFF; outline-offset: 2px; }
.ac__tool[aria-pressed="true"] { background: var(--chip); color: var(--on-chip); }
.ac__tool svg use[href="#i-close"] { fill: currentColor; }

/* the planner's star: an outline flooded by a growing clip disc */
.star__svg { overflow: visible; }
.star__disc { transform: scale(0); transform-origin: 12px 12px; transition: transform .34s cubic-bezier(.34,1.3,.64,1); }
.ac__tool[aria-pressed="true"] .star__disc { transform: scale(1); }
.star__outline { fill: none; stroke: currentColor; stroke-width: 1.8; stroke-linejoin: round; transition: opacity .2s ease; }
.ac__tool[aria-pressed="true"] .star__outline { opacity: 0; transition-delay: .12s; }
.star__fill { fill: currentColor; stroke: none; }

/* notch + chip — the card system's signature */
.ac__notch {
  position: absolute; z-index: 1; inset-block-end: 0; inset-inline-end: 0;
  padding: 6px 0 0 6px; background: var(--surf); border-start-start-radius: 22px;
}
.ac__notch i {
  position: absolute; inline-size: 12px; block-size: 12px;
  background: radial-gradient(circle at 0 0, #0000 11.5px, var(--surf) 12.5px);
}
.ac__notch i:first-child { inset-inline-end: 0; inset-block-end: 100%; }
.ac__notch i:last-child { inset-inline-end: 100%; inset-block-end: 0; }
.ac__chip {
  display: block; padding: 9px 16px;
  border-start-start-radius: 16px; border-end-end-radius: 20px;
  background: var(--chip); color: var(--on-chip);
  font-family: inherit; font-size: 12px; line-height: 1; font-weight: 700;
  letter-spacing: .09em; text-transform: uppercase;
}

/* ============================================================
   3 · LISTEN
   A facade: no iframe exists, and nothing is requested from YouTube
   or Spotify, until play is pressed.
   ============================================================ */
/* A relative tint, not a named surface: --card is the music card's own
   background, so a fixed value made the well disappear on that strand. */
.listen { margin-block-start: 16px; padding: 8px; border-radius: 28px; background: var(--state6); }
.listen__row { display: flex; align-items: center; gap: 14px; }

.listen__cover {
  position: relative; flex: none; inline-size: 56px; block-size: 56px;
  border-radius: 18px; overflow: hidden; background: var(--art-bg);
}
.listen__cover svg { display: block; inline-size: 100%; block-size: 100%; }

.listen__meta { flex: 1 1 auto; min-inline-size: 0; display: grid; gap: 4px; }
.listen__title {
  margin: 0; font-size: 15px; font-weight: 650; letter-spacing: -.01em; line-height: 1.2;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.listen__src {
  display: inline-flex; align-items: center; gap: 7px; margin: 0;
  font-size: 12.5px; font-weight: 500; color: var(--on-var);
}
.listen__src svg { flex: none; inline-size: 15px; block-size: 15px; }
.listen__none { margin: 0; font-size: 12.5px; line-height: 1.4; color: var(--on-var); }

/* two sources: the label line becomes a connected button group —
   filled segments, no strokes, selected one rounds to a pill */
.srcs { display: inline-flex; gap: 3px; }
.srcs__btn {
  display: inline-flex; align-items: center; gap: 6px;
  block-size: 30px; padding: 0 11px; border: 0; border-radius: 6px;
  background: var(--state6); color: var(--on-var);
  font-family: inherit; font-size: 11.5px; line-height: 1; font-weight: 600;
  cursor: pointer; white-space: nowrap;
  -webkit-tap-highlight-color: transparent;
  transition: background var(--effects), color var(--effects), border-radius .35s cubic-bezier(.42,1.67,.21,.9);
}
.srcs__btn:first-child { border-start-start-radius: 15px; border-end-start-radius: 15px; }
.srcs__btn:last-child { border-start-end-radius: 15px; border-end-end-radius: 15px; }
.srcs__btn svg { flex: none; inline-size: 14px; block-size: 14px; }
.srcs__btn:hover { background: var(--state8); }
.srcs__btn:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.srcs__btn[aria-pressed="true"] { border-radius: 15px; background: var(--chip); color: var(--on-chip); }

/* circle at rest, squircle when pressed — the shape morph the plan
   button already uses elsewhere in the app */
.listen__play {
  flex: none; display: grid; place-items: center;
  inline-size: 56px; block-size: 56px; border: 0; border-radius: 28px;
  background: var(--plan-on); color: var(--plan-on-fg);
  cursor: pointer; -webkit-tap-highlight-color: transparent;
  transition: border-radius .35s cubic-bezier(.42,1.67,.21,.9), background var(--effects);
}
.listen__play svg { inline-size: 26px; block-size: 26px; fill: currentColor; }
.listen__play:hover { border-radius: 18px; }
.listen__play:active { border-radius: 16px; }
.listen__play:focus-visible { outline: 2px solid var(--accent); outline-offset: 3px; }

.listen__embed { margin-block-start: 8px; border-radius: 20px; overflow: hidden; }
.listen__embed[hidden] { display: none; }
.listen__embed iframe { display: block; inline-size: 100%; border: 0; }
.listen__embed--yt iframe { aspect-ratio: 16 / 9; block-size: auto; }
.listen__embed--sp iframe { block-size: 152px; }

.listen--empty { background: var(--state6); }
.listen--empty .listen__cover { display: grid; place-items: center; background: var(--state6); }
.listen--empty .listen__cover svg { inline-size: 24px; block-size: 24px; fill: var(--on-var); opacity: .7; }

/* ============================================================
   4 · BIOGRAPHY — three lines, then on request
   ============================================================ */
.bio { margin-block-start: 20px; }
.bio__clip { overflow: hidden; max-block-size: calc(3 * 1.55em); transition: max-block-size 340ms var(--ease); }
.bio__text { margin: 0; font-size: 15px; line-height: 1.55; color: var(--on-var); }
.bio__more {
  display: inline-flex; align-items: center; gap: 6px;
  margin-block-start: 8px; padding: 8px 14px 8px 12px; min-block-size: 40px;
  border: 0; border-radius: 20px; background: none; color: var(--accent);
  font-family: inherit; font-size: 14px; line-height: 1; font-weight: 700;
  cursor: pointer; transition: background var(--effects);
}
.bio__more:hover { background: var(--state8); }
.bio__more:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.bio__more svg { inline-size: 18px; block-size: 18px; fill: currentColor; transition: transform var(--spring); }
.bio.is-open .bio__more svg { transform: rotate(180deg); }
.bio__more[hidden] { display: none; }

/* ---------- links ---------- */
.links { display: flex; flex-wrap: wrap; gap: 8px; margin-block-start: 18px; padding: 0; list-style: none; }
.links a {
  display: grid; place-items: center; inline-size: 44px; block-size: 44px;
  border-radius: 50%; background: var(--state6); color: var(--on-var);
  text-decoration: none; transition: background var(--effects), color var(--effects);
}
.links svg { inline-size: 20px; block-size: 20px; }
.links a:hover { background: var(--chip); color: var(--on-chip); }
.links a:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }

/* ---------- tags ---------- */
.tags { display: flex; flex-wrap: wrap; gap: 8px; margin: 18px 0 0; padding: 0; list-style: none; }
.tags li {
  display: inline-flex; align-items: center; block-size: 32px; padding: 0 16px;
  border: 1px solid var(--outline); border-radius: 8px;
  font-size: 14px; font-weight: 500; line-height: 20px; color: var(--on-var);
}

/* ---------- actions ---------- */
.ac__rule { margin: 20px 0 0; block-size: 1px; border: 0; background: var(--outline); }
.ac__actions { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; margin-block-start: 16px; }
.btn {
  display: inline-flex; align-items: center; justify-content: center; gap: 8px;
  block-size: 44px; padding: 0 20px 0 16px; border-radius: 22px;
  font-family: inherit; font-size: 14px; line-height: 1; font-weight: 500;
  letter-spacing: .006em; cursor: pointer; border: 0;
  transition: background var(--effects);
}
.btn svg { inline-size: 20px; block-size: 20px; fill: currentColor; }
.btn--outlined { border: 1px solid var(--outline); background: transparent; color: var(--on); }
.btn--outlined:hover { background: var(--state8); }
.btn:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
/* filled tonal, shape-morphing on selection like the festival card's */
.btn--plan {
  margin-inline-start: auto; border-radius: 12px;
  background: var(--plan-bg); color: var(--plan-fg);
  transition: background var(--effects), color var(--effects), border-radius .35s cubic-bezier(.42,1.67,.21,.9);
}
.btn--plan[aria-pressed="true"] { border-radius: 22px; background: var(--plan-on); color: var(--plan-on-fg); }

/* ============================================================
   5 · ADAPTIVE
   ============================================================ */
@container ac (min-width: 700px) {
  /* 236px in the reference; the same reasoning as above, one step taller
     than the phone's so the band still reads as a header over two columns. */
  .ac__hero { block-size: auto; min-block-size: 176px; }
  .ac__body { grid-template-columns: minmax(0,1fr) minmax(0,1fr); column-gap: 28px; padding: 0 10px; }
  .ac__col { display: grid; align-content: start; }
  .ac__col--a { grid-column: 1; }
  .ac__col--b { grid-column: 2; }
  .ac__rule, .ac__actions { grid-column: 1 / -1; }
  .bio { margin-block-start: 16px; }
  .tags { margin-block-start: 16px; }
}
/* below that the columns dissolve and everything runs in one flow */
@container ac (max-width: 699px) {
  .ac__col { display: contents; }
  /* Departure from the reference, which lays the body out as a grid of auto
     rows. On a phone the card is the whole screen, and auto rows in a grid
     taller than its content share the slack out between them: every block
     stood a little further from the last than it was written to, and the
     spacing the design set — 12, 18, 20 — read as one loose column. The
     blocks keep their own margins now, and the slack collects in one place,
     above the divider, so the two actions sit at the foot of the card. */
  .ac__body { display: flex; flex-direction: column; }
  /* The 20px the design leaves above the divider becomes a transparent
     border, so an auto margin can take the slack without ever closing that
     gap up. The rule paints its content box alone and stays 1px. */
  .ac__rule {
    margin-block-start: auto; border-block-start: 20px solid transparent;
    background-clip: content-box; box-sizing: content-box;
  }
}
@container ac (max-width: 400px) {
  .ac { padding: 10px 10px 14px; }
  .ac__body { padding: 0 6px; }
  .ac__overlay { padding: 0 16px 15px; gap: 6px; }
  .ac__where { font-size: 13px; }
  .listen__cover, .listen__play { inline-size: 50px; block-size: 50px; }
  .btn--plan { flex-basis: 100%; margin-inline-start: 0; }
  .btn--outlined { flex: 1 1 auto; }
}
/* ---- the stage label is the way to the map ----
   It was a line of text; it is the only route to the stage now that the
   Navigate button has gone, so it is a control and reads as one: the hero's
   own translucent surface, the same one its two icon buttons use, with a
   state layer and the arrow the button used to carry. */
.ac__where {
  /* The overlay is a grid, which stretches its rows: inline-flex alone left
     the pill running the width of the hero with the name in one end of it. */
  display: inline-flex; justify-self: start; align-items: center; gap: 8px;
  margin: 3px 0 0; max-inline-size: 100%;
  padding: 7px 12px 7px 10px; border: 0; border-radius: 20px;
  background: rgb(255 255 255 / .16);
  -webkit-backdrop-filter: blur(10px); backdrop-filter: blur(10px);
  color: var(--on-hero); font-family: inherit; font-size: 13.5px;
  font-weight: 500; line-height: 1.2; text-align: start; cursor: pointer;
  -webkit-tap-highlight-color: transparent;
  transition: background var(--effects);
}
.ac__where:hover { background: rgb(255 255 255 / .30); }
.ac__where:active { background: rgb(255 255 255 / .38); }
.ac__where:focus-visible { outline: 2px solid #FFFFFF; outline-offset: 2px; }
.ac__where-go { opacity: .8; }

/* ---- the star, under the player and against its right edge ----
   Off the artwork, so it takes the surface treatment the link buttons use
   rather than the hero's glass. */
/* One row: the act's own pages on the left, the star against the right edge
   of the player above it. */
.ac__row { display: flex; align-items: center; gap: 8px; margin-block-start: 12px; }
/* The list's own bottom margin would push the star 8px below the links it
   sits beside. */
.ac__row .links { flex: 1 1 auto; margin: 0; }
.ac__fav-btn { margin-inline-start: auto; }
.ac__fav-btn {
  display: grid; place-items: center; inline-size: 44px; block-size: 44px;
  border: 0; border-radius: 50%; background: var(--state6);
  color: var(--on-var); cursor: pointer;
  -webkit-tap-highlight-color: transparent;
  transition: background var(--effects), color var(--effects);
}
.ac__fav-btn svg { inline-size: 22px; block-size: 22px; }
.ac__fav-btn:hover { background: var(--state8); }
.ac__fav-btn:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.ac__fav-btn[aria-pressed="true"] { background: var(--chip); color: var(--on-chip); }

/* ---- the player's loading indicator ----
   M3's wavy linear indicator: a 4dp active line on a dim track, the wave
   travelling one wavelength a second while an indeterminate window sweeps
   across it. Drawn rather than imported — one SVG path, the card's accent,
   and it stops dead for anyone who has asked for less motion. */
.wave {
  position: absolute; inset-inline: 24px; inset-block-start: 50%;
  translate: 0 -50%; block-size: 24px; pointer-events: none;
}
.wave__svg { display: block; inline-size: 100%; block-size: 100%; overflow: visible; }
.wave__track {
  fill: none; stroke: var(--state10); stroke-width: 4; stroke-linecap: round;
}
.wave__line {
  fill: none; stroke: var(--accent); stroke-width: 4;
  stroke-linecap: round; stroke-linejoin: round;
  animation: wave-travel 1s linear infinite, wave-sweep 2s cubic-bezier(.2,0,0,1) infinite;
}
@keyframes wave-travel { to { transform: translateX(24px); } }
@keyframes wave-sweep {
  0%   { clip-path: inset(0 100% 0 0); }
  45%  { clip-path: inset(0 0 0 0); }
  55%  { clip-path: inset(0 0 0 0); }
  100% { clip-path: inset(0 0 0 100%); }
}
@media (prefers-reduced-motion: reduce) {
  .wave__line { animation: none; }
}

/* On a phone everything runs in one column, and the reference's 18-20px
   between blocks reads as a gap when the player above it is 352px tall. */
@container ac (max-width: 699px) {
  /* The same gap above the row as below it: the player, the row, the text. */
  .ac__row { margin-block-start: 12px; }
  .bio { margin-block-start: 12px; }
  .tags { margin-block-start: 12px; }
}

/* The corner chip names the stage the act is on, so it is a name and reads
   like one: sentence case, medium weight, a size down from the reference's
   all-caps label. */
.ac__chip { font-size: 11.5px; font-weight: 500; letter-spacing: .01em;
  text-transform: none; padding: 8px 14px; }

/* The player is Spotify's own card, shown at the height Spotify draws it —
   the reference's 152px is the compact bar, which clips an artist's track
   list mid-row. Nothing of ours stands over it: no cover, no name, no play
   button, since the embed carries all three. */
/* A flex column, so the whitespace between the template's tags cannot leave
   a stray 4px line box under the player and make the gap above the row
   larger than the one below it. */
.listen { display: flex; flex-direction: column; padding: 0; background: none; }
.listen__embed { position: relative; margin-block-start: 0; }
.listen__embed--sp iframe { block-size: 352px; }
.listen:has(.listen__none) { padding: 8px; background: var(--state6,rgba(25,29,19,.055)); }

@media (prefers-reduced-motion: reduce) {
  /* Scoped to the card. The reference is a page of nothing but cards, so it
     writes this at the root; here that would stop every animation on the
     planner, including ones the design decides for itself. */
  .ac, .ac *, .ac *::before, .ac *::after { animation-duration:.01ms !important; transition-duration:.01ms !important; }
}
"""

# ── the card is a bottom sheet on a phone ─────────────
# The phone shell draws the act as a page of its own, which is what a screen
# that narrow has room for — but a page arrives by replacing what you were
# reading, and this one is an aside from the grid you are still in. M3 has the
# component for that: a modal bottom sheet. It rises from the edge it is
# dragged from, keeps the top of the screen showing so the timetable is still
# there behind it, and carries the handle that says it can be dragged.
#
# Its height is its content's. A card with a player, an introduction and four
# tags fills the screen; one with a name and two tags is a third of it, and
# standing that at full height left the reader looking at an empty column with
# the action stranded at the bottom of it.
#
# The page behind it steps back as it arrives — scaled a little and rounded,
# the way M3's own sheets treat what they cover — so the card reads as the
# thing being looked at rather than as another page in the stack.
#
# The scoping is the shell's own breakpoint: mode() returns 'bar' below 640,
# which is exactly the width this media query starts at. Nothing above it
# changes — the tablet and the desktop keep the container transform that grows
# the card out of the cell that was pressed.
SHEET_CSS = """/* ---- modal bottom sheet, phone only ---- */
:root{--sheet-gap:calc(56px + env(safe-area-inset-top,0px))}
[data-fp-shell]{transform-origin:50% 0}
@media (max-width:639.98px){
  [data-fp-shell]{
    transition:transform .44s cubic-bezier(.2,0,0,1),border-radius .44s cubic-bezier(.2,0,0,1)}
  body.fp-sheet [data-fp-shell]{
    transform:scale(.94) translateY(8px);border-radius:28px;overflow:clip}
  /* M3's drag handle: 32×4, on the surface it sits on at 40%. The hero is
     dark under both themes, so it is drawn in white. */
  .ac__grab{
    position:absolute;inset-block-start:8px;inset-inline-start:50%;
    transform:translateX(-50%);z-index:3;inline-size:32px;block-size:4px;
    border-radius:2px;background:rgb(255 255 255 / .4);pointer-events:none}
  .ac__hero{padding-block-start:64px}
}
@media (min-width:640px){ .ac__grab{display:none} }
@media (prefers-reduced-motion:reduce){
  [data-fp-shell]{transition:none}
}

/* ---- the player opens, phone only ----
   Spotify draws two cards from the same URL: a 152px bar with the act, its
   Follow and its play button, and a 352px one with the first three tracks
   under it. The tall one is most of a phone screen before the introduction
   has started, so the card opens with the bar and the reader asks for the
   rest. The ask is M3's own expand: the chevron that says which way it goes,
   turning as it goes, and the height on the emphasised curve — a change of
   size is a spatial change, so it takes the spatial duration, while the
   chevron is a change of state and takes the shorter one. */
.embed__more{display:none}
@media (max-width:639.98px){
  .listen__embed--sp,.listen__embed--sp iframe{
    block-size:152px;transition:block-size .5s cubic-bezier(.2,0,0,1)}
  .listen__embed--sp.is-open,.listen__embed--sp.is-open iframe{block-size:352px}
  /* A surface of its own, the width of the player and shallow-cornered
     against its 20: a control under the card rather than a glyph floating
     below it. */
  .embed__more{
    display:flex;align-items:center;justify-content:center;
    inline-size:100%;min-block-size:32px;margin-block-start:6px;
    padding:0;border:0;border-radius:12px;
    background:var(--state6,rgba(25,29,19,.055));
    color:var(--on-var,#494E42);cursor:pointer;
    -webkit-tap-highlight-color:transparent;
    transition:background .2s cubic-bezier(.2,0,0,1)}
  .embed__more:hover{background:var(--state8,rgba(25,29,19,.08))}
  .embed__more:active{background:var(--state9,rgba(25,29,19,.09))}
  .embed__more:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
  .embed__more svg{
    inline-size:18px;block-size:18px;fill:currentColor;
    transition:transform .3s cubic-bezier(.2,0,0,1)}
  .embed__more[aria-expanded="true"] svg{transform:rotate(180deg)}
}
@media (prefers-reduced-motion:reduce){
  .listen__embed--sp,.listen__embed--sp iframe,.embed__more svg{transition:none}
}

/* ---- the map's own furniture ----
   Leaflet ships the controls of 2011: white squares with a 1px border and a
   4px corner, a popup with a hairline and a drop shadow, an attribution strip
   in 11px grey. The map underneath is the festival's; these are the page's,
   so they are drawn as the page draws its own — surface-container under M3's
   level-1 elevation, the shape scale for the corners, and the type scale for
   the words. */
.leaflet-container{font-family:inherit}
.leaflet-bar,.leaflet-touch .leaflet-bar{
  border:0;border-radius:16px;overflow:hidden;
  box-shadow:0 1px 2px rgba(20,24,14,.24),0 1px 3px 1px rgba(20,24,14,.12)}
.leaflet-bar a,.leaflet-touch .leaflet-bar a{
  inline-size:40px;block-size:40px;line-height:40px;
  border:0;border-block-end:1px solid var(--outline-variant,rgba(25,29,19,.10));
  background:var(--card,#F2F0EB);color:var(--on-var,#494E42);
  font-family:inherit;font-size:20px;font-weight:500;
  transition:background .2s cubic-bezier(.2,0,0,1)}
.leaflet-bar a:last-child,.leaflet-touch .leaflet-bar a:last-child{border-block-end:0}
.leaflet-bar a:hover,.leaflet-touch .leaflet-bar a:hover{
  background:var(--state8,rgba(25,29,19,.08))}
.leaflet-bar a.leaflet-disabled{background:var(--card,#F2F0EB);opacity:.38}
.leaflet-control-zoom{margin:12px}
.leaflet-popup-content-wrapper{
  border-radius:16px;background:var(--card,#F2F0EB);color:var(--on,#191D13);
  box-shadow:0 1px 2px rgba(20,24,14,.24),0 2px 6px 2px rgba(20,24,14,.12)}
.leaflet-popup-content{margin:12px 16px;font-family:inherit}
.leaflet-popup-tip{background:var(--card,#F2F0EB);box-shadow:none}
.leaflet-container a.leaflet-popup-close-button{
  inline-size:36px;block-size:36px;padding:0;line-height:36px;
  color:var(--on-var,#494E42);font-size:18px}
.leaflet-control-attribution{
  padding:2px 8px;border-start-start-radius:12px;
  background:color-mix(in srgb,var(--card,#F2F0EB) 82%,transparent);
  color:var(--on-var,#494E42);
  font-family:inherit;font-size:11px;line-height:16px;letter-spacing:.5px}
.leaflet-control-attribution a{color:var(--primary,#4C662B)}

/* ---- the pin answers when its stage is pressed ----
   Two beats to the round and three rounds, the way a heart does it, over
   three rings that leave the pin half a second apart. The pin keeps its
   rotation through the beat — it is a teardrop turned 45° — and both are the
   stage's own colour. */
@keyframes fp-beat{
  0%{transform:rotate(-45deg) scale(1)}
  12%{transform:rotate(-45deg) scale(1.24)}
  24%{transform:rotate(-45deg) scale(1)}
  36%{transform:rotate(-45deg) scale(1.14)}
  52%{transform:rotate(-45deg) scale(1)}
  100%{transform:rotate(-45deg) scale(1)}
}
@keyframes fp-ripple{
  0%{transform:scale(.42);opacity:.6}
  70%{opacity:.14}
  100%{transform:scale(2.9);opacity:0}
}
/* ---- the sound level in the Live chip ----
   Three bars, a second to the cycle, a third of a cycle apart, on the
   standard curve in and out. It says one thing — this is on now — and says it
   quietly enough to be read past. */
@keyframes fp-live{
  0%,100%{transform:scaleY(.35)}
  50%{transform:scaleY(1)}
}
@media (prefers-reduced-motion:reduce){
  [style*="fp-live"]{animation:none!important;transform:scaleY(.7)}
}

/* A pin is the colour of the cells in its column. */
[data-fp-pin]{
  background:var(--pin,var(--sec,#DCE8C0));color:var(--pin-on,var(--on-sec,#1F2D0A));
  transition:background .3s cubic-bezier(.2,0,0,1),color .3s cubic-bezier(.2,0,0,1)}
@media (prefers-reduced-motion:reduce){
  /* The map still travels to the stage; it just does not beat about it. */
  [style*="fp-beat"],[style*="fp-ripple"]{animation:none!important}
}

/* ---- the measure ----
   M3 puts a readable line at 40–60 characters. Nothing in the planner is
   justified: every measure here is a card's width, and justification needs a
   line long enough to absorb the stretch — under about 55 characters the
   spaces open so far to reach the right edge that the paragraph reads as full
   of holes. The written pages, which hold a 66ch column, are where the site
   justifies. What the planner takes from the same rule is the ceiling, for
   the two paragraphs it has outside the card. */
[data-fp-shell] p{max-inline-size:66ch}
/* The introduction was set at 15/1.55, between the type scale's two body
   sizes. At Body Medium it is the size every other piece of supporting text
   in the card is. */
.bio__text{font-size:14px;line-height:20px;letter-spacing:.25px}"""

# ── the festival, at the compact breakpoint ───────────
# The phone's festival card is a second exported design, festival-mobile.html,
# and this is its stylesheet as written: the hero and its notch, the status
# chips, the headline and its meta list, the genre rail, the actions and the
# About block, rule for rule and value for value.
#
# One departure, and it is mechanical: every selector is prefixed with .fest.
# The design is a page of its own, so it names things .hero, .title, .chip,
# .actions — names a planner carrying an artist card, a map and a timetable
# cannot leave unqualified. The prefix scopes them and changes nothing about
# what they draw.
#
# The type scale it declares on :root is declared on .fest here, for the same
# reason: the planner has its own and they are not the same numbers.
FEST_CSS = """/* ---------- the festival, compact ---------- */
/* The design's own type scale, which it declares on the root and this page
   cannot: the planner's root already carries a scale of its own. The colour
   roles it declares there are the planner's roles under the planner's names,
   so they are simply used; the artwork's five come from the strand class the
   card system already puts on the element. The measures are the design's:
   16dp margins, and the room the floating bar stands in. */
.fest{
  /* a step down the M3 scale from the design's 32, which was drawn for a
     three-word name and set a festival's full name across two lines */
  --headline-size:28px; --headline-lh:1.08;
  --title-size:17px;
  --body-size:15px;   --body-lh:1.55;
  --body-sm-size:14px;
  --label-size:14px;  --label-sm-size:11.5px;
  font-size:var(--body-size); line-height:var(--body-lh);
  /* the design's 16dp margin, over the 12 the view already keeps; the room
     the bar stands in is kept by the scroller above this. */
  padding: 8px 4px 0;
}

/* ---------- hero ---------- */
/* This page runs on two edges, and they are the planner's own: text and the
   controls that stand in the text stay on the 16dp margin, with the bar's
   title and the programme's headings; a surface sits 4px outside it, where
   every card and every row in the app already sits. So the two surfaces the
   design brings — the artwork and the About card — come out to meet the
   weather card under them rather than standing 4px in from it. */
/* One surface holds what the festival is: its picture, what it plays and
   what you can do about it. The card system's own proportions — a 12px inset
   around a 20px picture inside a 28px corner — so it stands with the About
   card under it rather than as three loose things. */
.fest .fcard {
  margin-inline: -4px; padding: 12px 12px 16px;
  border-radius: 28px; background: var(--card);
}
.fest .hero {
  position: relative; display: grid; align-content: end;
  aspect-ratio: 16 / 10;
  border-radius: 20px; overflow: hidden; background: var(--art-bg);
}
/* The festival says what it is the way an act does: the card's own hero,
   rule for rule — the flat wash rather than a gradient, so the line keeps
   its contrast wherever the picture happens to be light; the date over the
   name in the strand's tint; and the place as the pill that goes to the
   map. Which is why nothing under the picture repeats them. */
.fest .hero__overlay {
  position: relative; z-index: 1; display: grid; gap: 6px; padding: 0 16px 15px;
}
.fest .hero__eyebrow {
  margin: 0; font-size: 12px; font-weight: 700; letter-spacing: .1em;
  /* white rather than the strand's tint: the picture already carries the
     festival's colour, and a third one over it was one too many */
  text-transform: uppercase; color: var(--on-hero-dim,rgb(255 255 255 / .84));
}
.fest .hero__title {
  margin: 0; padding-inline-end: 4px; color: var(--on-hero,#FFFFFF);
  font-size: 26px; font-weight: 700; line-height: 1.08; letter-spacing: -.03em;
  text-wrap: balance;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
}
.fest .hero__where {
  display: inline-flex; justify-self: start; align-items: center; gap: 8px;
  margin: 3px 0 0; max-inline-size: 100%;
  padding: 7px 12px 7px 10px; border: 0; border-radius: 20px;
  background: rgb(255 255 255 / .16);
  -webkit-backdrop-filter: blur(10px); backdrop-filter: blur(10px);
  color: var(--on-hero,#FFFFFF); font-family: inherit; font-size: 13px;
  font-weight: 500; line-height: 1.2; text-align: start; cursor: pointer;
  -webkit-tap-highlight-color: transparent;
  transition: background var(--effects);
}
.fest .hero__where:hover { background: rgb(255 255 255 / .30); }
.fest .hero__where:active { background: rgb(255 255 255 / .38); }
.fest .hero__where:focus-visible { outline: 2px solid #FFFFFF; outline-offset: 2px; }
.fest .hero__where span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.fest .hero__where svg { flex: none; inline-size: 17px; block-size: 17px; fill: currentColor; }
.fest .hero__where-go { opacity: .8; }
.fest .hero__art { position: absolute; inset: 0; inline-size: 100%; block-size: 100%; }
.fest .hero__photo {
  position: absolute; inset: 0; inline-size: 100%; block-size: 100%;
  object-fit: cover; display: block;
}
/* Only where the mark stands: the picture keeps its own light everywhere
   else, and a scrim over all of it would read as a dimmed photograph
   rather than as a surface something is written on. */
.fest .hero__scrim {
  position: absolute; inset: 0; pointer-events: none; background: rgb(0 0 0 / .46);
}
/* the card system's notch, cutting into the page rather than a card */
.fest .notch {
  position: absolute; inset-block-end: 0; inset-inline-end: 0;
  padding: 6px 0 0 6px; background: var(--wash,#FFFFFF); border-start-start-radius: 22px;
}
.fest .notch i {
  position: absolute; inline-size: 12px; block-size: 12px;
  background: radial-gradient(circle at 0 0,#0000 11.5px,var(--wash,#FFFFFF) 12.5px);
}
.fest .notch i:first-child { inset-inline-end: 0; inset-block-end: 100%; }
.fest .notch i:last-child { inset-inline-end: 100%; inset-block-end: 0; }
.fest .notch span {
  display: block; padding: 9px 16px;
  border-start-start-radius: 16px; border-end-end-radius: 20px;
  background: var(--sec); color: var(--on-sec);
  font-size: var(--label-sm-size); font-weight: 700; line-height: 1;
  letter-spacing: .1em; text-transform: uppercase;
}

/* ---------- status row (M3 assist chips, 32dp) ---------- */
.fest .status { display: flex; flex-wrap: wrap; gap: 8px; margin-block-start: 14px; }
.fest .chip {
  display: inline-flex; align-items: center; gap: 8px;
  block-size: 32px; padding: 0 14px 0 10px;
  border: 1px solid var(--outline); border-radius: 8px;
  background: transparent; color: var(--on-var);
  font-size: 13.5px; font-weight: 500; line-height: 1; font-family: inherit;
  cursor: pointer; transition: background var(--effects);
}
.fest .chip:hover { background: var(--state8); }
.fest .chip svg { flex: none; inline-size: 18px; block-size: 18px; fill: currentColor; }
.fest .chip--live { border-color: transparent; background: var(--sec); color: var(--on-sec); font-weight: 600; }
.fest .chip--live b {
  inline-size: 8px; block-size: 8px; border-radius: 50%; background: var(--primary);
  animation: fp-fest-pulse 2s var(--ease) infinite;
}
@keyframes fp-fest-pulse { 0%,100% { opacity: 1; transform: scale(1); } 50% { opacity: .45; transform: scale(.78); } }

/* ---------- headline + meta ---------- */
.fest .title {
  margin: 12px 0 0;
  font-size: var(--headline-size); font-weight: 700; line-height: var(--headline-lh);
  letter-spacing: -.03em; text-wrap: balance;
}
/* The name is the bar's, not this page's — it says it at the top of every
   view — so the facts under the picture are what this block is, and they are
   set at the size the Lineup sets an act's name in. One size for the two
   things on the page that name something, and the page is shorter for it. */
.fest .meta { margin: 12px 0 0; padding: 0; list-style: none; display: grid; gap: 9px; }
.fest .meta li { display: flex; align-items: center; gap: 10px; font-size: 13px; line-height: 1.35; }
.fest .meta svg {
  flex: none; inline-size: 18px; block-size: 18px;
  fill: none; stroke: var(--on-var); stroke-width: 1.7;
  stroke-linecap: round; stroke-linejoin: round;
}
.fest .meta em { font-style: normal; color: var(--on-var); }
/* the address is the one meta row that does something */
/* 12px, not the design's 10: the row that is a button carries the same
   glyph as the two that are not, and its label belongs in their column. */
.fest .meta button {
  display: inline-flex; align-items: center; gap: 12px;
  margin: -6px -10px; padding: 6px 10px; border: 0; border-radius: 10px;
  background: none; color: inherit; font: inherit; text-align: start; cursor: pointer;
  transition: background var(--effects);
}
.fest .meta button:hover { background: var(--state8); }
.fest .meta button svg { stroke: var(--primary); }

/* ---------- genre chips ---------- */
.fest .genres {
  display: flex; flex-wrap: nowrap; gap: 8px; margin: 12px -12px 0; padding: 0 12px;
  overflow-x: auto; scrollbar-width: none; list-style: none;
}
.fest .genres::-webkit-scrollbar { block-size: 0; }
.fest .genres li {
  flex: none; display: inline-flex; align-items: center; block-size: 32px; padding: 0 14px;
  border: 1px solid var(--outline); border-radius: 8px;
  font-size: 12px; font-weight: 500; letter-spacing: .01em;
  color: var(--on-var); white-space: nowrap;
}
/* What the festival is stands with what it plays, in the festival's own
   colour — the one chip in the row that is filled, so it reads as the
   heading of the list rather than another entry in it. */
.fest .genres li.strand {
  border-color: transparent; background: var(--sec); color: var(--on-sec); font-weight: 600;
  letter-spacing: .02em;
}

/* ---------- actions ---------- */
/* M3's button group: three that share the row equally, and the one that is
   on takes room from the other two — the same idea as a selected segment
   growing, on the emphasised spring so the give and take reads as one
   movement. Each says what it does; an icon alone made the two links a
   guess. */
.fest .actions { display: flex; gap: 8px; margin-block-start: 12px; }
.fest .act, .fest .plan {
  flex: 1 1 0; min-inline-size: 0;
  display: inline-flex; align-items: center; justify-content: center; gap: 6px;
  block-size: 48px; padding: 0 8px; border: 0; border-radius: 16px;
  /* M3's tonal step: the card is the container and a control on it is the
     surface above — the same colour on both read as one shape. */
  background: var(--wash,#FFFFFF); color: var(--on);
  /* Label Medium: at 13 the longest of the three labels, "Add to plan",
     ran 72px into the 66 a third of the row leaves it and ellipsised. */
  font-size: 12px; font-weight: 600; font-family: inherit; letter-spacing: .01em;
  cursor: pointer; text-decoration: none;
  transition: background var(--effects), color var(--effects),
    border-radius var(--spring), flex-grow var(--spring);
}
.fest .act span, .fest .plan span {
  min-inline-size: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.fest .act svg { flex: none; inline-size: 18px; block-size: 18px; }
.fest .act:hover { background: var(--hover,#EAE8DF); border-radius: 28px; }
.fest .act:focus-visible { outline: 2px solid var(--primary); outline-offset: 2px; }

/* filled tonal, shape-morphing on selection — the app's own plan button */
.fest .plan[aria-pressed="true"] {
  flex-grow: 1.5; border-radius: 24px;
  background: var(--heart-cont,#FBE0C0); color: var(--on-heart-cont,#2B1700);
}
.fest .plan:focus-visible { outline: 2px solid var(--primary); outline-offset: 2px; }
.fest .plan svg { flex: none; inline-size: 18px; block-size: 18px; overflow: visible; color: var(--heart,#8F4C0A); }
.fest .plan[aria-pressed="true"] svg { color: currentColor; }

/* ---------- the lineup, a row you scroll ----------
   The row bleeds past the page's margin so a cut item shows at the edge;
   that is the only affordance a scrolling row needs. Snap points align to
   the margin rather than to the screen edge. */
/* The page has one content column: a card sits on the 12 every card in the
   app sits on, and what is written — inside a card or beside it — starts
   12 further in. So the Lineup's heading and the first face in its row line
   up with About's heading and its copy. */
.fest .sec-head { display: flex; align-items: baseline; gap: 12px; margin: 18px 0 10px;
  padding-inline: 8px; }
.fest .sec-head h2 { margin: 0; font-size: var(--title-size); font-weight: 650; letter-spacing: -.01em; }
.fest .sec-head button {
  /* the -12px is the rule the About card's Read more already follows: a
     text button's label sits on the margin and its padding hangs off it */
  margin-inline: auto -12px; padding: 8px 12px; min-block-size: 40px;
  border: 0; border-radius: 20px; background: none; color: var(--primary);
  font-size: 13.5px; font-weight: 650; font-family: inherit; cursor: pointer;
  transition: background var(--effects);
}
.fest .sec-head button:hover { background: var(--state8); }
.fest .sec-head button:focus-visible { outline: 2px solid var(--primary); outline-offset: 2px; }

.fest .lineup {
  display: flex; gap: 14px; margin: 0 -16px; padding: 2px 16px 6px 24px;
  overflow-x: auto; overscroll-behavior-x: contain;
  scroll-snap-type: x proximity; scroll-padding-inline-start: 24px;
  scrollbar-width: none; list-style: none;
}
.fest .lineup::-webkit-scrollbar { block-size: 0; }
.fest .lineup li { flex: none; inline-size: 84px; scroll-snap-align: start; }
.fest .who {
  display: grid; justify-items: center; gap: 8px; inline-size: 100%;
  padding: 0; border: 0; background: none; color: inherit;
  font-family: inherit; cursor: pointer; -webkit-tap-highlight-color: transparent;
}
.fest .who:focus-visible { outline: 2px solid var(--primary); outline-offset: 4px; border-radius: 12px; }
.fest .avatar {
  position: relative; inline-size: 72px; block-size: 72px; border-radius: 50%;
  display: grid; place-items: center; overflow: visible;
  transition: transform var(--spring);
}
.fest .who:active .avatar { transform: scale(.93); }
/* clipped rather than hidden: the tick has to stand outside the circle */
.fest .who__art { inline-size: 100%; block-size: 100%; clip-path: circle(50%); }
.fest .avatar--on { box-shadow: 0 0 0 3px var(--wash,#FFFFFF), 0 0 0 5px var(--accent); }
.fest .avatar b {
  position: absolute; inset-block-end: -1px; inset-inline-end: -1px;
  display: grid; place-items: center; inline-size: 22px; block-size: 22px;
  border-radius: 50%; border: 2px solid var(--wash,#FFFFFF);
  background: var(--accent); color: var(--wash,#FFFFFF);
}
.fest .avatar b svg { inline-size: 13px; block-size: 13px; fill: currentColor; }
.fest .who__name {
  font-size: 13px; font-weight: 600; line-height: 1.25; text-align: center;
  min-block-size: 2.5em;               /* two lines kept, so the times line up */
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
}
/* The time is what a lineup is scanned for, so it is set in tabular
   figures and every row of them lines up. */
.fest .who__role {
  margin-block-start: -2px; inline-size: 100%;
  font-size: 12px; font-weight: 550; line-height: 1.3; color: var(--on-var,#494E42);
  font-variant-numeric: tabular-nums; text-align: center; white-space: nowrap;
}

/* ---------- about ---------- */
.fest .about {
  margin-block-start: 14px; margin-inline: -4px; padding: 14px 12px 12px;
  border-radius: 24px; background: var(--card);
}
.fest .about h2 { margin: 0 0 10px; font-size: var(--title-size); font-weight: 650; line-height: 1.35; letter-spacing: -.01em; }
.fest .about__clip { overflow: hidden; max-block-size: calc(3 * 1.45em); transition: max-block-size 340ms var(--ease); }
/* The size the forecast writes its own line in, so the two cards under
   the festival read as one page rather than two. */
.fest .about__text { margin: 0; font-size: 13px; line-height: 1.45; color: var(--on-var); text-wrap: pretty; }
.fest .about__more {
  display: inline-flex; align-items: center; gap: 6px;
  margin: 8px 0 0 -12px; padding: 10px 14px 10px 12px; min-block-size: 44px;
  border: 0; border-radius: 22px; background: none; color: var(--primary);
  font: 700 14px/1 inherit; cursor: pointer; transition: background var(--effects);
}
.fest .about__more:hover { background: var(--state8); }
.fest .about__more:focus-visible { outline: 2px solid var(--primary); outline-offset: 2px; }
.fest .about__more svg { inline-size: 18px; block-size: 18px; fill: currentColor; transition: transform var(--spring); }
.fest .about.is-open .about__more svg { transform: rotate(180deg); }
.fest .about__facts {
  display: flex; flex-wrap: wrap; gap: 8px 18px; margin: 12px 0 0; padding: 10px 0 0;
  border-block-start: 1px solid var(--outline); list-style: none;
}
.fest .about__facts li { display: flex; align-items: center; gap: 8px; font-size: 13px; color: var(--on-var); }
.fest .about__facts svg { inline-size: 16px; block-size: 16px; fill: none; stroke: currentColor; stroke-width: 1.7; stroke-linecap: round; }"""

NO_ZOOM_CSS = """/* No double-tap zoom, and no rubber-banding past the page. */
html{touch-action:manipulation;-webkit-text-size-adjust:100%;overscroll-behavior:none}
/* The bounce again, for the scrollers inside the page. The timetable, the
   list, the map pane and every sheet declare overscroll-behavior:contain,
   which keeps a scroll from chaining out into the page but leaves each of
   them free to rubber-band at its own ends — the page reads as loose when
   reaching the end of the grid makes it wobble. They are all reached by the
   one attribute they have in common, since each states it inline and an
   inline declaration is the last word without this. */
body{overscroll-behavior:none}
[style*="overscroll-behavior"]{overscroll-behavior:none!important}"""

NO_ZOOM_JS = """(function () {
  if (!window.matchMedia || !matchMedia('(pointer: coarse)').matches) return;
  /* Leaflet does its own two-finger zoom, on the one element that should
     have one. */
  var onMap = function (e) {
    var t = e.target;
    return !!(t && t.closest && t.closest('.leaflet-container'));
  };
  var stop = function (e) {
    if (onMap(e)) return;
    if (e.cancelable) e.preventDefault();
  };
  /* Safari's own pinch events, which is what it listens to instead of the
     viewport tag. */
  document.addEventListener('gesturestart', stop, { passive: false });
  document.addEventListener('gesturechange', stop, { passive: false });
  document.addEventListener('gestureend', stop, { passive: false });
  /* Everywhere else: a touch that has become two fingers is a pinch. */
  document.addEventListener('touchmove', function (e) {
    if (e.touches && e.touches.length > 1) stop(e);
  }, { passive: false });
})();"""


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
<!-- frame-src: the act card's player. Nothing is asked of either host until a
     reader presses play on an act — the card holds a still picture and a
     button until then, and the iframe is created by that press. -->
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'self' 'unsafe-inline' 'unsafe-eval'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https://*.basemaps.cartocdn.com https://server.arcgisonline.com; font-src data:; connect-src 'self' https://api.open-meteo.com; frame-src https://open.spotify.com https://www.youtube-nocookie.com; manifest-src 'self'; worker-src 'self'; base-uri 'none'; form-action 'none'">
<meta name="referrer" content="strict-origin-when-cross-origin">
<!-- A planner is opened in a field, one-handed, and pinched by accident more
     often than on purpose: the timetable is a grid you drag in both
     directions, and a two-finger drag on it zoomed the page instead. So the
     page holds its scale, the way an app does. Browser zoom on a pointer
     device is untouched, and so is the stage map, which does its own
     pinching. -->
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no, viewport-fit=cover">
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
{stage_palette(len(fest.stages), _lch(fest.f['accent'])[2])[1]}
{CARD_CSS}
{theme_css(fest.f['accent'], art.other_css(), art.js, script, template)}
{FEST_CSS}
{SHEET_CSS}
{NO_ZOOM_CSS}
</style>
<script>/* the page holds its scale on a touch screen */
{NO_ZOOM_JS}
</script>
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
