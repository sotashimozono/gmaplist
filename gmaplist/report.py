"""Fixed-width text report.

Widths are measured with east-asian width so CJK names line up in a terminal.
"""

from __future__ import annotations

import datetime as _dt
import unicodedata
from collections import Counter
from typing import Sequence

from . import analyze


def width(text: str) -> int:
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in text)


def pad(text: str, n: int, align: str = "<") -> str:
    fill = " " * max(0, n - width(text))
    return text + fill if align == "<" else fill + text


def _stamp(value: _dt.datetime | None, tz: _dt.timezone, fmt: str = "%Y-%m-%d %H:%M") -> str:
    return value.astimezone(tz).strftime(fmt) if value else "-"


def render(plist, rows: Sequence[dict], tz_offset_hours: float = 9.0, bar_unit: int = 2) -> str:
    tz = _dt.timezone(_dt.timedelta(hours=tz_offset_hours))
    out: list[str] = []
    add = out.append

    add(f"# {plist.title or plist.list_id}")
    owner = plist.owner.name if plist.owner else "-"
    add(f"owner: {owner}   places: {len(rows)}   url: {plist.url}")
    add(f"created: {_stamp(plist.created_at, tz)}   updated: {_stamp(plist.updated_at, tz)}")
    if plist.description:
        add(f"description: {plist.description}")
    if plist.truncated:
        add(f"WARNING: Google reports {plist.reported_count} places but returned {len(rows)}.")

    contributors = analyze.by_contributor(rows)
    add("")
    add("## contributors")
    name_w = max([width(c["name"]) for c in contributors] + [4])
    add(
        f"{pad('count', 6, '>')}  {pad('share', 6, '>')}  {pad('name', name_w)}  "
        f"{pad('notes', 7, '>')}  {pad('avg', 6, '>')}  top regions"
    )
    for c in contributors:
        regions = " / ".join("{}{}".format(r, n) for r, n in c["top_regions"])
        share = "{:.1f}%".format(c["share"] * 100)
        notes = "{}/{}".format(c["with_note"], c["count"])
        avg = "{:.0f}".format(c["avg_note_chars"])
        add(
            pad(str(c["count"]), 6, ">") + "  " + pad(share, 6, ">") + "  "
            + pad(c["name"], name_w) + "  " + pad(notes, 7, ">") + "  "
            + pad(avg, 6, ">") + "  " + regions
        )

    add("")
    add("## prefectures")
    prefs = analyze.by_prefecture(rows)
    pref_w = max([width(p) for p, _ in prefs] + [4])
    for pref, n in prefs:
        add(f"{pad(str(n), 5, '>')}  {pad(pref, pref_w)}  {'#' * round(n / bar_unit)}")

    add("")
    add("## regions")
    total = len(rows) or 1
    blocks = analyze.by_block(rows)
    block_w = max([width(b) for b, _ in blocks] + [4])
    for block, n in blocks:
        share = "{:.1f}%".format(n / total * 100)
        add(pad(str(n), 5, ">") + "  " + pad(share, 6, ">") + "  " + pad(block, block_w))

    add("")
    add("## additions per day")
    for day, n in analyze.timeline(rows, "day", tz_offset_hours):
        add(f"{pad(str(n), 5, '>')}  {day}  {'#' * round(n / bar_unit)}")

    people, block_names, cells = analyze.crosstab(rows)
    add("")
    add("## contributor x region")
    col_w = max([width(b) for b in block_names] + [3]) + 1
    head = pad("", name_w) + "".join(pad(b, col_w, ">") for b in block_names)
    add(head)
    for person in people:
        line = pad(person, name_w)
        for block in block_names:
            v = cells.get((person, block), 0)
            line += pad(str(v) if v else "", col_w, ">")
        add(line)

    dupes = analyze.duplicates(rows)
    if dupes:
        add("")
        add("## duplicates")
        for name, n in dupes:
            add(f"{pad(str(n), 5, '>')}  {name}")

    sources = Counter(r["prefecture_source"] for r in rows)
    add("")
    add("## prefecture source")
    add("   " + "  ".join(f"{k}={v}" for k, v in sources.most_common()))
    return "\n".join(out)
