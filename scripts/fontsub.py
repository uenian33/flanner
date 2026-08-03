#!/usr/bin/env python3
"""Subset Roboto Flex to the characters a page actually sets.

Every page here is one self-contained file, which means the font is inlined
into each one and nothing is shared between them. A full Latin + Latin-Extended
Roboto Flex is 144 KB before base64, and it doubled the weight of a text page
that uses about a hundred distinct characters.

So each page gets its own cut of the font. The variable axes survive — this
drops glyphs, not axes, so wght and opsz still work across the whole range.
"""
import base64
import io
import re
from functools import lru_cache
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parent.parent
FONTS = [ROOT / "assets" / "font" / "robotoflex-latin.woff2",
         ROOT / "assets" / "font" / "robotoflex-latin-ext.woff2"]

# Characters every page needs whatever its copy says: the digits and
# punctuation that live in templates, and the arrows and dashes the UI draws.
ALWAYS = set(
    "0123456789"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "abcdefghijklmnopqrstuvwxyz"
    " !\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~"
    " –—‘’“”…·→←×"
    "äöåÄÖÅ"   # Finnish and Swedish
)

TAG = re.compile(r"<[^>]+>")


def chars_in(html: str) -> set:
    """Every character the page can render as text.

    Deliberately generous: tag names and attribute values are stripped, but
    anything inside a script string counts, because the page builds markup at
    runtime from data held in those strings.
    """
    text = TAG.sub(" ", html)
    return set(text) | ALWAYS


@lru_cache(maxsize=None)
def _load(path: str) -> bytes:
    return Path(path).read_bytes()


def subset_font(path: Path, keep: set) -> bytes:
    font = TTFont(io.BytesIO(_load(str(path))))
    unicodes = {ord(c) for c in keep if ord(c) > 0x1f}
    options = subset.Options()
    options.layout_features = ["*"]      # keep kerning and the rest
    options.name_IDs = ["*"]
    options.notdef_outline = True
    options.recalc_bounds = True
    options.drop_tables = []
    subsetter = subset.Subsetter(options=options)
    subsetter.populate(unicodes=unicodes)
    subsetter.subset(font)
    out = io.BytesIO()
    font.flavor = "woff2"
    font.save(out)
    return out.getvalue()


def inline(html: str) -> str:
    """Replace the two font tokens with data URIs cut to this page's text.

    Called last, once the page is otherwise complete, because the set of
    characters to keep is only known then.
    """
    keep = chars_in(html)
    for token, path in (("__ROBOTOFLEX_LATIN__", FONTS[0]),
                        ("__ROBOTOFLEX_EXT__", FONTS[1])):
        data = subset_font(path, keep)
        uri = "data:font/woff2;base64," + base64.b64encode(data).decode()
        html = html.replace(token, uri)
    return html
