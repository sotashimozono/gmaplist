"""Region resolution tests. No network: polygons are supplied inline."""

import unittest

from gmaplist import geo
from gmaplist.model import Place

# A unit square around (139.5, 35.5) standing in for a prefecture outline.
SQUARE = {
    "features": [
        {
            "properties": {"nam_ja": "東京都"},
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [
                        [139.0, 35.0],
                        [140.0, 35.0],
                        [140.0, 36.0],
                        [139.0, 36.0],
                        [139.0, 35.0],
                    ]
                ],
            },
        }
    ]
}


class TestAddressParsing(unittest.TestCase):
    def test_prefecture(self):
        self.assertEqual(
            geo.prefecture_from_address("〒163-8001 東京都新宿区西新宿２丁目"), "東京都"
        )
        self.assertEqual(
            geo.prefecture_from_address("〒545-0002 大阪府大阪市阿倍野区"), "大阪府"
        )
        self.assertEqual(
            geo.prefecture_from_address("〒604-8006 京都府京都市中京区"), "京都府"
        )
        self.assertIsNone(geo.prefecture_from_address(""))
        self.assertIsNone(geo.prefecture_from_address("10 Downing St, London"))

    def test_city(self):
        self.assertEqual(
            geo.city_from_address("〒163-8001 東京都新宿区西新宿２丁目"), "新宿区"
        )
        self.assertEqual(
            geo.city_from_address("〒545-0002 大阪府大阪市阿倍野区天王寺町南"), "大阪市"
        )
        self.assertEqual(geo.city_from_address("no prefecture here"), "")

    def test_blocks_cover_every_prefecture(self):
        self.assertEqual(len(geo.PREFECTURES), 47)
        self.assertEqual(set(geo.BLOCKS), set(geo.PREFECTURES))
        self.assertEqual(geo.BLOCKS["鹿児島県"], "九州")
        self.assertEqual(geo.BLOCKS["東京都"], "関東")
        self.assertEqual(geo.BLOCKS["岡山県"], "中国")
        self.assertEqual(geo.BLOCKS["北海道"], "北海道")
        self.assertEqual(geo.BLOCKS["沖縄県"], "九州")


class TestPolygonLookup(unittest.TestCase):
    def setUp(self):
        self.index = geo.PrefectureIndex(SQUARE)

    def test_inside(self):
        self.assertEqual(self.index.resolve(35.5, 139.5), ("東京都", "polygon"))

    def test_just_outside_falls_back_to_nearest(self):
        self.assertEqual(self.index.resolve(35.5, 140.05), ("東京都", "nearest"))

    def test_far_away_is_unresolved(self):
        self.assertEqual(self.index.resolve(50.94, 6.94), (None, "none"))

    def test_missing_coordinates(self):
        self.assertEqual(self.index.resolve(None, None), (None, "none"))


class TestAnnotate(unittest.TestCase):
    def test_address_wins_over_polygon(self):
        place = Place(
            name="a", address="〒545-0002 大阪府大阪市阿倍野区", lat=35.5, lng=139.5
        )
        row = geo.annotate([place], geo.PrefectureIndex(SQUARE))[0]
        self.assertEqual(row["prefecture"], "大阪府")
        self.assertEqual(row["prefecture_source"], "address")
        self.assertEqual(row["city"], "大阪市")
        self.assertEqual(row["block"], "近畿")

    def test_polygon_fills_the_gap(self):
        place = Place(name="a", address="", lat=35.5, lng=139.5)
        row = geo.annotate([place], geo.PrefectureIndex(SQUARE))[0]
        self.assertEqual(
            (row["prefecture"], row["prefecture_source"]), ("東京都", "polygon")
        )

    def test_without_index_unresolved_stays_unresolved(self):
        place = Place(name="a", address="", lat=35.5, lng=139.5)
        row = geo.annotate([place], None)[0]
        self.assertIsNone(row["prefecture"])
        self.assertEqual(row["block"], "abroad")


class TestCountry(unittest.TestCase):
    """Google formats foreign addresses with the country last."""

    def test_country_is_taken_from_a_foreign_address(self):
        self.assertEqual(
            geo.country_from_address("Friesenstrasse 64-66, 50670 Koeln, ドイツ"),
            "ドイツ",
        )
        self.assertEqual(
            geo.country_from_address(
                "1 Jalan Something, 10450 George Town, マレーシア"
            ),
            "マレーシア",
        )

    def test_japanese_addresses_have_no_country(self):
        self.assertEqual(geo.country_from_address("〒163-8001 東京都新宿区西新宿"), "")

    def test_empty_or_single_component_address(self):
        self.assertEqual(geo.country_from_address(""), "")
        self.assertEqual(geo.country_from_address("Nowhere"), "")

    def test_annotate_uses_the_country_as_the_block(self):
        place = Place(name="brewery", address="Friesenstrasse 1, 50670 Koeln, ドイツ")
        row = geo.annotate([place], None)[0]
        self.assertIsNone(row["prefecture"])
        self.assertEqual(row["country"], "ドイツ")
        self.assertEqual(row["block"], "ドイツ")

    def test_japanese_rows_carry_no_country(self):
        place = Place(name="x", address="〒545-0002 大阪府大阪市阿倍野区")
        row = geo.annotate([place], None)[0]
        self.assertEqual(row["country"], "")
        self.assertEqual(row["block"], "近畿")

    def test_unlocatable_row_still_falls_back_to_abroad(self):
        row = geo.annotate([Place(name="x", address="")], None)[0]
        self.assertEqual(row["block"], "abroad")
