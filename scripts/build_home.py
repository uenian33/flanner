#!/usr/bin/env python3
"""Build the Festival Planner home page.

One card per festival that has a planner, grouped by month, with a highlight
rail on top. Everything is inlined so the page is a single file like the
planners it links to.
"""
import json, pathlib
from build import ROOT, data_uri

OUT = ROOT / "index.html"
CFG = ROOT / "data" / "festivals.json"
H = ROOT / "assets" / "home"

def main():
    cfg = json.loads(CFG.read_text())
    for f in cfg["festivals"]:
        f["promoSrc"] = data_uri(H / f["promo"])
        f["logoSrc"] = data_uri(ROOT / "assets" / f["logo"])
        f.pop("promo", None); f.pop("logo", None)

    html = (ROOT / "scripts" / "home.html").read_text()
    for tok, val in [
        ("__DATA__", json.dumps(cfg, ensure_ascii=False, separators=(",", ":"))),
        ("__FONTCSS__", (ROOT / "assets" / "font" / "festiplannr.css").read_text().strip()),
        ("__CONTACT__", cfg["site"]["contact"]),
    ]:
        html = html.replace(tok, val)
    left = [t for t in ("__DATA__", "__FONTCSS__", "__CONTACT__") if t in html]
    if left:
        raise SystemExit(f"unreplaced tokens: {left}")
    OUT.write_text(html)
    print(f"{OUT}\n  {len(cfg['festivals'])} festivals · {OUT.stat().st_size // 1024} KB")

if __name__ == "__main__":
    main()
