#!/usr/bin/env python3
"""Fail unless the project version moved forward.

Used by the `version-check` job, which is a required check: a PR that changes
anything has to say so in `pyproject.toml`. Runnable locally too:

    python scripts/version_bump_check.py base-pyproject.toml pyproject.toml

Deliberately dependency-free, and deliberately not using ``tomllib``: this
has to run on 3.10, where that module does not exist. Only one key is needed,
so it is scanned for directly.

Versions here are plain `X.Y.Z`, optionally with a `-label.N` prerelease
suffix; anything outside that is rejected loudly rather than being put in
the wrong order silently.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_VERSION_RE = re.compile(
    r"^(?P<release>\d+(?:\.\d+)*)(?:-(?P<label>[A-Za-z]+)\.(?P<serial>\d+))?$"
)


class VersionError(ValueError):
    """The version string is not in a shape this checker can order."""


_TABLE_RE = re.compile(r"^\s*\[([^\]]+)\]\s*$")
_VERSION_KEY_RE = re.compile(r"""^\s*version\s*=\s*["'](?P<value>[^"']+)["']""")


def extract_version(text: str) -> str:
    """Read `version` from the `[project]` table of a pyproject document.

    Table-scoped on purpose: `[tool.*]` tables carry their own `version` keys,
    and picking the first one in the file would silently compare the wrong
    thing.
    """
    in_project = False
    for line in text.splitlines():
        table = _TABLE_RE.match(line)
        if table:
            in_project = table.group(1).strip() == "project"
            continue
        if in_project:
            m = _VERSION_KEY_RE.match(line)
            if m:
                return m.group("value")
    raise VersionError("no [project].version found")


def read_version(path: str | Path) -> str:
    try:
        return extract_version(Path(path).read_text(encoding="utf-8"))
    except VersionError as exc:
        raise VersionError(f"no [project].version in {path}") from exc


def sort_key(version: str) -> tuple:
    """Order versions, with a prerelease sorting below its own release."""
    m = _VERSION_RE.match(version.strip())
    if not m:
        raise VersionError(f"unsupported version string: {version!r}")
    release = tuple(int(part) for part in m.group("release").split("."))
    if m.group("label") is None:
        # A final release outranks every prerelease of the same number.
        return (release, 1, "", 0)
    return (release, 0, m.group("label").lower(), int(m.group("serial")))


def is_bumped(base: str, head: str) -> bool:
    return sort_key(head) > sort_key(base)


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    base, head = read_version(argv[1]), read_version(argv[2])
    if is_bumped(base, head):
        print(f"version-check: {base} -> {head}")
        return 0
    print(
        f"version-check: version did not move forward ({base} -> {head}).\n"
        f"Bump [project].version in pyproject.toml.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
