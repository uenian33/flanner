#!/usr/bin/env python3
"""robots.txt, sitemap.xml, the IndexNow key file — and the submission itself.

Run this last, after the pages are built: the sitemap's lastmod comes from the
files on disk, so building it first would date every page to the previous run.

    python3 scripts/build_seo.py            # write the files
    python3 scripts/build_seo.py --submit   # …and push the URLs to IndexNow

Google no longer accepts a sitemap ping and only picks up changes by crawling
or through Search Console. Bing, Yandex, Seznam and Naver all take the IndexNow
push, which is the one lever here that works without an account.
"""
from __future__ import annotations

import json
import sys
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import schema
import seo

ROOT = Path(__file__).resolve().parent.parent
# The planners come from the records, so a festival added to data/ is in the
# sitemap and in the IndexNow push without this file being touched — a page no
# sitemap names is a page that waits to be found by accident.
PAGES = ([""] + [f["planner"] for f in schema.load()["festivals"] if f.get("planner")]
         + ["about/", "faq/", "terms/", "privacy/"])


def lastmod(path: str) -> str:
    """The build date of the page itself, not the day this script happened to run."""
    f = ROOT / (path + "index.html")
    if not f.exists():
        raise SystemExit(f"missing page: {f.relative_to(ROOT)} — build the pages first")
    return datetime.fromtimestamp(f.stat().st_mtime, timezone.utc).date().isoformat()


def submit() -> None:
    """One request, every URL. IndexNow accepts a batch and answers 200/202."""
    body = json.dumps({
        "host": "uenian33.github.io",
        "key": seo.INDEXNOW_KEY,
        "keyLocation": f"{seo.BASE}/{seo.INDEXNOW_KEY}.txt",
        "urlList": [f"{seo.BASE}/{p}" for p in PAGES],
    }).encode()
    req = urllib.request.Request(
        "https://api.indexnow.org/IndexNow", data=body,
        headers={"Content-Type": "application/json; charset=utf-8"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            print(f"  IndexNow → {r.status} {r.reason} ({len(PAGES)} urls)")
    except Exception as e:
        # A rejection here is worth reading, not swallowing: 403 means the key
        # file is not reachable yet, which happens if Pages has not deployed.
        print(f"  IndexNow failed: {e}", file=sys.stderr)


def main() -> None:
    seo.write_robots_and_sitemap([(p, lastmod(p)) for p in PAGES])
    print(f"  {seo.INDEXNOW_KEY}.txt")
    if "--submit" in sys.argv:
        submit()


if __name__ == "__main__":
    print(ROOT)
    main()
