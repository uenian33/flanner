#!/usr/bin/env python3
"""Rank quantized colours by how well they would theme an interface.

A port of material-color-utilities' `score/score.ts` (Google, Apache-2.0) —
the second half of Material You. Quantization says what is *in* a picture;
this says which of it a product could be built from, which is a different
question and the one that matters. A poster is mostly its background, and the
commonest colour in it is very often a near-grey, a near-black, or a wash
nobody would name — none of which can carry a button.

Three things decide it, and the constants are Material's own:

  * **How much of the picture is that hue** — not that colour. The proportion
    is smeared over a 30° window (±15), so a gradient running through a family
    is counted as the family rather than split between its steps. This is why
    the hand-rolled histogram this replaces needed a special rule about
    gradients: the reference algorithm already had one.
  * **How colourful it is**, against a target of chroma 48 — the chroma
    Material's own primary palette sits at. Above the target counts for three
    times what below it counts for, so a picture that has one genuinely
    saturated colour offers it up rather than its washed-out majority.
  * **Whether it repeats something already chosen.** The chosen colours have to
    span hues, so the loop starts by demanding 90° between them and relaxes
    one degree at a time to 15° until it has as many as were asked for.

Anything under chroma 5 is dropped as effectively grey, and any hue holding
1% or less of the picture is dropped as incidental. If nothing survives, the
reference returns Google Blue and so does this — a caller that gets it back
knows the picture had no colour worth having.
"""
from __future__ import annotations

import hct

TARGET_CHROMA = 48.0            # the chroma of Material's own primary palette
WEIGHT_PROPORTION = 0.7
WEIGHT_CHROMA_ABOVE = 0.3
WEIGHT_CHROMA_BELOW = 0.1
CUTOFF_CHROMA = 5.0
CUTOFF_EXCITED_PROPORTION = 0.01
FALLBACK = 0xff4285f4           # Google Blue, as in the reference


def score(colors_to_population: dict[int, int], desired: int = 4,
          fallback: int = FALLBACK, filter_unsuitable: bool = True) -> list[int]:
    """The ranked ARGB colours, most suitable first. Never returns empty."""
    colors_hct = []
    hue_population = [0.0] * 360
    population_sum = 0.0
    for argb, population in colors_to_population.items():
        h, c, t = hct.from_argb(argb)
        colors_hct.append((argb, h, c, t))
        hue_population[int(h) % 360] += population
        population_sum += population
    if population_sum <= 0:
        return [fallback]

    # A hue's share, plus its neighbours' — the 30° window.
    excited = [0.0] * 360
    for hue in range(360):
        proportion = hue_population[hue] / population_sum
        for i in range(hue - 14, hue + 16):
            excited[i % 360] += proportion

    scored = []
    for argb, h, c, _t in colors_hct:
        proportion = excited[round(h) % 360]
        if filter_unsuitable and (c < CUTOFF_CHROMA
                                  or proportion <= CUTOFF_EXCITED_PROPORTION):
            continue
        weight = WEIGHT_CHROMA_BELOW if c < TARGET_CHROMA else WEIGHT_CHROMA_ABOVE
        scored.append((proportion * 100.0 * WEIGHT_PROPORTION
                       + (c - TARGET_CHROMA) * weight, argb, h))
    # Highest score first; ties broken by hue so the order cannot depend on
    # dictionary iteration, which a build has to be able to repeat.
    scored.sort(key=lambda s: (-s[0], s[2]))

    for difference in range(90, 14, -1):
        chosen: list[tuple[int, float]] = []
        for _s, argb, h in scored:
            if not any(hct.difference_degrees(h, ch) < difference
                       for _a, ch in chosen):
                chosen.append((argb, h))
            if len(chosen) >= desired:
                break
        if len(chosen) >= desired:
            break
    return [a for a, _h in chosen] if chosen else [fallback]


def ranked(colors_to_population: dict[int, int], desired: int = 4) -> list[dict]:
    """`score`, but reporting why — for the command line and the record.

    The share is the hue-excited proportion the ranking actually used, not the
    colour's own count, because that is the number that decided it.
    """
    total = sum(colors_to_population.values()) or 1
    hue_population = [0.0] * 360
    for argb, population in colors_to_population.items():
        hue_population[int(hct.from_argb(argb)[0]) % 360] += population
    excited = [0.0] * 360
    for hue in range(360):
        p = hue_population[hue] / total
        for i in range(hue - 14, hue + 16):
            excited[i % 360] += p

    out = []
    for argb in score(colors_to_population, desired=desired):
        h, c, t = hct.from_argb(argb)
        out.append({"argb": argb,
                    "hex": "#%06x" % (argb & 0xffffff),
                    "hue": h, "chroma": c, "tone": t,
                    "share": excited[round(h) % 360],
                    "pixels": colors_to_population.get(argb, 0) / total})
    return out


if __name__ == "__main__":
    import sys
    import quantize
    for path in sys.argv[1:]:
        counts = quantize.counts_from_image(path)
        print(path)
        for i, r in enumerate(ranked(quantize.celebi(counts))):
            print(f"  {i + 1}. {r['hex']}  hue {r['hue']:6.1f}  "
                  f"chroma {r['chroma']:5.1f}  tone {r['tone']:5.1f}  "
                  f"{r['share'] * 100:5.1f}% of the picture's hue")
