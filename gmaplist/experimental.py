"""Experimental: place categories, from a second undocumented endpoint.

The saved-list payload carries no category, so a list tells you *where* people
went but not *what kind of place* it was. Categories come from the Maps search
endpoint instead, queried by the feature ids the list already gives us.

    from gmaplist import experimental

    details = experimental.fetch_details([r["place"].place_id for r in rows])
    experimental.attach(rows, details)

**This module is experimental and the rest of the package does not depend on
it.** It reads a different endpoint from `gmaplist.fetch`, with its own way of
breaking, and `genre_of` applies opinionated Japanese-language rules on top.
Expect it to need maintenance sooner than the rest.

Two limits worth knowing before relying on the output:

* Not every place has a category. Streets, villages and other non-business
  entries come back with none, and Google occasionally files a place under
  something odd.
* ``review_count`` is usually absent. The endpoint only fills it in for a
  browser session with cookies; over plain HTTP it comes back for a minority
  of places, and *which* minority is a property of the request rather than of
  the places. Do not compute statistics over it without checking coverage.
"""

from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field

SEARCH_ENDPOINT = "https://www.google.com/search"

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0 Safari/537.36"
)

# The endpoint answers a bare list of feature ids; the only parameter that
# matters is the page size, which otherwise defaults to 20 and silently
# truncates the reply.
DEFAULT_BATCH = 100


class CategoryFetchError(RuntimeError):
    """The search endpoint could not be read."""


@dataclass(frozen=True)
class PlaceDetail:
    """What the search endpoint knows about one place."""

    place_id: str
    name: str = ""
    categories: tuple[str, ...] = ()
    rating: float | None = None
    review_count: int | None = None

    @property
    def primary_category(self) -> str:
        return self.categories[0] if self.categories else ""


def _at(node, *path):
    for i in path:
        if not isinstance(node, list) or len(node) <= i:
            return None
        node = node[i]
    return node


def build_search_url(place_ids: Sequence[str], hl: str = "ja", gl: str = "jp") -> str:
    """URL that asks for exactly these places."""
    body = "".join(f"!72m2!1m1!1s{pid}" for pid in place_ids)
    pb = f"!7i{max(len(place_ids), 1)}{body}!77b1"
    query = urllib.parse.quote(pb, safe="!*")
    return f"{SEARCH_ENDPOINT}?tbm=map&hl={hl}&gl={gl}&pb={query}&q=*&tch=1&ech=1"


def _http_get(url: str, timeout: float = 60.0) -> str:
    req = urllib.request.Request(
        url, headers={"User-Agent": _UA, "Accept-Language": "ja,en;q=0.8"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as res:
        return res.read().decode("utf-8", "replace")


def parse_response(body: str) -> list[PlaceDetail]:
    """Decode a search response into details.

    The body is a sequence of JSON envelopes separated by a comment marker,
    whose ``d`` fields concatenate into one guarded JSON document.
    """
    chunks = [part for part in body.split('/*""*/') if part.strip()]
    if not chunks:
        raise CategoryFetchError("empty search response")
    try:
        payload = "".join(json.loads(part).get("d", "") for part in chunks)
        payload = payload[payload.index("\n") + 1 :]
        decoded = json.loads(payload)
    except (json.JSONDecodeError, ValueError) as exc:
        raise CategoryFetchError("unparsable search response") from exc

    out = []
    for entry in _at(decoded, 0, 1) or []:
        place_id = _at(entry, 14, 10)
        if not place_id:
            continue
        categories = _at(entry, 14, 13) or []
        rating = _at(entry, 14, 4, 7)
        reviews = _at(entry, 14, 4, 8)
        out.append(
            PlaceDetail(
                place_id=place_id,
                name=_at(entry, 14, 11) or "",
                categories=tuple(categories),
                rating=float(rating) if rating is not None else None,
                review_count=int(reviews) if reviews is not None else None,
            )
        )
    return out


def fetch_details(
    place_ids: Iterable[str],
    *,
    hl: str = "ja",
    gl: str = "jp",
    batch_size: int = DEFAULT_BATCH,
    delay: float = 1.0,
    transport: Callable[[str], str] | None = None,
) -> dict[str, PlaceDetail]:
    """Look up every place id, in batches, keyed by place id.

    ``transport`` takes a URL and returns a body; it exists so callers can
    supply a cache or a recorded fixture instead of live requests.
    """
    get = transport or _http_get
    wanted = [pid for pid in place_ids if pid]
    out: dict[str, PlaceDetail] = {}
    for start in range(0, len(wanted), batch_size):
        chunk = wanted[start : start + batch_size]
        for detail in parse_response(get(build_search_url(chunk, hl, gl))):
            out[detail.place_id] = detail
        if delay and start + batch_size < len(wanted):
            time.sleep(delay)
    return out


# --------------------------------------------------------------------------
# Rolling ~100 distinct Google categories up into something countable.
# --------------------------------------------------------------------------

# Ordered; the first rule with a keyword occurring in any of a place's
# categories wins. Matched against the category strings only, never the name,
# so the classification stays auditable against what Google actually said.
DEFAULT_GENRE_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "宿泊・温泉",
        (
            "旅館",
            "ホテル",
            "温泉",
            "銭湯",
            "浴場",
            "民宿",
            "キャンプ",
            "足湯",
            "露天風呂",
        ),
    ),
    (
        "文化施設",
        (
            "博物館",
            "美術館",
            "水族館",
            "動物園",
            "記念館",
            "資料館",
            "科学館",
            "展示",
            "ギャラリー",
        ),
    ),
    (
        "観光・自然",
        (
            "観光名所",
            "公園",
            "庭園",
            "史跡",
            "神社",
            "寺",
            "城",
            "橋",
            "峠",
            "滝",
            "山",
            "展望",
            "海岸",
            "ビーチ",
            "灯台",
            "名所",
            "遺跡",
            "天文台",
            "牧場",
            "農園",
            "島",
        ),
    ),
    ("酒造・醸造", ("醸造", "酒蔵", "蒸留")),
    (
        "カフェ・甘味",
        (
            "カフェ",
            "喫茶",
            "デザート",
            "スイーツ",
            "和菓子",
            "ケーキ",
            "アイス",
            "パン屋",
            "ベーカリー",
            "ジェラート",
        ),
    ),
    (
        "飲食店",
        (
            "レストラン",
            "ラーメン",
            "カレー",
            "居酒屋",
            "定食",
            "和食",
            "洋食",
            "焼肉",
            "蕎麦",
            "そば",
            "うどん",
            "たこ焼き",
            "麺",
            "料理",
            "食堂",
            "丼",
            "寿司",
            "焼鳥",
            "唐揚",
            "バー",
            "ビアホール",
            "パブ",
            "総菜",
            "弁当",
            "テイクアウト",
            "飲食",
            "うなぎ",
            "天ぷら",
            "餃子",
            "フードコート",
        ),
    ),
    (
        "買い物",
        (
            "スーパーマーケット",
            "土産",
            "商店",
            "市場",
            "書店",
            "ショップ",
            "ストア",
            "販売",
            "百貨店",
            "直売",
            "デパート",
            "酒店",
            "工芸品",
            "陶磁器",
            "卸売",
            "商業地",
        ),
    ),
    ("交通・道の駅", ("サービスエリア", "パーキング", "道の駅", "空港")),
)

UNCLASSIFIED = "その他・未分類"


def genre_of(categories: Sequence[str], rules=DEFAULT_GENRE_RULES) -> str:
    """Bucket a place by its categories.

    A heuristic over Japanese category names, not a Google-provided taxonomy.
    Pass your own ``rules`` for another language or another set of buckets.
    Anything unmatched lands in ``UNCLASSIFIED`` rather than being forced into
    the nearest bucket, so the residue stays visible.
    """
    for name, keywords in rules:
        for category in categories:
            if any(keyword in category for keyword in keywords):
                return name
    return UNCLASSIFIED


@dataclass
class Enrichment:
    """What ``attach`` added, and what it could not."""

    matched: int = 0
    missing: list[str] = field(default_factory=list)
    without_category: list[str] = field(default_factory=list)
    with_review_count: int = 0

    @property
    def review_coverage(self) -> float:
        return self.with_review_count / self.matched if self.matched else 0.0


def attach(
    rows: Sequence[dict],
    details: dict[str, PlaceDetail],
    rules=DEFAULT_GENRE_RULES,
) -> Enrichment:
    """Add ``detail``, ``categories`` and ``genre`` to each row, in place.

    Returns what was and was not covered. Callers should look at it: a genre
    breakdown computed over partial data reads as complete unless the gaps are
    stated.
    """
    report = Enrichment()
    for row in rows:
        place = row["place"]
        detail = details.get(place.place_id)
        row["detail"] = detail
        row["categories"] = list(detail.categories) if detail else []
        row["genre"] = genre_of(row["categories"], rules)
        if detail is None:
            report.missing.append(place.name)
            continue
        report.matched += 1
        if not detail.categories:
            report.without_category.append(place.name)
        if detail.review_count is not None:
            report.with_review_count += 1
    return report


def by_genre(rows: Sequence[dict]) -> list[tuple[str, int]]:
    return Counter(row.get("genre", UNCLASSIFIED) for row in rows).most_common()


def by_category(
    rows: Sequence[dict], limit: int | None = None
) -> list[tuple[str, int]]:
    """Primary categories, ungrouped, for auditing the rules above."""
    counts = Counter(row["categories"][0] for row in rows if row.get("categories"))
    return counts.most_common(limit)


def genre_crosstab(
    rows: Sequence[dict],
) -> tuple[list[str], list[str], dict[tuple[str, str], int]]:
    """Contributor x genre, both axes ordered by descending totals."""
    genres = [g for g, _ in by_genre(rows)]
    per_person: dict[str, int] = defaultdict(int)
    cells: Counter = Counter()
    for row in rows:
        by = row["place"].added_by
        name = by.name if by else "(unknown)"
        per_person[name] += 1
        cells[(name, row.get("genre", UNCLASSIFIED))] += 1
    people = sorted(per_person, key=lambda n: (-per_person[n], n))
    return people, genres, dict(cells)
