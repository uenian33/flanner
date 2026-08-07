#!/usr/bin/env python3
"""Where the pages get their type.

Both a subsetter and a linker, and which one a page uses is a judgement about
where the bytes hurt.

The subsetter came first, when every page was one self-contained file: the font
was inlined into each of them and nothing was shared, so a text page that sets
about a hundred distinct characters was carrying a 144 KB Latin + Latin-Extended
Roboto Flex. Cutting the font to the page's own text fixed that.

It stopped paying on the pages that matter. A planner sets every artist's name,
so its cut of Roboto Flex came to 83 KB against the full file's 84 KB — it was
carrying the whole font under another name, once per page, unshared and
un-cacheable, ahead of the first paint because a data URI in a stylesheet has to
be parsed before any rule applies.

So the pages link the four files instead, and the browser fetches each one once
for the whole site. `link()` is what the built pages call; `inline()` stays for
the artifact, which really is one file and has no second request to make.
"""
import base64
import io
import re
from functools import lru_cache
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parent.parent
# token in the page -> the file it stands for. A page that does not carry a
# token is not charged for the font: Inter is the card component's face and
# only the home page sets it, so the planners never pay the bytes.
FONTS = {
    "__ROBOTOFLEX_LATIN__": ROOT / "assets" / "font" / "robotoflex-latin.woff2",
    "__ROBOTOFLEX_EXT__":   ROOT / "assets" / "font" / "robotoflex-latin-ext.woff2",
    "__INTER_LATIN__":      ROOT / "assets" / "font" / "inter-latin.woff2",
    "__INTER_EXT__":        ROOT / "assets" / "font" / "inter-latin-ext.woff2",
}

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
    """Replace the font tokens with data URIs cut to this page's text.

    Called last, once the page is otherwise complete, because the set of
    characters to keep is only known then.
    """
    keep = chars_in(html)
    for token, path in FONTS.items():
        if token not in html:
            continue
        data = subset_font(path, keep)
        uri = "data:font/woff2;base64," + base64.b64encode(data).decode()
        html = html.replace(token, uri)
    return html


# Which files the browser should be told about before it has parsed the CSS
# that asks for them. Only the Latin cuts: the Extended ones carry a
# unicode-range the page will usually never touch, and preloading a font the
# page does not use is a download spent on nothing.
PRELOAD = ("__ROBOTOFLEX_LATIN__", "__INTER_LATIN__")


def link(html: str, root: str = "./") -> str:
    """Point the font tokens at the shared files, and preload the Latin cuts.

    `root` is the page's way back to the site root — `./` from the home page,
    `../` from a planner or an article — so the same tokens resolve from any
    depth.

    A `@font-face` src is discovered late: the browser has to have parsed the
    stylesheet before it knows the file exists, and on these pages that
    stylesheet sits behind a good deal of other CSS. The preload hints move the
    request to the top of the document, which is where it belongs for the face
    every visible glyph is set in.
    """
    for token, path in FONTS.items():
        if token not in html:
            continue
        html = html.replace(token, f"{root}assets/font/{path.name}")

    hints = "\n".join(
        f'<link rel="preload" href="{root}assets/font/{FONTS[t].name}" '
        f'as="font" type="font/woff2" crossorigin>'
        for t in PRELOAD if f"{root}assets/font/{FONTS[t].name}" in html
    )
    if hints:
        html = html.replace("<head>", "<head>\n" + hints, 1)
    return html
