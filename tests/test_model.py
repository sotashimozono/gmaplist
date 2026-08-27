"""Parsing tests against the real response layout."""

import datetime as dt
import unittest

from gmaplist.model import Author, Place, PlaceList

# One item shaped exactly like a getlist entry. Names and ids are synthetic.
# The two feature-id halves are a real pair taken from a public business
# listing: Google's own search endpoint renders them as
# 0x6018edf73ca54c3f:0xc0bdb6fbb0534c21, which is what the hex conversion
# below has to reproduce.
ITEM = [
    None,
    [
        None,
        None,
        "",
        None,
        "〒163-8001 東京都新宿区西新宿２丁目８−１",
        [None, None, 35.704868, 139.6223648],
        ["6924546073212308543", "-4558286055717778399"],
        "/g/11bwnydddk",
    ],
    "Test Restaurant",
    "line one\nline two",
    None,
    None,
    None,
    None,
    [[1], ["6924546073212308543", "-4558286055717778399"]],
    [1723682872, 157928000],
    [1787793162, 274472000],
    None,
    ["Tester", "https://example.invalid/avatar", "100000000000000000001"],
]

PAYLOAD = [
    [
        ["LISTID0123456789ab", 1, None, 1, 1],
        4,
        [3, 1, "https://www.google.com/maps/placelists/list/LISTID0123456789ab"],
        ["Owner Name", "https://example.invalid/owner", "100000000000000000002"],
        "Test List",
        "a description",
        None,
        None,
        [ITEM],
        None,
        [1723682872, 157928000],
        [1787793162, 274472000],
        7,
    ]
]


class TestPlace(unittest.TestCase):
    def setUp(self):
        self.place = Place._parse(ITEM)

    def test_scalar_fields(self):
        self.assertEqual(self.place.name, "Test Restaurant")
        self.assertEqual(self.place.note, "line one\nline two")
        self.assertEqual(self.place.address, "〒163-8001 東京都新宿区西新宿２丁目８−１")
        self.assertEqual(self.place.mid, "/g/11bwnydddk")
        self.assertAlmostEqual(self.place.lat, 35.704868)
        self.assertAlmostEqual(self.place.lng, 139.6223648)

    def test_place_id_matches_google_hex_form(self):
        self.assertEqual(self.place.place_id, "0x6018edf73ca54c3f:0xc0bdb6fbb0534c21")

    def test_author(self):
        self.assertEqual(
            self.place.added_by,
            Author("Tester", "100000000000000000001", "https://example.invalid/avatar"),
        )

    def test_timestamps_are_utc_aware(self):
        self.assertEqual(self.place.added_at.tzinfo, dt.timezone.utc)
        jst = dt.timezone(dt.timedelta(hours=9))
        self.assertEqual(
            self.place.added_at.astimezone(jst).strftime("%Y-%m-%d %H:%M"),
            "2024-08-15 09:47",
        )
        self.assertGreater(self.place.updated_at, self.place.added_at)

    def test_maps_url_prefers_place_id(self):
        self.assertIn("place_id:0x6018edf73ca54c3f", self.place.maps_url)


class TestPlaceList(unittest.TestCase):
    def setUp(self):
        self.plist = PlaceList._parse(PAYLOAD)

    def test_metadata(self):
        self.assertEqual(self.plist.list_id, "LISTID0123456789ab")
        self.assertEqual(self.plist.title, "Test List")
        self.assertEqual(self.plist.description, "a description")
        self.assertEqual(self.plist.owner.name, "Owner Name")
        self.assertEqual(len(self.plist), 1)

    def test_truncation_is_detected(self):
        # reported_count is 7 but only one item came back
        self.assertTrue(self.plist.truncated)

    def test_bad_payload_is_rejected(self):
        with self.assertRaises(ValueError):
            PlaceList._parse([None])

    def test_missing_optional_fields(self):
        bare = Place._parse([None, None, "Nameless"])
        self.assertEqual(bare.name, "Nameless")
        self.assertEqual(bare.note, "")
        self.assertIsNone(bare.added_by)
        self.assertIsNone(bare.added_at)
        self.assertEqual(bare.place_id, "")


if __name__ == "__main__":
    unittest.main()
