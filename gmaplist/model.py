"""Typed view over the getlist payload.

The response is protobuf rendered as JSON: nested arrays with no field names,
so every accessor below is an index discovered by reading real responses. The
indices are stable in practice but are the one part of this package that can
break if Google reshapes the message.
"""

from __future__ import annotations

import datetime as _dt
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

_UINT64 = 1 << 64


def _at(node: Any, *path: int) -> Any:
    """Index into nested lists, returning None instead of raising."""
    for i in path:
        if not isinstance(node, list) or len(node) <= i:
            return None
        node = node[i]
    return node


def _ts(node: Any) -> _dt.datetime | None:
    """Convert a ``[seconds, nanos]`` pair into an aware UTC datetime."""
    secs = _at(node, 0)
    if secs is None:
        return None
    nanos = _at(node, 1) or 0
    return _dt.datetime.fromtimestamp(secs + nanos / 1e9, _dt.timezone.utc)


@dataclass(frozen=True)
class Author:
    """A person who added an entry, or who owns the list."""

    name: str
    user_id: str = ""
    avatar_url: str | None = None

    @classmethod
    def _parse(cls, node: Any) -> Author | None:
        name = _at(node, 0)
        if not name:
            return None
        return cls(name=name, user_id=_at(node, 2) or "", avatar_url=_at(node, 1))


@dataclass(frozen=True)
class Place:
    """One saved place, with the collaboration metadata Google keeps on it."""

    name: str
    note: str = ""
    address: str = ""
    lat: float | None = None
    lng: float | None = None
    place_id: str = ""
    mid: str = ""
    added_by: Author | None = None
    added_at: _dt.datetime | None = None
    updated_at: _dt.datetime | None = None

    @property
    def maps_url(self) -> str:
        if self.place_id:
            return f"https://www.google.com/maps/place/?q=place_id:{self.place_id}"
        if self.lat is not None:
            return f"https://www.google.com/maps/@{self.lat},{self.lng},17z"
        return ""

    @classmethod
    def _parse(cls, node: Any) -> Place:
        ids = _at(node, 1, 6)
        place_id = ""
        if isinstance(ids, list) and len(ids) >= 2:
            try:
                # Two signed 64-bit halves; Google prints them as unsigned hex.
                hi, lo = (int(x) % _UINT64 for x in ids[:2])
                place_id = f"0x{hi:x}:0x{lo:x}"
            except (TypeError, ValueError):
                place_id = ""
        return cls(
            name=_at(node, 2) or "",
            note=_at(node, 3) or "",
            address=(_at(node, 1, 4) or "").strip(),
            lat=_at(node, 1, 5, 2),
            lng=_at(node, 1, 5, 3),
            place_id=place_id,
            mid=_at(node, 1, 7) or "",
            added_by=Author._parse(_at(node, 12)),
            added_at=_ts(_at(node, 9)),
            updated_at=_ts(_at(node, 10)),
        )


@dataclass
class PlaceList:
    """A shared list: metadata plus every place in it."""

    list_id: str
    title: str = ""
    description: str = ""
    owner: Author | None = None
    created_at: _dt.datetime | None = None
    updated_at: _dt.datetime | None = None
    reported_count: int = 0
    places: list[Place] = field(default_factory=list)

    @property
    def url(self) -> str:
        return f"https://www.google.com/maps/placelists/list/{self.list_id}"

    @property
    def truncated(self) -> bool:
        """True when Google reported more places than it returned."""
        return bool(self.reported_count) and len(self.places) < self.reported_count

    def __len__(self) -> int:
        return len(self.places)

    def __iter__(self) -> Iterator[Place]:
        return iter(self.places)

    @classmethod
    def _parse(cls, payload: Any) -> PlaceList:
        root = _at(payload, 0)
        if root is None or _at(root, 0, 0) is None:
            raise ValueError(
                "unexpected getlist payload shape; the list may be private, "
                "deleted, or the request was throttled: " + repr(payload)[:200]
            )
        items = _at(root, 8) or []
        return cls(
            list_id=_at(root, 0, 0) or "",
            title=_at(root, 4) or "",
            description=_at(root, 5) or "",
            owner=Author._parse(_at(root, 3)),
            created_at=_ts(_at(root, 10)),
            updated_at=_ts(_at(root, 11)),
            reported_count=_at(root, 12) or 0,
            places=[Place._parse(it) for it in items],
        )
