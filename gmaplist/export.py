"""CSV / JSON serialisation of an annotated list."""

from __future__ import annotations

import csv
import datetime as _dt
import json
from pathlib import Path
from typing import Sequence

FIELDS = (
    "added_at", "updated_at", "added_by", "added_by_id", "name", "prefecture",
    "city", "block", "address", "lat", "lng", "note", "place_id", "mid",
    "prefecture_source", "maps_url",
)


def to_records(rows: Sequence[dict], tz_offset_hours: float = 9.0) -> list[dict]:
    tz = _dt.timezone(_dt.timedelta(hours=tz_offset_hours))

    def stamp(value: _dt.datetime | None) -> str:
        return value.astimezone(tz).isoformat(timespec="seconds") if value else ""

    out = []
    for row in rows:
        p = row["place"]
        out.append(
            {
                "added_at": stamp(p.added_at),
                "updated_at": stamp(p.updated_at),
                "added_by": p.added_by.name if p.added_by else "",
                "added_by_id": p.added_by.user_id if p.added_by else "",
                "name": p.name,
                "prefecture": row["prefecture"] or "",
                "city": row["city"],
                "block": row["block"],
                "address": p.address,
                "lat": p.lat,
                "lng": p.lng,
                "note": p.note,
                "place_id": p.place_id,
                "mid": p.mid,
                "prefecture_source": row["prefecture_source"],
                "maps_url": p.maps_url,
            }
        )
    return out


def write_csv(path: str | Path, rows: Sequence[dict], tz_offset_hours: float = 9.0) -> None:
    """Write UTF-8 with BOM so Excel opens Japanese text correctly."""
    records = to_records(rows, tz_offset_hours)
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(FIELDS))
        writer.writeheader()
        writer.writerows(records)


def write_json(path: str | Path, plist, rows: Sequence[dict], tz_offset_hours: float = 9.0) -> None:
    payload = {
        "list_id": plist.list_id,
        "title": plist.title,
        "description": plist.description,
        "owner": plist.owner.name if plist.owner else None,
        "url": plist.url,
        "created_at": plist.created_at.isoformat() if plist.created_at else None,
        "updated_at": plist.updated_at.isoformat() if plist.updated_at else None,
        "count": len(rows),
        "places": to_records(rows, tz_offset_hours),
    }
    Path(path).write_text(
        json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8"
    )


def write_geojson(path: str | Path, rows: Sequence[dict], tz_offset_hours: float = 9.0) -> None:
    """Point FeatureCollection, ready to drop into any map viewer."""
    features = []
    for record, row in zip(to_records(rows, tz_offset_hours), rows):
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
        json.dumps({"type": "FeatureCollection", "features": features}, ensure_ascii=False),
        encoding="utf-8",
    )
