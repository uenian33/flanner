#!/usr/bin/env python3
"""Render the 1200x630 social cards.

These are the one part of the site that cannot be a data URI: Facebook,
X, Slack and iMessage all fetch og:image over HTTP, so it has to be a real
file at a real URL. Everything else about a page stays self-contained.
"""
from __future__ import annotations

import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "og"
TTF = ROOT / "assets" / "font-ttf"
W, H = 1200, 630


def font(name: str, size: int, weight: int | None = None) -> ImageFont.FreeTypeFont:
    f = ImageFont.truetype(str(TTF / name), size)
    if weight is not None:
        try:
            f.set_variation_by_axes([weight])
        except Exception:
            pass
    return f


def disc(size: int, a: str = "#b6fc46", b: str = "#fff203") -> Image.Image:
    """The Flanner mark: a gradient disc cut on the diagonal, halves pulled apart."""
    s = size * 4
    grad = Image.new("RGB", (s, s))
    px = grad.load()
    ca = tuple(int(a[i:i + 2], 16) for i in (1, 3, 5))
    cb = tuple(int(b[i:i + 2], 16) for i in (1, 3, 5))
    for y in range(s):
        for x in range(s):
            t = (x / s * 0.5) + ((s - y) / s * 0.5)
            px[x, y] = tuple(int(ca[i] + (cb[i] - ca[i]) * t) for i in range(3))

    mark = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    for dx, dy, half in ((0.055, -0.083, "up"), (-0.055, 0.083, "dn")):
        mask = Image.new("L", (s, s), 0)
        d = ImageDraw.Draw(mask)
        c = s / 2
        r = s * 0.46
        d.ellipse([c + dx * s - r, c + dy * s - r, c + dx * s + r, c + dy * s + r], fill=255)
        cut = Image.new("L", (s, s), 0)
        dc = ImageDraw.Draw(cut)
        # the diagonal seam, at -34 degrees through the centre
        poly = [(-s, c + s * 1.0118), (2 * s, c - s * 1.0118), (2 * s, -s), (-s, -s)]
        dc.polygon(poly, fill=255)
        if half == "dn":
            cut = Image.eval(cut, lambda v: 255 - v)
        mask = Image.composite(mask, Image.new("L", (s, s), 0), cut)
        mark.paste(grad, (0, 0), mask)
    return mark.resize((size, size), Image.LANCZOS)


def card(out: str, photo: Path | None, kicker: str, title: str, sub: str,
         accent: str, ink: str) -> None:
    im = Image.new("RGB", (W, H), "#0d0f12")

    if photo and photo.exists():
        p = Image.open(photo).convert("RGB")
        scale = max(W / p.width, H / p.height)
        p = p.resize((int(p.width * scale) + 1, int(p.height * scale) + 1), Image.LANCZOS)
        p = p.crop((0, 0, W, H))
        im.paste(p, (0, 0))
        # a legibility ramp, dark at the foot where the type sits
        veil = Image.new("L", (W, H))
        vd = ImageDraw.Draw(veil)
        for y in range(H):
            t = y / H
            vd.line([(0, y), (W, y)], fill=int(28 + 225 * (t ** 1.9)))
        im = Image.composite(Image.new("RGB", (W, H), "#07080a"), im, veil)

    d = ImageDraw.Draw(im)
    pad = 68

    mark = disc(96)
    im.paste(mark, (pad, pad), mark)
    d.text((pad + 118, pad + 20), "FLANNER", font=font("Teko.ttf", 60, 600), fill="#ffffff")

    if kicker:
        chip = font("Teko.ttf", 40, 500)
        tw = d.textlength(kicker, font=chip)
        box = [pad, H - pad - 236, pad + tw + 44, H - pad - 236 + 60]
        d.rounded_rectangle(box, radius=12, fill=accent)
        d.text((pad + 22, box[1] + 6), kicker, font=chip, fill=ink)

    d.text((pad, H - pad - 158), title, font=font("Teko.ttf", 104, 600), fill="#ffffff")
    d.text((pad, H - pad - 46), sub, font=font("Lato-Regular.ttf", 30), fill="#d3d7dd")

    OUT.mkdir(parents=True, exist_ok=True)
    im.save(OUT / out, "JPEG", quality=88, optimize=True)
    print(f"  assets/og/{out} · {(OUT / out).stat().st_size // 1024} KB")


def main() -> None:
    cfg = json.loads((ROOT / "data" / "festivals.json").read_text())
    by = {f["id"]: f for f in cfg["festivals"]}

    card("home.jpg", ROOT / "assets" / "home" / "flow-promo.jpg",
         "HELSINKI", "FESTIVAL PLANNER",
         "Plannable timetables · stage maps · your own route", "#fff203", "#000000")

    for fid, out in (("kbp", "kallio.jpg"), ("flow", "flow.jpg")):
        f = by[fid]
        card(out, ROOT / "assets" / "home" / f"{'kbp' if fid == 'kbp' else 'flow'}-promo.jpg",
             f["dates"].upper(), f["name"].upper(),
             f"{f['stats']['acts']} acts · {f['stats']['stages']} stages · {f['city']}",
             f["accent"], f["ink"])

    card("info.jpg", None, "", "FLANNER",
         "Unofficial festival planners for Helsinki", "#b6fc46", "#0a1400")


if __name__ == "__main__":
    print(ROOT)
    main()
