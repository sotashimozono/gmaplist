"""Read and analyse Google Maps shared place lists.

Google exposes no official API for saved lists, and Takeout drops the fields
that make a collaborative list interesting: who added each place and when.
This package reads the same undocumented endpoint the Maps web client uses, so
those fields survive.

    import gmaplist
    plist, rows = gmaplist.load("https://maps.app.goo.gl/xxxxxxxx")
"""

from __future__ import annotations

import time
import urllib.error

from .fetch import ListFetchError, fetch_raw, resolve_list_id
from .geo import PrefectureIndex, annotate
from .model import Author, Place, PlaceList

__all__ = [
    "Author",
    "ListFetchError",
    "Place",
    "PlaceList",
    "PrefectureIndex",
    "annotate",
    "fetch_raw",
    "load",
    "resolve_list_id",
]

__version__ = "0.1.0"


def load(
    source: str,
    hl: str = "ja",
    gl: str = "jp",
    geo: bool = True,
    refresh_geo: bool = False,
    retries: int = 2,
):
    """Fetch a list and annotate every place with its prefecture.

    ``source`` may be a share link, a canonical list URL or a bare list id.
    Returns ``(PlaceList, rows)`` where each row pairs a ``Place`` with its
    resolved region.

    The endpoint intermittently answers with an undecodable payload, so the
    fetch is retried before giving up.
    """
    list_id = resolve_list_id(source)
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            plist = PlaceList._parse(fetch_raw(list_id, hl=hl, gl=gl))
            break
        except (ValueError, urllib.error.URLError, TimeoutError) as exc:
            last = exc
            if attempt < retries:
                time.sleep(1.0 + attempt)
    else:
        raise ListFetchError(f"could not read list {list_id}: {last}") from last

    index = PrefectureIndex.load(refresh=refresh_geo) if geo else None
    return plist, annotate(plist.places, index)
