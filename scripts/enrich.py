#!/usr/bin/env python3
"""Resolve streaming links and genre tags for every Kallio Block Party act.

Uses two keyless APIs:
  - Deezer  (api.deezer.com)      -> artist page, fan count, top-track preview
  - MusicBrainz (musicbrainz.org) -> genre tags + external URL relations
                                     (Spotify / SoundCloud / Bandcamp / homepage)

A match is only accepted when the returned artist name matches the booked name
after normalisation, so the long tail of local DJs stays unmatched rather than
being linked to a same-named stranger.
"""

import json
import pathlib
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
ACTS = ROOT / "data" / "kallio" / "acts.json"
OUT = ROOT / "data" / "kallio" / "enriched.json"

UA = "KallioBlockPartyPlanner/1.0 (personal schedule tool)"

# Names too generic to trust an automatic match on.
AMBIGUOUS = {
    "turbo", "ray", "aquarius", "dreamer", "void", "prinssi", "are", "wibe",
    "lionize", "rakata", "clamo", "mayela", "zeze", "1961", "hash", "seka",
    "power", "katto", "tens", "dr decks", "digital mindz", "temporados",
    "friends & family on decks", "happy hour crew", "rap stage showcase",
}


def get(url, tries=3):
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=25) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 503 and attempt < tries - 1:
                time.sleep(2 + attempt * 2)
                continue
            return None
        except Exception:
            if attempt < tries - 1:
                time.sleep(1)
                continue
            return None
    return None


def norm(s):
    s = unicodedata.normalize("NFKD", s.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"\b(dj|live|dj set|host)\b", " ", s)
    return re.sub(r"[^a-z0-9]+", "", s)


def deezer(name):
    q = urllib.parse.quote(name)
    d = get(f"https://api.deezer.com/search/artist?q={q}&limit=5")
    if not d or not d.get("data"):
        return None
    target = norm(name)
    for a in d["data"]:
        if norm(a["name"]) == target:
            return {
                "name": a["name"],
                "url": a["link"],
                "fans": a.get("nb_fan", 0),
                "img": a.get("picture_medium"),
                "id": a["id"],
            }
    return None


def deezer_top_track(artist_id):
    d = get(f"https://api.deezer.com/artist/{artist_id}/top?limit=1")
    if d and d.get("data"):
        t = d["data"][0]
        return {"title": t["title"], "url": t["link"], "preview": t.get("preview")}
    return None


def musicbrainz(name):
    q = urllib.parse.quote(f'artist:"{name}"')
    d = get(f"https://musicbrainz.org/ws/2/artist?query={q}&limit=5&fmt=json")
    time.sleep(1.1)  # MusicBrainz: 1 request/second
    if not d or not d.get("artists"):
        return None
    target = norm(name)
    for a in d["artists"]:
        if norm(a["name"]) != target:
            continue
        if a.get("score", 0) < 80:
            continue
        mbid = a["id"]
        rel = get(f"https://musicbrainz.org/ws/2/artist/{mbid}?inc=url-rels+tags&fmt=json")
        time.sleep(1.1)
        links, tags = {}, []
        if rel:
            for r in rel.get("relations", []):
                res = r.get("url", {}).get("resource", "")
                t = r.get("type", "")
                if "spotify.com" in res:
                    links["spotify"] = res
                elif "soundcloud.com" in res:
                    links["soundcloud"] = res
                elif "bandcamp.com" in res:
                    links["bandcamp"] = res
                elif "youtube.com" in res or "youtu.be" in res:
                    links.setdefault("youtube", res)
                elif t == "official homepage":
                    links["homepage"] = res
            tags = sorted(
                (t["name"] for t in rel.get("tags", []) if t.get("count", 0) > 0),
            )[:6]
        return {
            "mbid": mbid,
            "name": a["name"],
            "country": a.get("country"),
            "disambiguation": a.get("disambiguation"),
            "links": links,
            "tags": tags,
        }
    return None


def main():
    data = json.loads(ACTS.read_text())
    total = sum(len(s["acts"]) for s in data["stages"])
    done = 0
    hits = 0

    for stage in data["stages"]:
        for act in stage["acts"]:
            done += 1
            name = act["n"]
            print(f"[{done:3d}/{total}] {stage['name']:>22} | {name}", file=sys.stderr)

            if act.get("nomusic") or norm(name) in {norm(x) for x in AMBIGUOUS}:
                act["lookup"] = {"skipped": True}
                continue

            dz = deezer(name)
            mb = musicbrainz(name)

            found = {}
            if dz:
                found["deezer"] = dz
                top = deezer_top_track(dz["id"])
                if top:
                    found["top_track"] = top
            if mb:
                found["musicbrainz"] = mb

            if found:
                hits += 1
            act["lookup"] = found

    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    print(f"\nMatched {hits}/{total} acts -> {OUT}", file=sys.stderr)


if __name__ == "__main__":
    main()
