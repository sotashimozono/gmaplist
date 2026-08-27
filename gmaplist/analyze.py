"""Aggregations over an annotated shared list."""

from __future__ import annotations

import datetime as _dt
from collections import Counter, defaultdict
from typing import Sequence

UNKNOWN = "(unknown)"


def _author(row: dict) -> str:
    by = row["place"].added_by
    return by.name if by else UNKNOWN


def _region(row: dict) -> str:
    return row["prefecture"] or "abroad"


def by_contributor(rows: Sequence[dict]) -> list[dict]:
    """Per-person totals, note habits and the regions they cover."""
    groups: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        groups[_author(row)].append(row)

    out = []
    for name, items in groups.items():
        notes = [r["place"].note for r in items if r["place"].note]
        stamps = sorted(r["place"].added_at for r in items if r["place"].added_at)
        out.append(
            {
                "name": name,
                "count": len(items),
                "share": len(items) / len(rows) if rows else 0.0,
                "with_note": len(notes),
                "avg_note_chars": sum(len(n) for n in notes) / len(notes) if notes else 0.0,
                "top_regions": Counter(_region(r) for r in items).most_common(3),
                "first_added": stamps[0] if stamps else None,
                "last_added": stamps[-1] if stamps else None,
            }
        )
    out.sort(key=lambda d: -d["count"])
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


def timeline(rows: Sequence[dict], granularity: str = "day", tz_offset_hours: float = 9.0) -> list[tuple[str, int]]:
    """Additions bucketed by day, month or hour in a fixed UTC offset."""
    fmt = {"day": "%Y-%m-%d", "month": "%Y-%m", "hour": "%Y-%m-%d %H"}[granularity]
    tz = _dt.timezone(_dt.timedelta(hours=tz_offset_hours))
    counts = Counter(
        r["place"].added_at.astimezone(tz).strftime(fmt)
        for r in rows
        if r["place"].added_at
    )
    return sorted(counts.items())


def crosstab(rows: Sequence[dict]) -> tuple[list[str], list[str], dict[tuple[str, str], int]]:
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
