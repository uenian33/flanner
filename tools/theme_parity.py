#!/usr/bin/env python3
"""Prove the browser's colour engine is the build's colour engine.

`scripts/m3color.py` is the reference: it is what every page shipped so far was
themed with, and what the contrast audits in DESIGN.md were run against.
`scripts/_theme.js` is the same arithmetic in JavaScript, so a planner can take
an accent and theme itself.

Two implementations of the same maths drift silently — a rounding rule here, a
bisection step there — and the drift shows up as a colour nobody chose. So they
are checked against each other rather than trusted: every tone the design asks
for, at every festival hue, plus a wide sweep of the space around them. Any
disagreement at all is a failure; the reference wins.

    python3 tools/theme_parity.py
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import m3color                                             # noqa: E402
import build_planner as B                                  # noqa: E402
import schema                                              # noqa: E402


def sample() -> list[tuple[float, float, float]]:
    """What to compare: the tones the design actually asks for, and a sweep.

    The design's own asks are the ones that matter — they are the values that
    end up on a page. The sweep is there so a festival whose accent nobody has
    tried yet cannot be the first to find a disagreement.
    """
    out: list[tuple[float, float, float]] = []

    # every stage role, at every festival's hue and at the seed's
    hues = [B.SEED_HUE] + [B._lch(f["accent"])[2]
                           for f in schema.load()["festivals"] if f.get("accent")]
    for hue in hues:
        for i in range(12):
            h = (hue + i * 137.507) % 360
            for _k, lt, dk in B.ROLES:
                out.append((h, lt[0], lt[1]))
                out.append((h, dk[0], dk[1]))

    # a sweep of the space: 24 hues, the chroma range the scheme uses, and the
    # tones M3 names, including the ends where the gamut runs out
    for hi in range(24):
        h = hi * 15.0
        for c in (0, 4, 8, 12, 16, 24, 36, 48, 64, 84, 120):
            for t in m3color.TONES:
                out.append((float(h), float(c), float(t)))
    return out


JS_HARNESS = r"""
const fs = require('fs');
global.window = {};
new Function(fs.readFileSync(process.argv[2], 'utf8'))();
const T = global.window.FlannerTheme;
const job = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
const out = {
  tones: job.cases.map(c => T.tone(c[0], c[1], c[2])),
  schemes: job.schemes.map(s => T.schemeCss(job.recipe, s.accent, s.stages)),
};
process.stdout.write(JSON.stringify(out));
"""


def decls_of(css: str) -> dict:
    """Every `--name:value` in a stylesheet, keyed by block then name.

    Compared this way rather than as text: the two implementations are held to
    the same answers, not to the same whitespace.
    """
    import re
    out: dict = {}
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    for sel, body in re.findall(r"([^{}]+)\{([^}]*)\}", css):
        d = out.setdefault(" ".join(sel.split()), {})
        for name, val in re.findall(r"(--[\w-]+)\s*:\s*([^;]+)", body):
            d[name] = val.strip()
    return out


def main() -> int:
    cases = sample()
    recipe = B.theme_recipe(B.CARD_CSS, B.SHEET_CSS, B.FEST_CSS)
    fests = [(f["id"], f["accent"]) for f in schema.load()["festivals"] if f.get("accent")]
    # Ten stages is what both planners have; a festival with more is the case
    # the golden angle exists for, so one is checked well past it.
    schemes = [{"accent": a, "stages": n} for _i, a in fests for n in (10, 17)]

    tmp = ROOT / "tools" / "_parity_cases.json"
    harness = ROOT / "tools" / "_parity.js"
    tmp.write_text(json.dumps({"cases": cases, "recipe": recipe, "schemes": schemes}))
    harness.write_text(JS_HARNESS)
    try:
        got = json.loads(subprocess.run(
            ["node", str(harness), str(ROOT / "scripts" / "_theme.js"), str(tmp)],
            capture_output=True, text=True, check=True).stdout)
    finally:
        tmp.unlink(missing_ok=True)
        harness.unlink(missing_ok=True)

    fail = 0

    want = [m3color.tone(*c) for c in cases]
    bad = [(c, w, g) for c, w, g in zip(cases, want, got["tones"]) if w != g]
    print(f"  {len(cases)} tones compared")
    if bad:
        fail = 1
        print(f"  {len(bad)} disagree — the reference is m3color.py")
        for c, w, g in bad[:12]:
            print(f"    hue {c[0]:7.2f} chroma {c[1]:5.1f} tone {c[2]:5.1f}   py {w}   js {g}")
    else:
        print("  every tone identical")

    for spec, js_css in zip(schemes, got["schemes"]):
        py = decls_of(B.render_recipe(recipe, spec["accent"], spec["stages"]))
        js = decls_of(js_css)
        names = {(s, n) for s, d in py.items() for n in d} | {(s, n) for s, d in js.items() for n in d}
        diff = [(s, n, py.get(s, {}).get(n), js.get(s, {}).get(n))
                for s, n in sorted(names) if py.get(s, {}).get(n) != js.get(s, {}).get(n)]
        total = sum(len(d) for d in py.values())
        label = f"{spec['accent']} · {spec['stages']} stages"
        if diff:
            fail = 1
            print(f"  {label}: {len(diff)} of {total} tokens disagree")
            for s, n, w, g in diff[:10]:
                print(f"    {s} {n}   py {w}   js {g}")
        else:
            print(f"  {label}: all {total} tokens identical")

    return fail


if __name__ == "__main__":
    raise SystemExit(main())
