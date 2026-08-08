#!/usr/bin/env python3
"""A festival's palette, read off the picture the festival publishes of itself.

Material's own pipeline does the reading: `quantize.celebi` clusters the poster
and `score.score` ranks the clusters for how well each could theme an
interface. That much is the reference implementation, and the colour system
sanctions exactly this use of it — "in lists and collections of repeated items
that benefit from differentiation, content-based color can help associate
related elements … each card is colored with a scheme sourced from its main
image", which is this list of festivals.

What this module adds is the one thing Material's ranking cannot know, because
it was written to theme a phone from one wallpaper: that there are nine
festivals here and they have to stay apart.

    Two rules, and both of them are answers to something measured.

    A poster's identity is its most *chromatic* colour, not its most abundant
    one. Material's Score ranks by how much of the picture a hue covers, gently
    corrected for chroma; run it over these nine and the top answer for Kallio
    is the orange of a sunset behind the crowd, while the festival's own lime
    green — the colour on its posters and its tickets — comes second at chroma
    76. Blockfest's brand pink comes third, at chroma 90. Ranking the
    candidates Material returns by chroma instead recovers the published brand
    colour for four of the six festivals that have a picture, matching the
    hand-curated record exactly.

    And the set has to stay legible as a set. Taking Material's first choice
    for each festival puts Kallio, Love & Anarchy and the Helsinki Festival
    within 8° of one another — three identical oranges — because festival
    photographs are crowds at golden hour. Score already refuses to return two
    similar hues *within* one image, starting at 90° apart and relaxing to 15°;
    this applies the same rule *across* festivals, which is the same problem one
    level up.

A tool, not a build step: it prints and a person decides. A festival that
publishes a new poster must not silently re-theme the site on the next build,
and where a festival states its own colour — Flow's #fff203 is read off Flow's
own stylesheet, and is in no part of its crowd photograph — no extraction beats
being told.

    python3 scripts/palette.py            # every festival, against the record
    python3 scripts/palette.py blockfest  # one, with all its candidates
"""
from __future__ import annotations

import io
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import hct
import quantize
import score as scoring
from assets import ROOT

# How far apart two festivals' hues have to be before a reader stops reading
# them as the same colour. Material's own within-image floor is 15°; across a
# list, where the cards are not side by side and memory is doing the comparing,
# it takes more.
MIN_SEPARATION = 30.0
# Below this there is not enough colour to theme from, whatever the picture is
# mostly made of. Material drops candidates under chroma 5 as effectively grey;
# a card drawn from one at 20 is a card drawn from a wash.
MIN_CHROMA = 20.0


def candidates(path: pathlib.Path, desired: int = 4) -> list[dict]:
    """Material's ranked colours for one picture, most suitable first."""
    return scoring.ranked(quantize.celebi(quantize.counts_from_image(path)),
                          desired=desired)


def choose(cands: list[dict]) -> dict | None:
    """The most chromatic candidate with enough colour to theme from.

    Independent of what any other festival took, and deliberately so. An
    earlier version allocated greedily down the record — first festival to
    want a hue kept it — and it was worse than the values it was proposing to
    replace: Flow claimed the chroma-89 red of a single balloon in its crowd
    photograph, which pushed the Helsinki Festival off its own red onto the
    teal that covers a fifth of its poster, and left two festivals with nothing
    at all. Whichever festival happens to be recorded first should not decide
    what the others are allowed to look like.

    So this proposes per picture, `clashes()` reports where two proposals
    collide, and a person resolves it. Which is the honest division of labour:
    the instrument measures, and it is not the instrument's business that Love
    & Anarchy's violet comes from the festival's own branding rather than from
    the still it publishes.
    """
    usable = [c for c in cands if c["chroma"] >= MIN_CHROMA]
    return max(usable, key=lambda c: c["chroma"]) if usable else None


def clashes(chosen: list[tuple[str, float]]) -> list[tuple[str, str, float]]:
    """Pairs of festivals whose proposed hues a reader would not tell apart."""
    out = []
    for i in range(len(chosen)):
        for j in range(i + 1, len(chosen)):
            d = hct.difference_degrees(chosen[i][1], chosen[j][1])
            if d < MIN_SEPARATION:
                out.append((chosen[i][0], chosen[j][0], d))
    return sorted(out, key=lambda t: t[2])


def tertiary_of(cands: list[dict], primary: dict) -> dict | None:
    """A second colour from the same picture, for the tertiary palette.

    Material sanctions building a scheme from more than one extracted colour —
    `CorePalette.fromColors({primary, secondary, tertiary, …})` — and states
    the relationship the result has to keep: "primary and tertiary colors are
    the most visually prominent in the scheme, with tertiary appearing
    complementary to primary by changing its hue. Secondary, neutral variant,
    and neutral colors match primary in hue but are progressively less
    chromatic in that order."

    So only tertiary is taken from the picture as well. The furthest hue with
    real chroma in it is the complementary one the picture actually contains,
    which beats primary + 60° — the fixed offset a generated scheme uses when
    it has nothing better, and which for a poster that is red and teal invents
    an orange that is nowhere in it.
    """
    others = [c for c in cands
              if c is not primary and c["chroma"] >= MIN_CHROMA]
    if not others:
        return None
    return max(others, key=lambda c: hct.difference_degrees(c["hue"], primary["hue"]))


def for_festival(f: dict) -> dict | None:
    """{primary, tertiary, candidates} for one record, or None with no picture."""
    if not f.get("promo"):
        return None
    path = ROOT / "assets" / "home" / f["promo"]
    if not path.exists():
        return None
    return {"id": f["id"], "candidates": candidates(path)}


def _load() -> list[dict]:
    cfg = json.load(io.open(ROOT / "data" / "festivals.json", encoding="utf-8"))
    return cfg["festivals"] if isinstance(cfg, dict) else cfg


def main() -> None:
    want = sys.argv[1] if len(sys.argv) > 1 else None
    rows = []
    for f in _load():
        got = for_festival(f)
        if not got:
            continue
        primary = choose(got["candidates"])
        rows.append((f, got["candidates"], primary,
                     tertiary_of(got["candidates"], primary) if primary else None))

    for f, cands, primary, tert in rows:
        if want and f["id"] != want:
            continue
        rh, rc, rt = hct.from_hex(f["accent"])
        print(f"\n{f['id']}  ({f['promo']})")
        print(f"  record    {f['accent']}   hue {rh:6.1f}  chroma {rc:5.1f}")
        if primary:
            agree = hct.difference_degrees(primary["hue"], rh)
            print(f"  picture   {primary['hex']}   hue {primary['hue']:6.1f}  "
                  f"chroma {primary['chroma']:5.1f}   "
                  f"{'agrees with the record' if agree < 15 else f'{agree:.0f}° from the record'}")
        else:
            print("  picture   nothing chromatic enough, or every hue in it is "
                  "another festival's")
        if tert:
            print(f"  tertiary  {tert['hex']}   hue {tert['hue']:6.1f}  "
                  f"chroma {tert['chroma']:5.1f}")
        if want:
            print("  all candidates, as Material ranks them:")
            for i, c in enumerate(cands):
                print(f"    {i + 1}. {c['hex']}  hue {c['hue']:6.1f}  "
                      f"chroma {c['chroma']:5.1f}  tone {c['tone']:5.1f}  "
                      f"{c['share'] * 100:5.1f}% of the picture's hue")

    if not want:
        chosen = [(f["id"], p["hue"]) for f, _c, p, _t in rows if p]
        bad = clashes(chosen)
        print(f"\nwould these proposals stay apart?  (floor {MIN_SEPARATION:.0f}°)")
        if not bad:
            print("  yes — every pair is far enough apart to read as its own colour")
        for a, b, d in bad:
            print(f"  {a} and {b} are {d:.0f}° apart — one of them has to keep "
                  f"the colour its festival publishes instead")

        # The same question of the values actually shipping, which is the one
        # that matters: the record is what a reader sees.
        rec = [(f["id"], hct.from_hex(f["accent"])[0]) for f, _c, _p, _t in rows]
        bad = clashes(rec)
        print("and the record as it stands?")
        if not bad:
            print("  every festival on the site is already its own colour")
        for a, b, d in bad:
            print(f"  {a} and {b} are {d:.0f}° apart")


if __name__ == "__main__":
    main()
