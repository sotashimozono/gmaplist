"""Fixed-width text report.

Widths are measured with east-asian width so CJK names line up in a terminal.
"""

from __future__ import annotations

import datetime as _dt
import unicodedata
from collections import Counter
from collections.abc import Sequence

from . import analyze, experimental


def width(text: str) -> int:
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in text)


def pad(text: str, n: int, align: str = "<") -> str:
    fill = " " * max(0, n - width(text))
    return text + fill if align == "<" else fill + text


def _stamp(
    value: _dt.datetime | None, tz: _dt.timezone, fmt: str = "%Y-%m-%d %H:%M"
) -> str:
    return value.astimezone(tz).strftime(fmt) if value else "-"


def render(
    plist,
    rows: Sequence[dict],
    tz_offset_hours: float = 9.0,
    bar_unit: int = 2,
    anchor: tuple[float, float] | None = None,
) -> str:
    """Render the text report.

    With ``anchor`` set, a "reach" section reports how far the list extends
    from that coordinate.
    """
    tz = _dt.timezone(_dt.timedelta(hours=tz_offset_hours))
    out: list[str] = []
    add = out.append

    add(f"# {plist.title or plist.list_id}")
    owner = plist.owner.name if plist.owner else "-"
    add(f"owner: {owner}   places: {len(rows)}   url: {plist.url}")
    add(
        "created: "
        + _stamp(plist.created_at, tz)
        + "   updated: "
        + _stamp(plist.updated_at, tz)
    )
    if plist.description:
        add(f"description: {plist.description}")
    if plist.truncated:
        add(
            f"WARNING: Google reports {plist.reported_count} places "
            f"but returned {len(rows)}."
        )

    contributors = analyze.by_contributor(rows)
    add("")
    add("## contributors")
    name_w = max([width(c["name"]) for c in contributors] + [4])
    add(
        f"{pad('count', 6, '>')}  {pad('share', 6, '>')}  {pad('name', name_w)}  "
        f"{pad('notes', 7, '>')}  {pad('wrote', 6, '>')}  {pad('avg', 6, '>')}  "
        "top regions"
    )
    for c in contributors:
        regions = " / ".join(f"{r}{n}" for r, n in c["top_regions"])
        share = "{:.1f}%".format(c["share"] * 100)
        notes = "{}/{}".format(c["with_note"], c["count"])
        avg = "{:.0f}".format(c["avg_note_chars"])
        add(
            pad(str(c["count"]), 6, ">")
            + "  "
            + pad(share, 6, ">")
            + "  "
            + pad(c["name"], name_w)
            + "  "
            + pad(notes, 7, ">")
            + "  "
            + pad(str(c["notes_written"]), 6, ">")
            + "  "
            + pad(avg, 6, ">")
            + "  "
            + regions
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
        share = f"{n / total * 100:.1f}%"
        add(
            pad(str(n), 5, ">") + "  " + pad(share, 6, ">") + "  " + pad(block, block_w)
        )

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

    if any("genre" in row for row in rows):
        add("")
        add("## genres (experimental)")
        genre_rows = experimental.by_genre(rows)
        genre_w = max([width(g) for g, _ in genre_rows] + [4])
        for genre, count in genre_rows:
            share = f"{count / total * 100:.1f}%"
            add(
                pad(str(count), 5, ">")
                + "  "
                + pad(share, 6, ">")
                + "  "
                + pad(genre, genre_w)
                + "  "
                + "#" * round(count / bar_unit)
            )
        uncategorised = [r["place"].name for r in rows if not r.get("categories")]
        if uncategorised:
            add(f"   without a Google category: {', '.join(uncategorised)}")

        people_g, genres, cells_g = experimental.genre_crosstab(rows)
        add("")
        add("## contributor x genre (experimental)")
        gcol = max([width(g) for g in genres] + [3]) + 1
        add(pad("", name_w) + "".join(pad(g, gcol, ">") for g in genres))
        for person in people_g:
            line = pad(person, name_w)
            for genre in genres:
                v = cells_g.get((person, genre), 0)
                line += pad(str(v) if v else "", gcol, ">")
            add(line)

    crossed = analyze.cross_author_notes(rows)
    if crossed:
        add("")
        add("## notes written on someone else's entry")
        for item in crossed:
            add(f"   {item['name']}")
            add(f"      added by {item['added_by']}, note by {item['note_by']}")

    if anchor is not None:
        summary = analyze.distance_summary(rows, anchor)
        add("")
        add(f"## reach from {anchor[0]:.5f}, {anchor[1]:.5f}")
        add(
            f"   median {summary['median_km']:.1f} km"
            f"   mean {summary['mean_km']:.1f} km"
            f"   ({summary['count']} located)"
        )
        for lo, hi, n in summary["bands"]:
            label = f"{lo:.0f}-{hi:.0f} km" if hi != float("inf") else f">{lo:.0f} km"
            share = n / summary["count"] * 100 if summary["count"] else 0.0
            add(
                f"{pad(str(n), 5, '>')}  {pad(f'{share:.1f}%', 6, '>')}  "
                f"{pad(label, 12)}{'#' * round(n / bar_unit)}"
            )
        nearest = " / ".join(f"{n} ({d:.1f} km)" for n, d in summary["nearest"])
        farthest = " / ".join(f"{n} ({d:.0f} km)" for n, d in summary["farthest"])
        add(f"   nearest:  {nearest}")
        add(f"   farthest: {farthest}")

        add("")
        add("## where each contributor clusters")
        geo_rows = analyze.contributor_geography(rows, anchor)
        add(
            pad("", name_w)
            + pad("n", 5, ">")
            + pad("centroid from anchor", 24, ">")
            + pad("own spread", 14, ">")
        )
        for g in geo_rows:
            add(
                pad(g["name"], name_w)
                + pad(str(g["count"]), 5, ">")
                + pad(f"{g['anchor_km']:.0f} km", 24, ">")
                + pad(f"{g['spread_km']:.0f} km", 14, ">")
            )

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
