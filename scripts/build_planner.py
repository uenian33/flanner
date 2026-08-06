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

    return patch_nav(patch_card(patch_sheet(patch_cards(patch_grid(patch_viewport(
        patch_stage_colours(patch_weather(patch_map(src, fest), fest), fest)))))))


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
    const shut = () => { clearTimeout(this.closeT); this.setState({ sheet: null }); };
    if (!el) { shut(); return; }
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

  /* ---- throw to dismiss ---- */
  sheetDragOn() {
    const el = this.sheetEl;
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
        "          + (playSrc === 'youtube' ? 'yt' : 'sp'),\n"
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
        "    if (!h.length) { window.location.href = '../index.html'; return; }\n"
        "    const prev = h[h.length - 1];",
        "back leaves for the list")

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
        "    }\n",
        "sheet open animation")

    # ---- the sheet is the page on a phone ----
    src = sub_once(
        src,
        r"      \}, tight \? \{\n"
        r"        display: 'flex', flexDirection: 'column', overflow: 'hidden',\n",
        "      }, sheet ? sheet.vars : null, mob ? {\n"
        "        /* A phone opens it as a page of its own: the whole screen,\n"
        "           squared off, the hero at its own height and the body taking\n"
        "           the rest. The card stays a grid — its columns are decided by\n"
        "           its own container queries and nothing here may take that. */\n"
        "        gridTemplateRows: 'auto minmax(0, 1fr)', overflow: 'hidden',\n"
        "        width: '100%', height: '100%', maxHeight: 'none',\n"
        "        borderRadius: '0px', boxShadow: 'none',\n"
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
        "      }, mob ? { width: '100%', height: '100%', display: 'grid',\n"
        "        gridTemplateRows: 'minmax(0, 1fr)' } : null),\n"
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
        "        placeContent: mob ? 'stretch' : 'safe center',",
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

    # The bar keeps its compact height for the whole of the programme. It
    # already compacted itself the moment you scrolled the grid and came back
    # to full height the moment you scrolled the other way, which on a page
    # you read by dragging in two directions is a bar that changes size under
    # your thumb. Reading the timetable is the one thing this page is for, so
    # there it is small; Info and Map, which you land on rather than scroll
    # through, keep the labels.
    src = sub_once(
        src,
        r"    const mini = mob && S\.barMini;",
        "    const progNow = (S.view || this.props.startView || 'timetable');\n"
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
                   "      : (view === 'list' ? 'timetable' : view);",
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


def stage_palette(n: int) -> tuple[list[dict], str]:
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
        h = (124 + i * 137.507) % 360
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
        <div class="ac__notch"><i></i><i></i><span class="ac__chip">{{ sheet.chipLabel }}</span></div>
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
  text-transform: uppercase; color: var(--hero-tint);
}
.ac__title {
  margin: 0; padding-inline-end: 4px; color: var(--on-hero);
  font-size: clamp(22px, 5.4cqi, 30px); font-weight: 700;
  line-height: 1.08; letter-spacing: -.03em; text-wrap: balance;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
}
/* Only the last row needs to clear the notch — indenting the headline
   too would cost it a line of width for nothing. */
.ac__where {
  display: flex; align-items: center; gap: 8px; margin: 1px 0 0;
  padding-inline-end: clamp(96px, 29%, 150px);
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
  .ac__where { padding-inline-end: 92px; font-size: 13px; }
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
  margin: 3px 0 0; max-inline-size: calc(100% - 96px);
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
{stage_palette(len(fest.stages))[1]}
{CARD_CSS}
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
