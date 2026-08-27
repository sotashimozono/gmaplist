"""Aggregation tests."""

import datetime as dt
import unittest

from gmaplist import analyze, geo
from gmaplist.model import Author, Place

UTC = dt.timezone.utc
ALICE = Author("Alice", "1")
BOB = Author("Bob", "2")


def row(name, pref, author, day, note=""):
    place = Place(
        name=name,
        note=note,
        address="",
        lat=None,
        lng=None,
        place_id=name,
        added_by=author,
        added_at=dt.datetime(2026, 8, day, 20, 0, tzinfo=UTC),
    )
    return {
        "place": place,
        "prefecture": pref,
        "prefecture_source": "address",
        "city": "",
        "block": geo.BLOCKS.get(pref, "abroad"),
    }


ROWS = [
    row("a", "鹿児島県", ALICE, 26, "x" * 10),
    row("b", "鹿児島県", ALICE, 26),
    row("c", "東京都", ALICE, 27, "x" * 30),
    row("d", "大阪府", BOB, 26, "x" * 100),
]


class TestAggregations(unittest.TestCase):
    def test_by_contributor_orders_by_count(self):
        stats = analyze.by_contributor(ROWS)
        self.assertEqual([s["name"] for s in stats], ["Alice", "Bob"])
        alice = stats[0]
        self.assertEqual(alice["count"], 3)
        self.assertAlmostEqual(alice["share"], 0.75)
        self.assertEqual(alice["with_note"], 2)
        # averaged over notes that exist, not over all entries
        self.assertAlmostEqual(alice["avg_note_chars"], 20.0)
        self.assertEqual(alice["top_regions"][0], ("鹿児島県", 2))

    def test_contributor_activity_span(self):
        alice = analyze.by_contributor(ROWS)[0]
        self.assertEqual(alice["first_added"].day, 26)
        self.assertEqual(alice["last_added"].day, 27)

    def test_by_prefecture_and_block(self):
        self.assertEqual(analyze.by_prefecture(ROWS)[0], ("鹿児島県", 2))
        self.assertEqual(
            dict(analyze.by_block(ROWS)), {"九州": 2, "関東": 1, "近畿": 1}
        )

    def test_timeline_uses_the_given_offset(self):
        # 20:00 UTC on the 26th is 05:00 JST on the 27th
        self.assertEqual(
            analyze.timeline(ROWS, "day", 9.0), [("2026-08-27", 3), ("2026-08-28", 1)]
        )
        self.assertEqual(
            analyze.timeline(ROWS, "day", 0.0), [("2026-08-26", 3), ("2026-08-27", 1)]
        )

    def test_crosstab(self):
        people, _blocks, cells = analyze.crosstab(ROWS)
        self.assertEqual(people, ["Alice", "Bob"])
        self.assertEqual(cells[("Alice", "九州")], 2)
        self.assertEqual(cells.get(("Bob", "九州"), 0), 0)

    def test_duplicates(self):
        self.assertEqual(analyze.duplicates(ROWS), [])
        self.assertEqual(analyze.duplicates([*ROWS, ROWS[0]]), [("a", 2)])

    def test_unknown_author(self):
        anon = row("e", "東京都", None, 26)
        stats = analyze.by_contributor([anon])
        self.assertEqual(stats[0]["name"], analyze.UNKNOWN)
