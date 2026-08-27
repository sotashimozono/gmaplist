"""Fetch Google Maps shared-list payloads over plain HTTP.

The list contents come from an undocumented endpoint,
``/maps/preview/entitylist/getlist``. It needs no browser, no cookies and no
API key: the only required input is the list id, carried in the ``pb``
parameter. Everything else in ``pb`` is constant.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request

ENDPOINT = "https://www.google.com/maps/preview/entitylist/getlist"

# Matches the id in every URL shape Google hands out for a list:
#   .../maps/@/data=...!11m2!2s<ID>!3e3
#   .../maps/placelists/list/<ID>
_LIST_ID_RE = re.compile(r"(?:!2s|/list/)([A-Za-z0-9_-]{16,})")
_BARE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{16,}$")

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0 Safari/537.36"
)

# Google caps a saved list at a few hundred places; ask for more than that and
# compare against the server-reported total to detect truncation.
DEFAULT_PAGE_SIZE = 2000


class ListFetchError(RuntimeError):
    """Raised when a list cannot be located or decoded."""


def _http_get(url: str, timeout: float = 30.0) -> tuple[str, str]:
    req = urllib.request.Request(
        url, headers={"User-Agent": _UA, "Accept-Language": "ja,en;q=0.8"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as res:
        return res.read().decode("utf-8", "replace"), res.geturl()


def resolve_list_id(source: str, timeout: float = 30.0) -> str:
    """Turn a share link, a canonical list URL or a bare id into a list id.

    ``maps.app.goo.gl`` short links are followed; urllib handles the redirect,
    so the final URL is read back off the response.
    """
    source = source.strip()
    if _BARE_ID_RE.match(source):
        return source

    m = _LIST_ID_RE.search(source)
    if m:
        return m.group(1)

    if not source.startswith(("http://", "https://")):
        raise ListFetchError(f"not a list URL or id: {source!r}")

    try:
        _, final_url = _http_get(source, timeout)
    except (urllib.error.URLError, TimeoutError) as exc:
        raise ListFetchError(f"could not follow {source}: {exc}") from exc
    m = _LIST_ID_RE.search(final_url)
    if not m:
        raise ListFetchError(f"no list id in resolved URL: {final_url}")
    return m.group(1)


def build_url(
    list_id: str, hl: str = "ja", gl: str = "jp", page_size: int = DEFAULT_PAGE_SIZE
) -> str:
    pb = f"!1m4!1s{list_id}!2e1!3m1!1e1!2e2!3e2!4i{page_size}"
    return f"{ENDPOINT}?authuser=0&hl={hl}&gl={gl}&pb={pb}"


def fetch_raw(
    list_id: str,
    hl: str = "ja",
    gl: str = "jp",
    page_size: int = DEFAULT_PAGE_SIZE,
    timeout: float = 30.0,
) -> list:
    """Return the decoded JSON body of the getlist response.

    The body is prefixed with an anti-JSON-hijacking guard line that is
    stripped before parsing.
    """
    body, _ = _http_get(build_url(list_id, hl, gl, page_size), timeout)
    if body.startswith(")]}'"):
        body = body[body.index("\n") + 1 :]
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise ListFetchError(f"unparsable getlist response for {list_id}") from exc
