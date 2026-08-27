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


class TestNoteAttribution(unittest.TestCase):
    """Notes belong to their own author, not to whoever added the place."""

    @staticmethod
    def _row(place_name, added_by, note, note_by):
        place = Place(
            name=place_name,
            note=note,
            place_id=place_name,
            added_by=Author(added_by, added_by),
            note_author=Author(note_by, note_by) if note_by else None,
        )
        return {
            "place": place,
            "prefecture": "東京都",
            "prefecture_source": "address",
            "city": "",
            "country": "",
            "block": "関東",
        }

    def setUp(self):
        self.rows = [
            self._row("a", "Alice", "x" * 10, "Alice"),
            self._row("b", "Alice", "x" * 20, "Bob"),
            self._row("c", "Bob", "", None),
        ]

    def test_notes_are_credited_to_their_writer(self):
        stats = {s["name"]: s for s in analyze.by_contributor(self.rows)}
        self.assertEqual(stats["Alice"]["count"], 2)
        self.assertEqual(stats["Alice"]["notes_written"], 1)
        self.assertEqual(stats["Bob"]["count"], 1)
        self.assertEqual(stats["Bob"]["notes_written"], 1)

    def test_with_note_still_counts_annotated_entries(self):
        stats = {s["name"]: s for s in analyze.by_contributor(self.rows)}
        # Both of Alice's entries carry a note, even though she wrote one.
        self.assertEqual(stats["Alice"]["with_note"], 2)
        self.assertEqual(stats["Bob"]["with_note"], 0)

    def test_average_length_uses_only_notes_the_person_wrote(self):
        stats = {s["name"]: s for s in analyze.by_contributor(self.rows)}
        self.assertAlmostEqual(stats["Alice"]["avg_note_chars"], 10.0)
        self.assertAlmostEqual(stats["Bob"]["avg_note_chars"], 20.0)

    def test_cross_author_notes_finds_the_collaboration(self):
        crossed = analyze.cross_author_notes(self.rows)
        self.assertEqual(len(crossed), 1)
        self.assertEqual(crossed[0]["name"], "b")
        self.assertEqual(crossed[0]["added_by"], "Alice")
        self.assertEqual(crossed[0]["note_by"], "Bob")

    def test_no_cross_author_notes_when_everyone_annotates_their_own(self):
        rows = [self._row("a", "Alice", "note", "Alice")]
        self.assertEqual(analyze.cross_author_notes(rows), [])

    def test_missing_note_author_falls_back_to_the_entry_author(self):
        rows = [self._row("a", "Alice", "note", None)]
        stats = {s["name"]: s for s in analyze.by_contributor(rows)}
        self.assertEqual(stats["Alice"]["notes_written"], 1)
        self.assertEqual(analyze.cross_author_notes(rows), [])

    def test_someone_who_only_wrote_notes_still_appears(self):
        rows = [self._row("a", "Alice", "note", "Carol")]
        stats = {s["name"]: s for s in analyze.by_contributor(rows)}
        self.assertIn("Carol", stats)
        self.assertEqual(stats["Carol"]["count"], 0)
        self.assertEqual(stats["Carol"]["notes_written"], 1)
