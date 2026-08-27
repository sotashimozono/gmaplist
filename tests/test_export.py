"""Serialisation. Every file is written to a temporary directory and read back."""

import csv
import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

from gmaplist import export
from gmaplist.model import Author, Place, PlaceList

UTC = dt.timezone.utc


def row(name, *, lat=1.0, lng=0.0, note="", note_by=None, country="", pref="東京都"):
    place = Place(
        name=name,
        note=note,
        address="",
        lat=lat,
        lng=lng,
        place_id=name,
        added_by=Author("Alice", "alice-id"),
        note_author=Author(note_by, note_by + "-id") if note_by else None,
        added_at=dt.datetime(2026, 1, 2, 0, 0, tzinfo=UTC),
    )
    return {
        "place": place,
        "prefecture": pref,
        "prefecture_source": "address",
        "city": "",
        "country": country,
        "block": "関東" if pref else country,
    }


class TestRecords(unittest.TestCase):
    def test_note_by_is_the_note_author(self):
        rec = export.to_records([row("a", note="hi", note_by="Bob")])[0]
        self.assertEqual(rec["added_by"], "Alice")
        self.assertEqual(rec["note_by"], "Bob")

    def test_note_by_is_blank_when_there_is_no_note(self):
        self.assertEqual(export.to_records([row("a")])[0]["note_by"], "")

    def test_country_is_carried_through(self):
        rec = export.to_records([row("a", country="ドイツ", pref=None)])[0]
        self.assertEqual(rec["country"], "ドイツ")

    def test_timestamps_honour_the_offset(self):
        recs = export.to_records([row("a")], tz_offset_hours=9.0)
        self.assertEqual(recs[0]["added_at"], "2026-01-02T09:00:00+09:00")
        recs = export.to_records([row("a")], tz_offset_hours=0.0)
        self.assertEqual(recs[0]["added_at"], "2026-01-02T00:00:00+00:00")

    def test_distance_only_appears_with_an_anchor(self):
        self.assertNotIn("distance_km", export.to_records([row("a")])[0])
        rec = export.to_records([row("a")], anchor=(0.0, 0.0))[0]
        self.assertGreater(rec["distance_km"], 111.0)

    def test_unlocated_row_gets_a_blank_distance(self):
        rec = export.to_records([row("a", lat=None, lng=None)], anchor=(0.0, 0.0))[0]
        self.assertEqual(rec["distance_km"], "")


class TestWriters(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.rows = [row("a", note="hi", note_by="Bob"), row("b")]
        self.plist = PlaceList(list_id="LISTID0123456789ab", title="T")

    def test_csv_round_trips(self):
        path = self.dir / "out.csv"
        export.write_csv(path, self.rows)
        with open(path, encoding="utf-8-sig", newline="") as fh:
            got = list(csv.DictReader(fh))
        self.assertEqual([r["name"] for r in got], ["a", "b"])
        self.assertEqual(got[0]["note_by"], "Bob")
        self.assertNotIn("distance_km", got[0])

    def test_csv_with_anchor_declares_the_extra_column(self):
        # DictWriter raises if a record carries a key the header does not.
        path = self.dir / "anchored.csv"
        export.write_csv(path, self.rows, anchor=(0.0, 0.0))
        with open(path, encoding="utf-8-sig", newline="") as fh:
            got = list(csv.DictReader(fh))
        self.assertIn("distance_km", got[0])
        self.assertGreater(float(got[0]["distance_km"]), 111.0)

    def test_json_carries_list_metadata(self):
        path = self.dir / "out.json"
        export.write_json(path, self.plist, self.rows)
        payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(payload["list_id"], "LISTID0123456789ab")
        self.assertEqual(payload["count"], 2)
        self.assertEqual(len(payload["places"]), 2)

    def test_geojson_drops_unlocated_places(self):
        path = self.dir / "out.geojson"
        export.write_geojson(path, [*self.rows, row("c", lat=None, lng=None)])
        payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(payload["type"], "FeatureCollection")
        self.assertEqual(len(payload["features"]), 2)
        # GeoJSON is lng, lat - the opposite order from everywhere else here.
        self.assertEqual(payload["features"][0]["geometry"]["coordinates"], [0.0, 1.0])


if __name__ == "__main__":
    unittest.main()
