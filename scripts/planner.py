#!/usr/bin/env python3
"""Take the planner design apart, so a build can put it back together.

`scripts/planner.artifact.html` is the design exactly as it was exported: a
self-extracting bundle holding a template with `{{ }}` bindings, the component
class that feeds them, and four libraries — React, ReactDOM, Leaflet and the
dc-runtime that compiles the one against the other. Nothing in it is meant to
be edited by hand, and nothing here does: this module only unpacks it and hands
the pieces to `build_planner.py`, which substitutes a festival's own data.

Re-exporting the design from the artifact tool and dropping the new file in
place is therefore the whole update procedure. If a substitution stops matching
its anchor, the build fails loudly rather than shipping a planner with someone
else's line-up in it.
"""
from __future__ import annotations

import base64
import gzip
import html
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
ARTIFACT = ROOT / "scripts" / "planner.artifact.html"

# The four libraries, by the mime the bundler records for them. React has to be
# in the document before the runtime looks for it, or the runtime fetches it
# from unpkg — which a page that has to work with no signal cannot do.
LIB_ORDER = ("react", "react-dom", "leaflet", "dc-runtime")
LIB_MARK = {
    "react": "react.production.min.js",
    "react-dom": "react-dom.production.min.js",
    "leaflet": "Leaflet 1.9.4",
    "dc-runtime": "dc-runtime/src",
}

# Latin and Latin Extended carry Finnish and English. The export also ships
# Cyrillic, Greek and Vietnamese — 150KB of a page that never draws them.
KEEP_SUBSETS = ("latin", "latin-ext")


class MissingAnchor(RuntimeError):
    """A substitution found nothing to substitute — the design has moved."""


def _blocks(src: str) -> dict:
    out = {}
    for kind in ("manifest", "template", "page_order"):
        m = re.search(r'<script type="__bundler/%s">(.*?)</script>' % kind, src, re.S)
        if m:
            out[kind] = json.loads(m.group(1).strip())
    return out


def _asset(entry: dict) -> bytes:
    data = base64.b64decode(entry["data"])
    return gzip.decompress(data) if entry.get("compressed") else data


class Artifact:
    """The design, unpacked."""

    def __init__(self, path: pathlib.Path = ARTIFACT):
        src = path.read_text()
        blocks = _blocks(src)
        self.manifest = blocks["manifest"]
        template = blocks["template"]

        # ---- libraries, in load order ----
        self.libs: dict[str, str] = {}
        for uid, entry in self.manifest.items():
            if entry["mime"] != "text/javascript":
                continue
            text = _asset(entry).decode()
            for name, mark in LIB_MARK.items():
                if mark in text[:4000]:
                    self.libs[name] = text
                    break
        missing = [n for n in LIB_ORDER if n not in self.libs]
        if missing:
            raise MissingAnchor(f"artifact is missing {missing}")

        # ---- the three pieces of the component ----
        xdc = re.search(r"<x-dc>(.*)</x-dc>", template, re.S)
        script = re.search(
            r'<script type="text/x-dc" data-dc-script=""(.*?)>(.*?)</script>',
            template, re.S)
        if not xdc or not script:
            raise MissingAnchor("artifact has no <x-dc> block or no component script")
        body = xdc.group(1)
        self.props = html.unescape(
            re.search(r'data-props="(.*?)"', script.group(1), re.S).group(1))
        self.js = script.group(2)

        # The helmet is the runtime's way of writing to <head>; we place its
        # contents ourselves, minus the two preconnects to Google's font hosts,
        # which this page never talks to.
        helmet = re.search(r"<helmet>(.*?)</helmet>", body, re.S)
        self.head_css = ""
        if helmet:
            for style in re.findall(r"<style>(.*?)</style>", helmet.group(1), re.S):
                self.head_css += style + "\n"
            body = body.replace(helmet.group(0), "")
        self.template = body.strip()

        # ---- assets the template and the CSS point at, by uuid ----
        self.assets = {uid: e for uid, e in self.manifest.items()
                       if e["mime"] != "text/javascript"}

    # -- fonts ---------------------------------------------------------
    def font_css(self) -> str:
        """The @font-face block, trimmed to the subsets this site sets and to
        one face per subset.

        The export declares thirty-five faces — seven subsets at five weights —
        but each subset's five weights name the same file: Inter is a variable
        font and one file carries the whole axis. Inlined face by face that is
        the same 85KB of Latin base64'd five times over. Each subset is emitted
        once instead, with the weight range the file actually holds."""
        seen, kept = set(), []
        for subset, rule in re.findall(r"/\* ([\w-]+) \*/\s*(@font-face \{.*?\})",
                                       self.head_css, re.S):
            if subset not in KEEP_SUBSETS or subset in seen:
                continue
            seen.add(subset)
            rule = re.sub(r"font-weight: [^;]+;", "font-weight: 100 900;", rule)
            for uid in re.findall(r"[0-9a-f-]{36}", rule):
                if uid in self.assets:
                    rule = rule.replace(uid, self.data_uri(uid))
            kept.append(rule)
        if len(kept) != len(KEEP_SUBSETS):
            raise MissingAnchor(
                f"expected one face per subset {KEEP_SUBSETS}, got {len(kept)}")
        return "\n".join(kept)

    def other_css(self) -> str:
        """Everything in the helmet that is not a font face."""
        css = re.sub(r"/\* [\w-]+ \*/\s*@font-face \{.*?\}", "", self.head_css, flags=re.S)
        return css.strip()

    def data_uri(self, uid: str) -> str:
        e = self.assets[uid]
        return "data:%s;base64,%s" % (e["mime"], base64.b64encode(_asset(e)).decode())

    def resolve(self, text: str) -> str:
        """Swap any remaining uuid asset reference for its data URI."""
        for uid in set(re.findall(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", text)):
            if uid in self.assets:
                text = text.replace(uid, self.data_uri(uid))
        return text


def inline_js(src: str) -> str:
    """Neutralise the four sequences that a library's own source can put into
    the page's structure when it is inlined rather than linked.

    `</script`, `<script` and `<!--` decide where the block ends: the runtime
    carries `<script data-dc-script>` in an error message, and left alone the
    tail of the library becomes a stray element that renders its own source as
    page text. `<x-dc` is subtler — the runtime finds the component by
    `querySelector('x-dc')`, and its error strings mention the tag by name, so
    an unescaped one in the head has the runtime compile *itself* as the
    component. Each is written as an escape that is valid inside the string
    literal it sits in, so every string keeps its meaning."""
    return (src.replace("</", "<\\/")
               .replace("<script", "\\x3Cscript")
               .replace("<!--", "\\x3C!--")
               .replace("<x-dc", "\\x3Cx-dc"))


def sub_once(text: str, pattern: str, repl: str, what: str, flags=re.S) -> str:
    """Substitute exactly once, or fail the build. A silent miss here ships a
    planner showing the design's sample line-up."""
    out, n = re.subn(pattern, lambda _m: repl, text, count=1, flags=flags)
    if n != 1:
        raise MissingAnchor(f"{what}: pattern matched {n} times, expected 1")
    return out
