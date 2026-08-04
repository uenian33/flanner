#!/usr/bin/env python3
"""Where the built pages get their paths and their inlined bytes.

These three lived in the old planner builder, which every other builder then
imported for them. The planner is generated from the design artifact now, so
the shared pieces moved here rather than leaving a builder standing to be
imported for its constants.
"""
from __future__ import annotations

import base64
import mimetypes
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

# The calibration tool's per-stage pins. The planners take their colours from
# the generated M3 palettes; this is a workbench, and these are only there to
# tell one draggable pin from another.
STAGE_COLORS = {
    "alive": "#f59e0b", "woj": "#c084fc", "happyhour": "#f472b6", "ptnky": "#22d3ee",
    "dnb": "#4ade80", "katto": "#60a5fa", "rap": "#fb7185", "power": "#a3e635",
    "soundgarden": "#2dd4bf", "activities": "#94a3b8",
}


def data_uri(path: pathlib.Path) -> str:
    """A file as a data URI. Everything a page needs travels inside it, so
    every asset arrives through here."""
    mime = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
    if path.suffix == ".woff2":
        mime = "font/woff2"
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode()}"
