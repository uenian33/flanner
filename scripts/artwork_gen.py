#!/usr/bin/env python3
"""An artwork per act, drawn from the act's own name, baked at build time.

Every act used to wear the same picture: one symbol in the sprite, the same
bars in the same places, recoloured per stage. A rail of twelve of them read as
twelve copies of one thing, which is exactly what a lineup is not.

`scripts/vendor/artwork-generator.js` turns a name into a variant of that same
picture — the bars' silhouette is the first letter's own ink-density profile,
and every other parameter is drawn from a hash of the whole name, so the same
name always gives the same artwork and no name can give an off-brand one. It is
the artist's own picture in the sense that a fingerprint is: derived from them,
and theirs alone.

WHY IT RUNS HERE AND NOT IN THE BROWSER

Because it need only run once. The alternative is every reader's phone
rasterising a glyph and running a PRNG for a hundred and fifty acts before the
first paint, to arrive at the same answer every time. Baked, the page has the
finished drawings and does no work at all.

It is deterministic because the profiles are baked too: the generator normally
measures each letter by rasterising it in a canvas with Inter loaded, which
makes the result depend on the machine. `BAKED_PROFILES` in the vendored copy
is that measurement taken once, in a browser, so this runs in Node with no
canvas and no webfont and every build produces the same bytes.

WHAT IS *NOT* BAKED IN

Colour. Every fill in the generated SVG is `var(--art-bg)`, `var(--art-1)` and
so on — the same five names the design's own artwork uses — and the planner
already sets those per stage on the element that carries the drawing. So one
drawing per act serves every theme and every stage it might move to, and the
rail stays in step with the stage colours without the artwork knowing anything
about them.
"""
from __future__ import annotations

import json
import pathlib
import re
import subprocess

ROOT = pathlib.Path(__file__).resolve().parent.parent
GEN = ROOT / "scripts" / "vendor" / "artwork-generator.js"

# The generator emits a whole document; what goes in the sprite is its
# contents. Everything between the opening tag and the close.
_INNER = re.compile(r"<svg[^>]*>(.*)</svg>\s*$", re.S)

_NODE = """
const A = require(%s);
const names = JSON.parse(require('fs').readFileSync(0, 'utf8'));
const out = {};
for (const n of names) out[n] = A.artFor(n, { category: 'music' }).svg;
process.stdout.write(JSON.stringify(out));
"""


def draw(names: list[str]) -> dict[str, str]:
    """name -> the artwork's inner markup, ready to go in a <symbol>."""
    names = sorted(set(names))
    if not names:
        return {}
    res = subprocess.run(
        ["node", "-e", _NODE % json.dumps(str(GEN))],
        input=json.dumps(names), capture_output=True, text=True, check=True)
    svgs = json.loads(res.stdout)
    out = {}
    for name, svg in svgs.items():
        m = _INNER.search(svg)
        if not m:
            raise SystemExit(f"artwork for {name!r} is not an <svg> document")
        # Whitespace between elements is 40% of what the generator prints and
        # none of it renders. A hundred and fifty of these travel in the page.
        inner = re.sub(r"\s*\n\s*", "", m.group(1)).strip()
        out[name] = inner
    return out


def sprite(art: dict[str, str], ids: dict[str, str]) -> str:
    """The symbols, in the order the page will reference them."""
    return "\n".join(
        '<symbol id="%s" viewBox="0 0 400 250">%s</symbol>' % (ids[name], art[name])
        for name in sorted(art) if name in ids)


if __name__ == "__main__":
    import sys
    got = draw(sys.argv[1:] or ["Vive Latino", "Turnstile"])
    for k, v in got.items():
        print(f"{k}: {len(v)} bytes")
