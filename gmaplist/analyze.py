"""Aggregations over an annotated shared list."""

from __future__ import annotations

import datetime as _dt
import math
from collections import Counter, defaultdict
from collections.abc import Sequence

UNKNOWN = "(unknown)"


def _author(row: dict) -> str:
    by = row["place"].added_by
    return by.name if by else UNKNOWN


def _note_author(row: dict) -> str:
    """Who wrote the note, which is not always who added the place."""
    place = row["place"]
    by = place.note_author or place.added_by
    return by.name if by else UNKNOWN


def _region(row: dict) -> str:
    return row["prefecture"] or row.get("country") or "abroad"


def by_contributor(rows: Sequence[dict]) -> list[dict]:
    """Per-person totals, note habits and the regions they cover.

    ``count`` is places added. ``notes_written`` is notes authored, counted
    against the note's own author: on a collaborative list one person can
    annotate another's entry, and folding those into the entry author would
    credit the wrong person.
    """
    added: dict[str, list[dict]] = defaultdict(list)
    written: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        added[_author(row)].append(row)
        if row["place"].note:
            written[_note_author(row)].append(row["place"].note)

    out = []
    for name in set(added) | set(written):
        items = added.get(name, [])
        notes = written.get(name, [])
        stamps = sorted(r["place"].added_at for r in items if r["place"].added_at)
        out.append(
            {
                "name": name,
                "count": len(items),
                "share": len(items) / len(rows) if rows else 0.0,
                # Entries this person added that carry a note by anyone.
                "with_note": sum(1 for r in items if r["place"].note),
                "notes_written": len(notes),
                "avg_note_chars": sum(len(n) for n in notes) / len(notes)
                if notes
                else 0.0,
                "top_regions": Counter(_region(r) for r in items).most_common(3),
                "first_added": stamps[0] if stamps else None,
                "last_added": stamps[-1] if stamps else None,
            }
        )
    out.sort(key=lambda d: (-d["count"], -d["notes_written"], d["name"]))
    return out


def cross_author_notes(rows: Sequence[dict]) -> list[dict]:
    """Entries where one person added the place and another wrote the note.

    The clearest evidence of a list actually being collaborated on rather than
    merely shared.
    """
    out = []
    for row in rows:
        place = row["place"]
        if not (place.note and place.note_author and place.added_by):
            continue
        if place.note_author.user_id and place.added_by.user_id:
            same = place.note_author.user_id == place.added_by.user_id
        else:
            same = place.note_author.name == place.added_by.name
        if not same:
            out.append(
                {
                    "name": place.name,
                    "added_by": place.added_by.name,
                    "note_by": place.note_author.name,
                    "note": place.note,
                }
            )
    return out


def by_prefecture(rows: Sequence[dict]) -> list[tuple[str, int]]:
    return Counter(_region(r) for r in rows).most_common()


def by_block(rows: Sequence[dict]) -> list[tuple[str, int]]:
    return Counter(r["block"] or "abroad" for r in rows).most_common()


def by_city(rows: Sequence[dict], limit: int | None = None) -> list[tuple[str, int]]:
    counts = Counter(
        f"{r['prefecture']}{r['city']}" for r in rows if r["prefecture"] and r["city"]
    )
    return counts.most_common(limit)


def timeline(
    rows: Sequence[dict], granularity: str = "day", tz_offset_hours: float = 9.0
) -> list[tuple[str, int]]:
    """Additions bucketed by day, month or hour in a fixed UTC offset."""
    fmt = {"day": "%Y-%m-%d", "month": "%Y-%m", "hour": "%Y-%m-%d %H"}[granularity]
    tz = _dt.timezone(_dt.timedelta(hours=tz_offset_hours))
    counts = Counter(
        r["place"].added_at.astimezone(tz).strftime(fmt)
        for r in rows
        if r["place"].added_at
    )
    return sorted(counts.items())


def crosstab(
    rows: Sequence[dict],
) -> tuple[list[str], list[str], dict[tuple[str, str], int]]:
    """Contributor x region block, ordered by descending totals."""
    people = [d["name"] for d in by_contributor(rows)]
    blocks = [b for b, _ in by_block(rows)]
    cells = Counter((_author(r), r["block"] or "abroad") for r in rows)
    return people, blocks, dict(cells)


def note_leaders(rows: Sequence[dict], limit: int = 5) -> list[tuple[str, int]]:
    """Longest notes, as a proxy for who actually wrote things up."""
    scored = [(r["place"].name, len(r["place"].note)) for r in rows if r["place"].note]
    scored.sort(key=lambda t: -t[1])
    return scored[:limit]


def duplicates(rows: Sequence[dict]) -> list[tuple[str, int]]:
    """Places saved more than once, by Google place id."""
    counts = Counter(r["place"].place_id for r in rows if r["place"].place_id)
    names = {r["place"].place_id: r["place"].name for r in rows}
    return [(names[pid], n) for pid, n in counts.most_common() if n > 1]


EARTH_RADIUS_KM = 6371.0088


def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Great-circle distance between two (lat, lng) pairs, in kilometres."""
    lat1, lat2 = math.radians(a[0]), math.radians(b[0])
    dlat = lat2 - lat1
    dlng = math.radians(b[1] - a[1])
    h = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
    )
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(h))


def distances_from(
    rows: Sequence[dict], anchor: tuple[float, float]
) -> list[tuple[dict, float]]:
    """Pair each located row with its distance from ``anchor``, nearest first.

    Rows without coordinates are dropped rather than reported as zero.
    """
    out = [
        (row, haversine_km(anchor, (row["place"].lat, row["place"].lng)))
        for row in rows
        if row["place"].lat is not None and row["place"].lng is not None
    ]
    out.sort(key=lambda pair: pair[1])
    return out


def distance_summary(rows: Sequence[dict], anchor: tuple[float, float]) -> dict:
    """How far a list reaches from a reference point.

    A saved list is often assumed to be "places near us". Measuring against a
    home coordinate is what tells you whether that is actually true.
    """
    pairs = distances_from(rows, anchor)
    if not pairs:
        return {
            "count": 0,
            "median_km": 0.0,
            "mean_km": 0.0,
            "bands": [],
            "farthest": [],
        }
    km = [d for _, d in pairs]
    bands = []
    edges = [(0, 10), (10, 50), (50, 300), (300, 900), (900, math.inf)]
    for lo, hi in edges:
        n = sum(1 for d in km if lo <= d < hi)
        bands.append((lo, hi, n))
    mid = len(km) // 2
    median = km[mid] if len(km) % 2 else (km[mid - 1] + km[mid]) / 2
    return {
        "count": len(km),
        "median_km": median,
        "mean_km": sum(km) / len(km),
        "bands": bands,
        "nearest": [(r["place"].name, d) for r, d in pairs[:3]],
        "farthest": [(r["place"].name, d) for r, d in pairs[-3:]],
    }


def contributor_geography(
    rows: Sequence[dict], anchor: tuple[float, float] | None = None
) -> list[dict]:
    """Per contributor: where their picks cluster and how tightly.

    ``spread_km`` is the median distance from their own centroid, so a person
    who saved twenty places in one town reads as ~0 while a person covering a
    whole region does not.
    """
    groups: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for row in rows:
        place = row["place"]
        if place.lat is None or place.lng is None:
            continue
        groups[_author(row)].append((place.lat, place.lng))

    out = []
    for name, points in groups.items():
        centroid = (
            sum(p[0] for p in points) / len(points),
            sum(p[1] for p in points) / len(points),
        )
        spans = sorted(haversine_km(centroid, p) for p in points)
        mid = len(spans) // 2
        spread = spans[mid] if len(spans) % 2 else (spans[mid - 1] + spans[mid]) / 2
        out.append(
            {
                "name": name,
                "count": len(points),
                "centroid": centroid,
                "spread_km": spread,
                "anchor_km": haversine_km(anchor, centroid) if anchor else None,
            }
        )
    out.sort(key=lambda d: (-d["count"], d["name"]))
    return out
