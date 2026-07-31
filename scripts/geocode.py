#!/usr/bin/env python3
"""Resolve the real-world position of every stage.

The organiser's map is a stylised drawing, so stage pins are placed at the
street intersections it shows them on. This pulls the actual OSM geometry for
those streets via Overpass and computes the intersection nodes, which gives
real coordinates instead of eyeballed ones.
"""

import itertools
import json
import pathlib
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "geo.json"

# Alppila, Helsinki
BBOX = (60.1840, 24.9280, 60.1960, 24.9520)  # S, W, N, E

STREETS = [
    "Viipurinkatu", "Kotkankatu", "Sturenkatu", "Aleksis Kiven katu",
    "Kolkankatu", "Loviisankatu", "Hangonkatu", "Kirstinkatu", "Tivolitie",
    "Porvoonkatu", "Vesilinnankatu", "Savonkatu", "Lämmittäjänkatu",
    "Itäinen Brahenkatu", "Läntinen Brahenkatu", "Karjalankatu",
]

QUERY = """[out:json][timeout:60];
(
%s
);
out geom;
""" % "\n".join(
    f'way["name"="{s}"]["highway"]({BBOX[0]},{BBOX[1]},{BBOX[2]},{BBOX[3]});'
    for s in STREETS
)


def overpass():
    for host in ("https://overpass-api.de/api/interpreter",
                 "https://overpass.kumi.systems/api/interpreter"):
        try:
            req = urllib.request.Request(
                host, data=QUERY.encode(),
                headers={"User-Agent": "KallioBlockPartyPlanner/1.0"})
            with urllib.request.urlopen(req, timeout=90) as r:
                return json.load(r)
        except Exception as e:
            print(f"  {host} failed: {e}")
    raise SystemExit("Overpass unreachable")


def main():
    data = overpass()
    streets = {}
    for el in data.get("elements", []):
        nm = el.get("tags", {}).get("name")
        if not nm or "geometry" not in el:
            continue
        streets.setdefault(nm, []).extend(
            (p["lat"], p["lon"]) for p in el["geometry"])

    print(f"Streets found: {len(streets)}")
    for k, v in sorted(streets.items()):
        print(f"  {k:24} {len(v)} points")

    # Shared vertices between two named streets = the junction.
    junctions = {}
    for a, b in itertools.combinations(sorted(streets), 2):
        shared = set(streets[a]) & set(streets[b])
        if shared:
            lat = sum(p[0] for p in shared) / len(shared)
            lon = sum(p[1] for p in shared) / len(shared)
            junctions[f"{a} x {b}"] = [round(lat, 6), round(lon, 6)]

    OUT.write_text(json.dumps(
        {"streets": {k: [[round(a, 6), round(b, 6)] for a, b in v]
                     for k, v in streets.items()},
         "junctions": junctions}, ensure_ascii=False, indent=1))
    print(f"\nJunctions: {len(junctions)} -> {OUT}")
    for k, v in sorted(junctions.items()):
        print(f"  {k:52} {v}")


if __name__ == "__main__":
    main()
