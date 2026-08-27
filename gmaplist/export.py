"""CSV / JSON serialisation of an annotated list."""

from __future__ import annotations

import csv
import datetime as _dt
import json
from collections.abc import Sequence
from pathlib import Path

from . import analyze

FIELDS = (
    "added_at",
    "updated_at",
    "added_by",
    "added_by_id",
    "name",
    "prefecture",
    "city",
    "country",
    "block",
    "address",
    "lat",
    "lng",
    "note",
    "note_by",
    "place_id",
    "mid",
    "prefecture_source",
    "maps_url",
)


def to_records(
    rows: Sequence[dict],
    tz_offset_hours: float = 9.0,
    anchor: tuple[float, float] | None = None,
) -> list[dict]:
    """Flatten rows for serialisation.

    With ``anchor`` set, a ``distance_km`` column is appended.
    """
    tz = _dt.timezone(_dt.timedelta(hours=tz_offset_hours))

    def stamp(value: _dt.datetime | None) -> str:
        return value.astimezone(tz).isoformat(timespec="seconds") if value else ""

    out = []
    for row in rows:
        p = row["place"]
        # The note's author, which differs from the entry's author whenever a
        # collaborator annotated someone else's place.
        note_by = p.note_author or p.added_by
        record = {
            "added_at": stamp(p.added_at),
            "updated_at": stamp(p.updated_at),
            "added_by": p.added_by.name if p.added_by else "",
            "added_by_id": p.added_by.user_id if p.added_by else "",
            "name": p.name,
            "prefecture": row["prefecture"] or "",
            "city": row["city"],
            "country": row.get("country", ""),
            "block": row["block"],
            "address": p.address,
            "lat": p.lat,
            "lng": p.lng,
            "note": p.note,
            "note_by": (note_by.name if note_by else "") if p.note else "",
            "place_id": p.place_id,
            "mid": p.mid,
            "prefecture_source": row["prefecture_source"],
            "maps_url": p.maps_url,
        }
        # Present only when gmaplist.experimental.attach has run.
        if "genre" in row:
            record["categories"] = "; ".join(row.get("categories") or [])
            record["genre"] = row["genre"]
            detail = row.get("detail")
            record["rating"] = detail.rating if detail else ""
            record["review_count"] = (
                detail.review_count if detail and detail.review_count else ""
            )
        if anchor is not None:
            record["distance_km"] = (
                round(analyze.haversine_km(anchor, (p.lat, p.lng)), 3)
                if p.lat is not None and p.lng is not None
                else ""
            )
        out.append(record)
    return out


def write_csv(
    path: str | Path,
    rows: Sequence[dict],
    tz_offset_hours: float = 9.0,
    anchor: tuple[float, float] | None = None,
) -> None:
    """Write UTF-8 with BOM so Excel opens Japanese text correctly."""
    records = to_records(rows, tz_offset_hours, anchor)
    fields = list(FIELDS)
    if any("genre" in row for row in rows):
        fields += ["categories", "genre", "rating", "review_count"]
    if anchor is not None:
        fields.append("distance_km")
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(records)


def write_json(
    path: str | Path,
    plist,
    rows: Sequence[dict],
    tz_offset_hours: float = 9.0,
    anchor: tuple[float, float] | None = None,
) -> None:
    payload = {
        "list_id": plist.list_id,
        "title": plist.title,
        "description": plist.description,
        "owner": plist.owner.name if plist.owner else None,
        "url": plist.url,
        "created_at": plist.created_at.isoformat() if plist.created_at else None,
        "updated_at": plist.updated_at.isoformat() if plist.updated_at else None,
        "count": len(rows),
        "places": to_records(rows, tz_offset_hours, anchor),
    }
    Path(path).write_text(
        json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8"
    )


def write_geojson(
    path: str | Path,
    rows: Sequence[dict],
    tz_offset_hours: float = 9.0,
    anchor: tuple[float, float] | None = None,
) -> None:
    """Point FeatureCollection, ready to drop into any map viewer."""
    features = []
    for record, row in zip(
        to_records(rows, tz_offset_hours, anchor), rows, strict=True
    ):
        p = row["place"]
        if p.lat is None or p.lng is None:
            continue
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [p.lng, p.lat]},
                "properties": record,
            }
        )
    Path(path).write_text(
        json.dumps(
            {"type": "FeatureCollection", "features": features}, ensure_ascii=False
        ),
        encoding="utf-8",
    )
