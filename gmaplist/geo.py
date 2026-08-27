"""Resolve places to Japanese prefectures.

Google returns a formatted address for only some entries, so this falls back
to point-in-polygon against prefecture boundaries. The boundary file is
downloaded once and cached under the user cache directory.
"""

from __future__ import annotations

import json
import os
import urllib.request
from collections.abc import Iterable, Sequence
from pathlib import Path

GEOJSON_URL = "https://raw.githubusercontent.com/dataofjapan/land/master/japan.geojson"

PREFECTURES: tuple[str, ...] = (
    "北海道",
    "青森県",
    "岩手県",
    "宮城県",
    "秋田県",
    "山形県",
    "福島県",
    "茨城県",
    "栃木県",
    "群馬県",
    "埼玉県",
    "千葉県",
    "東京都",
    "神奈川県",
    "新潟県",
    "富山県",
    "石川県",
    "福井県",
    "山梨県",
    "長野県",
    "岐阜県",
    "静岡県",
    "愛知県",
    "三重県",
    "滋賀県",
    "京都府",
    "大阪府",
    "兵庫県",
    "奈良県",
    "和歌山県",
    "鳥取県",
    "島根県",
    "岡山県",
    "広島県",
    "山口県",
    "徳島県",
    "香川県",
    "愛媛県",
    "高知県",
    "福岡県",
    "佐賀県",
    "長崎県",
    "熊本県",
    "大分県",
    "宮崎県",
    "鹿児島県",
    "沖縄県",
)

_BLOCK_RANGES = (
    ("北海道", 1),
    ("東北", 6),
    ("関東", 7),
    ("中部", 9),
    ("近畿", 7),
    ("中国", 5),
    ("四国", 4),
    ("九州", 8),
)


def _build_blocks() -> dict[str, str]:
    out, i = {}, 0
    for block, n in _BLOCK_RANGES:
        for pref in PREFECTURES[i : i + n]:
            out[pref] = block
        i += n
    return out


BLOCKS: dict[str, str] = _build_blocks()

# Longest-first so that e.g. 京都府 is never shadowed by a shorter name.
_PREF_BY_LENGTH = sorted(PREFECTURES, key=len, reverse=True)


def prefecture_from_address(address: str) -> str | None:
    """Pick the prefecture name out of a formatted Japanese address."""
    if not address:
        return None
    for pref in _PREF_BY_LENGTH:
        if pref in address:
            return pref
    return None


def city_from_address(address: str) -> str:
    """Return the municipality that follows the prefecture, if present."""
    pref = prefecture_from_address(address)
    if not pref:
        return ""
    rest = address.split(pref, 1)[1]
    for i, ch in enumerate(rest):
        if ch in "市区町村":
            return rest[: i + 1].strip()
    return ""


def country_from_address(address: str) -> str:
    """Return the country of a non-Japanese address, or "" if it is Japanese.

    Google formats foreign addresses with the country last, localised to the
    requested language: "Friesenstrasse 64-66, 50670 Koeln, ..." Collapsing
    every one of those to a single "abroad" bucket throws away the only piece
    of geography the payload does supply for them.
    """
    if not address or prefecture_from_address(address):
        return ""
    tail = address.rsplit(",", 1)[-1].strip()
    return tail if tail and tail != address.strip() else ""


def cache_dir() -> Path:
    """Per-user cache location, resolved at runtime on every platform."""
    base = os.environ.get("GMAPLIST_CACHE") or os.environ.get("XDG_CACHE_HOME")
    if not base and os.name == "nt":
        base = os.environ.get("LOCALAPPDATA")
    root = Path(base) if base else Path.home() / ".cache"
    return root / "gmaplist"


def _ring_bbox(ring: Sequence[Sequence[float]]) -> tuple[float, float, float, float]:
    xs = [p[0] for p in ring]
    ys = [p[1] for p in ring]
    return min(xs), min(ys), max(xs), max(ys)


def _dist2_to_segment(  # noqa: PLR0917 - six scalars beats boxing points
    px: float, py: float, ax: float, ay: float, bx: float, by: float
) -> float:
    """Squared distance from a point to a segment, in degrees."""
    dx, dy = bx - ax, by - ay
    if dx == 0.0 and dy == 0.0:
        return (px - ax) ** 2 + (py - ay) ** 2
    t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
    t = 0.0 if t < 0.0 else (min(t, 1.0))
    return (px - (ax + t * dx)) ** 2 + (py - (ay + t * dy)) ** 2


def _dist2_to_ring(px: float, py: float, ring: Sequence[Sequence[float]]) -> float:
    best = float("inf")
    ax, ay = ring[-1][0], ring[-1][1]
    for pt in ring:
        bx, by = pt[0], pt[1]
        d = _dist2_to_segment(px, py, ax, ay, bx, by)
        best = min(best, d)
        ax, ay = bx, by
    return best


def _point_in_ring(x: float, y: float, ring: Sequence[Sequence[float]]) -> bool:
    """Standard ray-casting test."""
    inside = False
    jx, jy = ring[-1][0], ring[-1][1]
    for pt in ring:
        ix, iy = pt[0], pt[1]
        if (iy > y) != (jy > y) and x < (jx - ix) * (y - iy) / (jy - iy) + ix:
            inside = not inside
        jx, jy = ix, iy
    return inside


class PrefectureIndex:
    """Point-in-polygon lookup over prefecture outlines."""

    def __init__(self, geojson: dict):
        self._prefs: list[tuple[str, list]] = []
        for feature in geojson.get("features", []):
            name = feature.get("properties", {}).get("nam_ja")
            geom = feature.get("geometry") or {}
            coords = geom.get("coordinates") or []
            polygons = coords if geom.get("type") == "MultiPolygon" else [coords]
            rings = []
            for poly in polygons:
                if not poly or not poly[0]:
                    continue
                outer = poly[0]
                rings.append((*_ring_bbox(outer), outer))
            if name and rings:
                self._prefs.append((name, rings))

    @classmethod
    def load(cls, refresh: bool = False, timeout: float = 60.0) -> PrefectureIndex:
        path = cache_dir() / "japan.geojson"
        if refresh or not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            with urllib.request.urlopen(GEOJSON_URL, timeout=timeout) as res:
                path.write_bytes(res.read())
        return cls(json.loads(path.read_text(encoding="utf-8")))

    def contains(self, lat: float, lng: float) -> str | None:
        for name, rings in self._prefs:
            for x0, y0, x1, y1, ring in rings:
                if (
                    x0 <= lng <= x1
                    and y0 <= lat <= y1
                    and _point_in_ring(lng, lat, ring)
                ):
                    return name
        return None

    def nearest(self, lat: float, lng: float, max_deg: float = 0.15) -> str | None:
        """Nearest prefecture outline, for points just off the coastline.

        Distance is measured to the boundary segments, not just to vertices:
        coastlines are densely sampled but administrative outlines inland are
        not, and a vertex-only test misses those.
        """
        best_d, best = max_deg * max_deg, None
        for name, rings in self._prefs:
            for x0, y0, x1, y1, ring in rings:
                if not (
                    x0 - max_deg <= lng <= x1 + max_deg
                    and y0 - max_deg <= lat <= y1 + max_deg
                ):
                    continue
                d = _dist2_to_ring(lng, lat, ring)
                if d < best_d:
                    best_d, best = d, name
        return best

    def resolve(self, lat: float | None, lng: float | None) -> tuple[str | None, str]:
        """Return ``(prefecture, source)`` where source explains the match."""
        if lat is None or lng is None:
            return None, "none"
        hit = self.contains(lat, lng)
        if hit:
            return hit, "polygon"
        hit = self.nearest(lat, lng)
        if hit:
            return hit, "nearest"
        return None, "none"


def annotate(places: Iterable, index: PrefectureIndex | None) -> list[dict]:
    """Attach prefecture, city and block to each place.

    ``source`` records how the prefecture was determined, so callers can tell a
    Google-supplied address from an inferred one. Places outside Japan carry a
    ``country`` instead of a prefecture, and their block is that country.
    """
    out = []
    for place in places:
        pref = prefecture_from_address(place.address)
        source = "address" if pref else "none"
        if not pref and index is not None:
            pref, source = index.resolve(place.lat, place.lng)
        country = "" if pref else country_from_address(place.address)
        out.append(
            {
                "place": place,
                "prefecture": pref,
                "prefecture_source": source,
                "city": city_from_address(place.address),
                "country": country,
                "block": BLOCKS.get(pref or "", "") if pref else (country or "abroad"),
            }
        )
    return out
