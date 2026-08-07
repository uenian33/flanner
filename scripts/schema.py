#!/usr/bin/env python3
"""The contract for data/festivals.json, and the one place that enforces it.

Two rules keep the data honest:

  Derive whatever can be derived.  A month, a display date range and a day
  count are all functions of `start` and `end`, so they are computed here
  rather than typed by hand — three fields that could drift out of step with
  each other become one that cannot.

  Fail the build, not the page.  Anything a page would have to guess about at
  runtime (a missing name, a category that is not a category, an end before a
  start) stops the build with every problem listed at once, so a bad edit is
  caught here instead of showing up as an empty card in a browser.

Import it from a builder:

    import schema
    cfg = schema.load()          # validated, normalised, categories attached
"""
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]*$")
HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
URL = re.compile(r"^https://")

MONTHS = ["January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]

# field -> type, for the flat part of a festival record. Anything not listed
# here is either derived (see normalise) or structured (stats, tags, stars).
REQUIRED = {
    "id": str, "name": str, "year": str, "start": str, "end": str,
    "city": str, "type": str, "accent": str, "ink": str,
    "description": str, "official": str, "free": bool,
    "highlight": bool, "category": str,
}
# A festival the site lists but has not built a planner for carries none of
# these: no planner directory, no poster, no wordmark. It shows as a card with
# the category's own artwork and a link to the festival's own site.
OPTIONAL = {"planner": str, "logo": str, "promo": str, "linkLabel": str,
            "previewNote": str}
DERIVED = ("month", "dates", "stats.days")


class DataError(SystemExit):
    """Raised with every problem found, not just the first."""


def load_categories() -> dict:
    cats = json.loads((DATA / "categories.json").read_text())
    seen = set()
    for c in cats["categories"]:
        for key in ("id", "label", "color", "ink"):
            if key not in c:
                raise DataError(f"categories.json: {c.get('id', '?')} has no {key}")
        if not SLUG.match(c["id"]):
            raise DataError(f"categories.json: {c['id']!r} is not a slug")
        if not HEX.match(c["color"]) or not HEX.match(c["ink"]):
            raise DataError(f"categories.json: {c['id']} has a malformed colour")
        if c["id"] in seen:
            raise DataError(f"categories.json: duplicate id {c['id']}")
        seen.add(c["id"])
    if cats["fallback"] not in seen:
        raise DataError(f"categories.json: fallback {cats['fallback']!r} is not a category")
    return cats


def _day(iso: str) -> date:
    y, m, d = (int(p) for p in iso.split("-"))
    return date(y, m, d)


def _range_label(start: date, end: date) -> str:
    """'14–16 August 2026', '30 July – 2 August 2026', '1 August 2026'."""
    if start == end:
        return f"{start.day} {MONTHS[start.month - 1]} {start.year}"
    if (start.year, start.month) == (end.year, end.month):
        return f"{start.day}–{end.day} {MONTHS[start.month - 1]} {start.year}"
    if start.year == end.year:
        return (f"{start.day} {MONTHS[start.month - 1]} – "
                f"{end.day} {MONTHS[end.month - 1]} {start.year}")
    return (f"{start.day} {MONTHS[start.month - 1]} {start.year} – "
            f"{end.day} {MONTHS[end.month - 1]} {end.year}")


def normalise(f: dict, cats: dict, problems: list[str]) -> dict:
    """Fill in the derived fields and report anything that cannot be fixed."""
    where = f.get("id", "<no id>")

    for key, kind in REQUIRED.items():
        if key not in f:
            problems.append(f"{where}: missing {key}")
        elif not isinstance(f[key], kind):
            problems.append(f"{where}: {key} should be {kind.__name__}, "
                            f"got {type(f[key]).__name__}")
    for key, kind in OPTIONAL.items():
        if key in f and f[key] is not None and not isinstance(f[key], kind):
            problems.append(f"{where}: {key} should be {kind.__name__} or absent, "
                            f"got {type(f[key]).__name__}")

    if not SLUG.match(str(f.get("id", ""))):
        problems.append(f"{where}: id must be a lowercase slug")
    for key in ("start", "end"):
        if not ISO.match(str(f.get(key, ""))):
            problems.append(f"{where}: {key} must be YYYY-MM-DD")
    for key in ("accent", "ink"):
        if not HEX.match(str(f.get(key, ""))):
            problems.append(f"{where}: {key} must be #rrggbb")
    for key in ("official", "tickets"):
        if f.get(key) and not URL.match(str(f[key])):
            problems.append(f"{where}: {key} must be an https URL")
    if not f.get("free") and not f.get("tickets"):
        problems.append(f"{where}: a ticketed festival needs a tickets URL")
    if f.get("planner") and not str(f["planner"]).endswith("/"):
        problems.append(f"{where}: planner should be a directory path ending in /")
    # A planner page is built from a poster and a wordmark where the festival
    # has published them; where it has not, the planner draws the category's
    # own artwork, exactly as its card on the list does.
    if f.get("planner") and f.get("promo") and not f.get("logo"):
        problems.append(f"{where}: a festival with a poster needs its wordmark too")

    ids = {c["id"] for c in cats["categories"]}
    # Accepts the label people actually type ("Music") as well as the id.
    given = str(f.get("category", "")).strip().lower()
    if given not in ids:
        problems.append(f"{where}: category {f.get('category')!r} is not one of "
                        + ", ".join(sorted(ids)))
    else:
        f["category"] = given

    if not isinstance(f.get("tags"), list) or not f["tags"]:
        problems.append(f"{where}: tags must be a non-empty list")
    # The line-up and the counts belong to a festival we have the programme
    # for. A listed festival without a planner states its own facts instead.
    # Headliners are the organiser's own billing, and a festival that has not
    # published a running order has not billed anyone yet.
    if f.get("stars") is not None and (not isinstance(f["stars"], list) or not f["stars"]):
        problems.append(f"{where}: stars must be a non-empty list or absent")
    stats = f.setdefault("stats", {})
    if not isinstance(stats, dict):
        problems.append(f"{where}: stats must be an object")
        stats = f["stats"] = {}
    for key in ("acts", "stages"):
        if key in stats and (not isinstance(stats[key], int) or stats[key] < 1):
            problems.append(f"{where}: stats.{key} must be a positive integer")
    # Counted from the programme where there is one. A planner that only knows
    # where the festival is counts nothing, and says so rather than saying 0.
    if f.get("planner") and stats and not (stats.get("acts") and stats.get("stages")):
        problems.append(f"{where}: stats needs both acts and stages, or neither")

    facts = f.get("facts")
    if facts is not None and (not isinstance(facts, dict)
                              or any(not isinstance(v, str) for v in facts.values())
                              or set(facts) - {"time", "place", "price"}):
        problems.append(f"{where}: facts must be an object of time/place/price strings")

    if problems:
        return f

    start, end = _day(f["start"]), _day(f["end"])
    if end < start:
        problems.append(f"{where}: end {f['end']} is before start {f['start']}")
        return f

    # Derived — always recomputed, so hand-edited copies cannot go stale.
    f["month"] = f["start"][:7]
    f["dates"] = _range_label(start, end)
    f["stats"]["days"] = (end - start).days + 1
    return f


_cache: dict | None = None


def load() -> dict:
    """The whole site config: validated festivals, in date order, + categories.

    Cached: a build reads it from several places and the file cannot change
    underneath a single run.
    """
    global _cache
    if _cache is not None:
        return _cache
    cfg = json.loads((DATA / "festivals.json").read_text())
    cats = load_categories()

    problems: list[str] = []
    for f in cfg["festivals"]:
        normalise(f, cats, problems)

    ids = [f.get("id") for f in cfg["festivals"]]
    for dupe in {i for i in ids if ids.count(i) > 1}:
        problems.append(f"duplicate festival id {dupe!r}")

    if problems:
        raise DataError("festivals.json:\n  " + "\n  ".join(problems))

    cfg["festivals"].sort(key=lambda f: (f["start"], f["name"]))
    cfg["categories"] = cats["categories"]
    cfg["categoryFallback"] = cats["fallback"]
    _cache = cfg
    return cfg


def festival(fid: str) -> dict:
    """One festival by id, or a build failure naming the ones that exist."""
    for f in load()["festivals"]:
        if f["id"] == fid:
            return f
    known = ", ".join(f["id"] for f in load()["festivals"])
    raise DataError(f"no festival with id {fid!r} — have: {known}")


def category_css(cfg: dict) -> str:
    """One custom-property pair per category, plus the selector that picks it.

    A card carries data-cat, so the colour travels with the markup and nothing
    in the stylesheet has to know which festival is which.
    """
    lines = [":root{"]
    for c in cfg["categories"]:
        lines.append(f"  --cat-{c['id']}:{c['color']}; --cat-{c['id']}-ink:{c['ink']};")
    lines.append("}")
    for c in cfg["categories"]:
        lines.append(f"[data-cat=\"{c['id']}\"]{{--cat:var(--cat-{c['id']});"
                     f"--cat-ink:var(--cat-{c['id']}-ink)}}")
    return "\n".join(lines)


# The five variables the drawn cover reads, as (chroma, tone) in each theme.
#
# The tones are the ones the ramp already resolves to as a grey — the page
# mixes its own ink into its own paper at 8, 16, 24 and 70 per cent, which
# lands on these — so nothing here moves a lightness and no contrast pair
# changes. What is added is chroma, and it is the planner's own artwork
# chroma, role for role: the two drawings are the same drawing, and this is
# what makes a festival's card and that festival's page read as one thing.
ART_TONES = (
    #  variable    light (chroma, tone)   dark (chroma, tone)
    ("art-bg",     (12, 93.7),            (14, 14.2)),
    ("art-1",      (28, 87.4),            (26, 21.7)),
    ("art-3",      (39, 80.6),            (25, 29.3)),
    ("art-2",      (36, 40.3),            (30, 67.4)),
    ("art-ink",    (40, 30.2),            (30, 79.9)),
)


def _hue_chroma(hex_colour: str) -> tuple[float, float]:
    import math
    import m3color
    _L, a, b = m3color.hex_to_lab(hex_colour)
    return math.degrees(math.atan2(b, a)) % 360, math.hypot(a, b)


# The highlight's own tokens, and the Material role each one is. The section
# indirects everything through this handful, so restating them under a themed
# selector re-themes the eyebrow, the arrows, the dots, the card it stands on
# and the two buttons in it — without a single component knowing.
HL_ROLES = (
    ("accent",         "primary"),
    ("surface",        "surface-container-low"),
    ("on-surface",     "on-surface"),
    ("on-surface-var", "on-surface-variant"),
    ("outline-var",    "outline-variant"),
    ("chip",           "secondary-container"),
    ("on-chip",        "on-secondary-container"),
    ("sel-bg",         "primary"),
    ("sel-fg",         "on-primary"),
)


def _sources(cfg: dict) -> list[tuple[str, str]]:
    """What each card is drawn in, as (attribute selector, source colour).

    A festival with a planner of ours takes the colour that planner is themed
    from — the same `accent` it turns its whole page to — so the card here and
    the page it opens are one colour. A festival we have not built a planner
    for has no colour of its own to borrow, so it takes its category's, the one
    the chip beside it already wears. Categories first: a festival's own rule
    is written after the category's and wins on order, not on weight.
    """
    return ([(f'[data-cat="{c["id"]}"]', c["color"]) for c in cfg["categories"]]
            + [(f'[data-id="{f["id"]}"]', f["accent"]) for f in cfg["festivals"]
               if f.get("planner") and f.get("accent")])


def _themed(cfg: dict, rule) -> str:
    """One rule per source, in the light theme and then twice in the dark.

    Dark is stated under both the attribute the settings menu writes and the
    media query, which is the convention the shared tokens already use — and
    both carry more weight than the light rules, so the order holds.
    """
    out = [rule(sel, src, False, "") for sel, src in _sources(cfg)]
    out += [rule(sel, src, True, ":root[data-theme=dark] ") for sel, src in _sources(cfg)]
    out.append("@media(prefers-color-scheme:dark){")
    out += ["  " + rule(sel, src, True, ":root:not([data-theme=light]) ")
            for sel, src in _sources(cfg)]
    out.append("}")
    return "\n".join(out)


def artwork_css(cfg: dict) -> str:
    """The drawn cover, in the colour the festival is themed by.

    Only the hue travels. The ramp keeps the lightness it has as a grey, and
    it never claims more chroma than the source colour itself has, which is
    what leaves `others` — a grey by definition — the grey it is now.
    """
    import m3color

    def rule(sel: str, src: str, dark: bool, prefix: str) -> str:
        hue, chroma = _hue_chroma(src)
        vals = ";".join("--%s:%s" % (name, m3color.tone(hue, min(c, chroma), t))
                        for name, light, deep in ART_TONES
                        for c, t in [deep if dark else light])
        # And the star, once it is filled. Unstarred it stays the page's own
        # grey — a row of unstarred cards is a list, not a colour chart — so
        # only the filled pair is the festival's.
        s = m3color.scheme(src)[1 if dark else 0]
        vals += f";--sel-bg:{s['primary']};--sel-fg:{s['on-primary']}"
        return f"{prefix}{sel}{{{vals}}}"

    return ("/* The drawn cover's ramp, generated by schema.py. The hue is the\n"
            "   festival's own where it has a planner and its category's where it\n"
            "   does not; the tones are the ones the grey ramp already lands on. */\n"
            + _themed(cfg, rule))


def highlight_css(cfg: dict) -> str:
    """The highlight, in the colour of whichever festival it is showing.

    The rest of the page is monochrome on purpose — a list of planners cannot
    be drawn in one festival's colour. The highlight is not a list: it is one
    festival at a time, saying which, so it is drawn in that festival's own
    scheme. Generated the way a planner's is, from the same source colour
    through `m3color`, so the two are the same nine roles at the same tones.

    Two selectors per source: the section, which carries the eyebrow, the
    arrows and the dots, and the card itself — the card, because during a
    slide two of them are on screen and each should still be its own.
    """
    import m3color

    def rule(sel: str, src: str, dark: bool, prefix: str) -> str:
        scheme = m3color.scheme(src)[1 if dark else 0]
        vals = ";".join("--%s:%s" % (name, scheme[role]) for name, role in HL_ROLES)
        return (f"{prefix}#hero{sel},{prefix}.banner-card{sel}{{{vals}}}")

    return ("/* The highlight's scheme, generated by schema.py from the same source\n"
            "   colour as the cover above it — nine Material roles at Material's own\n"
            "   tones, so the section is the festival's page in miniature. */\n"
            + _themed(cfg, rule))


def calendar_css(cfg: dict) -> str:
    """A festival's bar on the calendar, in that festival's own colour.

    The bar was the one place on the grid where a festival is named and drawn
    at once, and every one of them was the same grey — so the month said what
    was on and not what any of it was. Two pairs, the two states a bar has:
    the tonal container it rests in, and the filled primary it takes once the
    festival is in your plan. Both off the same scheme as the card above.
    """
    import m3color

    def rule(sel: str, src: str, dark: bool, prefix: str) -> str:
        s = m3color.scheme(src)[1 if dark else 0]
        return (f"{prefix}.event{sel}{{"
                f"--cat-bar:{s['secondary-container']};"
                f"--on-cat-bar:{s['on-secondary-container']};"
                f"--plan-bar:{s['primary']};"
                f"--on-plan-bar:{s['on-primary']}}}")

    return ("/* The calendar's bars, generated by schema.py from the same source\n"
            "   colour as that festival's card. Resting and in-your-plan. */\n"
            + _themed(cfg, rule))


if __name__ == "__main__":
    cfg = load()
    print(f"{len(cfg['festivals'])} festivals, "
          f"{len(cfg['categories'])} categories — data is valid")
    for f in cfg["festivals"]:
        print(f"  {f['id']:8} {f['category']:8} {f['dates']} "
              f"({f['stats']['days']}d)")
