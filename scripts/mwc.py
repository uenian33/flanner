#!/usr/bin/env python3
"""Bundle the Material Web components and hand them to the page builders.

Every page here is one self-contained file, so the components cannot be a
script tag pointing at a CDN — they are bundled with esbuild and inlined like
the fonts and the artwork. The bundle is rebuilt only when its entry point or
the installed package changes.

The components read their colours, shapes and type from `--md-sys-*` custom
properties, which is exactly what `m3color.py` and `_tokens.css` already emit.
Nothing has to be re-themed: the library picks up the scheme we generate.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENTRY = ROOT / "scripts" / "mwc.js"
OUT = ROOT / "assets" / "mwc.bundle.js"
LOCK = ROOT / "package-lock.json"


def _stale() -> bool:
    if not OUT.exists():
        return True
    age = OUT.stat().st_mtime
    return any(p.exists() and p.stat().st_mtime > age for p in (ENTRY, LOCK))


def bundle() -> str:
    """The minified ESM bundle, built if the sources moved under it."""
    if _stale():
        OUT.parent.mkdir(parents=True, exist_ok=True)
        proc = subprocess.run(
            ["npx", "esbuild", str(ENTRY), "--bundle", "--format=esm",
             "--minify", f"--outfile={OUT}"],
            cwd=ROOT, capture_output=True, text=True)
        if proc.returncode != 0:
            raise SystemExit("esbuild failed:\n" + proc.stderr)
        print(f"  bundled material-web · {OUT.stat().st_size // 1024} KB")
    return OUT.read_text()


def script() -> str:
    """The bundle as a module script, ready to drop into a page."""
    return '<script type="module">\n' + bundle() + '\n</script>'


if __name__ == "__main__":
    bundle()
