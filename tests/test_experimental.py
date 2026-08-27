"""The experimental category lookup.

Offline throughout: `fetch_details` takes a transport, so the batching and
decoding run against synthetic wire payloads with no request to Google.
"""

import json
import unittest
import urllib.parse

from gmaplist import experimental as ex
from gmaplist.model import Author, Place

GUARD = ")]}'"


def wire(entries):
    """Wrap decoded entries in the envelope the search endpoint returns."""
    document = json.dumps([[None, entries]], ensure_ascii=False)
    envelope = {"c": 0, "d": GUARD + "\n" + document, "e": 23}
    return json.dumps(envelope, ensure_ascii=False) + '/*""*/'


def entry(place_id, name="A place", categories=(), rating=None, reviews=None):
    block = [None] * 15
    block[4] = [None] * 9
    block[4][7] = rating
    block[4][8] = reviews
    block[10] = place_id
    block[11] = name
    block[13] = list(categories)
    node = [None] * 15
    node[14] = block
    return node


class TestBuildSearchUrl(unittest.TestCase):
    def test_carries_every_id_and_the_page_size(self):
        url = ex.build_search_url(["0xaaa:0xbbb", "0xccc:0xddd"])
        # The colon is percent-encoded, exactly as Google's own client sends
        # it, so assert on the decoded form rather than the wire form.
        decoded = urllib.parse.unquote(url)
        self.assertIn("!1s0xaaa:0xbbb", decoded)
        self.assertIn("!1s0xccc:0xddd", decoded)
        # Page size must match the batch, or the reply is silently truncated.
        self.assertIn("!7i2", url)

    def test_language_and_region_are_configurable(self):
        url = ex.build_search_url(["0xaaa:0xbbb"], hl="en", gl="us")
        self.assertIn("hl=en", url)
        self.assertIn("gl=us", url)

    def test_empty_input_still_produces_a_valid_page_size(self):
        self.assertIn("!7i1", ex.build_search_url([]))


class TestParseResponse(unittest.TestCase):
    def test_reads_the_fields_it_promises(self):
        body = wire(
            [entry("0xaaa:0xbbb", "Cafe A", ["カフェ・喫茶", "コーヒー"], 4.2, 857)]
        )
        (detail,) = ex.parse_response(body)
        self.assertEqual(detail.place_id, "0xaaa:0xbbb")
        self.assertEqual(detail.name, "Cafe A")
        self.assertEqual(detail.categories, ("カフェ・喫茶", "コーヒー"))
        self.assertEqual(detail.primary_category, "カフェ・喫茶")
        self.assertAlmostEqual(detail.rating, 4.2)
        self.assertEqual(detail.review_count, 857)

    def test_missing_rating_and_reviews_stay_none(self):
        (detail,) = ex.parse_response(wire([entry("0xaaa:0xbbb")]))
        self.assertIsNone(detail.rating)
        self.assertIsNone(detail.review_count)
        self.assertEqual(detail.categories, ())
        self.assertEqual(detail.primary_category, "")

    def test_entries_without_a_place_id_are_skipped(self):
        body = wire([entry("0xaaa:0xbbb"), [None] * 15])
        self.assertEqual(len(ex.parse_response(body)), 1)

    def test_split_envelopes_are_concatenated(self):
        # The endpoint streams the document across envelopes.
        document = json.dumps([[None, [entry("0xaaa:0xbbb", "Split")]]])
        full = GUARD + "\n" + document
        cut = len(full) // 2
        body = (
            json.dumps({"c": 0, "d": full[:cut]})
            + '/*""*/'
            + json.dumps({"c": 1, "d": full[cut:]})
            + '/*""*/'
        )
        (detail,) = ex.parse_response(body)
        self.assertEqual(detail.name, "Split")

    def test_empty_body_is_an_error(self):
        with self.assertRaises(ex.CategoryFetchError):
            ex.parse_response("")

    def test_garbage_body_is_an_error(self):
        with self.assertRaises(ex.CategoryFetchError):
            ex.parse_response('{"c":0,"d":"not json at all"}/*""*/')


class TestFetchDetails(unittest.TestCase):
    def setUp(self):
        self.urls = []

    def transport(self, url):
        self.urls.append(url)
        decoded = urllib.parse.unquote(url)
        ids = [p.split("!")[0].split("&")[0] for p in decoded.split("!72m2!1m1!1s")[1:]]
        return wire([entry(i, name=f"place {i}") for i in ids])

    def test_batches_and_keys_by_place_id(self):
        ids = [f"0x{i:03x}:0x{i:03x}" for i in range(25)]
        got = ex.fetch_details(ids, batch_size=10, delay=0, transport=self.transport)
        self.assertEqual(len(self.urls), 3)
        self.assertEqual(len(got), 25)
        self.assertEqual(got[ids[0]].name, f"place {ids[0]}")

    def test_blank_ids_are_dropped_before_the_request(self):
        got = ex.fetch_details(
            ["0xaaa:0xbbb", "", None], batch_size=10, delay=0, transport=self.transport
        )
        self.assertEqual(len(got), 1)
        self.assertEqual(self.urls[0].count("!72m2!1m1!1s"), 1)

    def test_no_ids_makes_no_request(self):
        self.assertEqual(ex.fetch_details([], delay=0, transport=self.transport), {})
        self.assertEqual(self.urls, [])


class TestGenreOf(unittest.TestCase):
    def test_matches_any_category_not_just_the_first(self):
        self.assertEqual(ex.genre_of(["珍しい何か", "ラーメン屋"]), "飲食店")

    def test_earlier_rules_win(self):
        # A hot-spring inn with a restaurant is lodging, because 宿泊・温泉
        # is ordered above 飲食店.
        self.assertEqual(ex.genre_of(["レストラン", "旅館"]), "宿泊・温泉")

    def test_unmatched_categories_stay_visible(self):
        self.assertEqual(ex.genre_of(["市役所・区役所"]), ex.UNCLASSIFIED)
        self.assertEqual(ex.genre_of([]), ex.UNCLASSIFIED)

    def test_custom_rules_replace_the_defaults(self):
        rules = (("food", ("Restaurant",)), ("stay", ("Hotel",)))
        self.assertEqual(ex.genre_of(["Italian Restaurant"], rules), "food")
        self.assertEqual(ex.genre_of(["カフェ・喫茶"], rules), ex.UNCLASSIFIED)

    def test_a_sample_of_real_category_names(self):
        for categories, expected in [
            (["カフェ・喫茶"], "カフェ・甘味"),
            (["観光名所"], "観光・自然"),
            (["博物館"], "文化施設"),
            (["焼酎醸造所"], "酒造・醸造"),
            (["スーパーマーケット"], "買い物"),
            (["サービスエリア / パーキング エリア"], "交通・道の駅"),
            (["日帰り温泉"], "宿泊・温泉"),
        ]:
            self.assertEqual(ex.genre_of(categories), expected, categories)


def make_row(name, place_id, who="Alice"):
    return {
        "place": Place(name=name, place_id=place_id, added_by=Author(who, who)),
        "prefecture": "東京都",
        "prefecture_source": "address",
        "city": "",
        "country": "",
        "block": "関東",
    }


class TestAttach(unittest.TestCase):
    def setUp(self):
        self.rows = [
            make_row("cafe", "0xaaa:0xbbb"),
            make_row("street", "0xccc:0xddd"),
            make_row("unknown", "0xeee:0xfff", who="Bob"),
        ]
        self.details = {
            "0xaaa:0xbbb": ex.PlaceDetail(
                "0xaaa:0xbbb", "cafe", ("カフェ・喫茶",), 4.2, 857
            ),
            "0xccc:0xddd": ex.PlaceDetail("0xccc:0xddd", "street", (), None, None),
        }

    def test_sets_genre_and_categories_on_every_row(self):
        ex.attach(self.rows, self.details)
        self.assertEqual(self.rows[0]["genre"], "カフェ・甘味")
        self.assertEqual(self.rows[0]["categories"], ["カフェ・喫茶"])
        self.assertEqual(self.rows[1]["genre"], ex.UNCLASSIFIED)
        self.assertEqual(self.rows[2]["categories"], [])

    def test_reports_what_it_could_not_cover(self):
        report = ex.attach(self.rows, self.details)
        self.assertEqual(report.matched, 2)
        self.assertEqual(report.missing, ["unknown"])
        self.assertEqual(report.without_category, ["street"])
        self.assertEqual(report.with_review_count, 1)
        self.assertAlmostEqual(report.review_coverage, 0.5)

    def test_review_coverage_of_nothing_is_zero_not_an_error(self):
        self.assertEqual(ex.Enrichment().review_coverage, 0.0)


class TestAggregations(unittest.TestCase):
    def setUp(self):
        self.rows = [
            make_row("a", "1"),
            make_row("b", "2"),
            make_row("c", "3", who="Bob"),
        ]
        ex.attach(
            self.rows,
            {
                "1": ex.PlaceDetail("1", "a", ("ラーメン屋",)),
                "2": ex.PlaceDetail("2", "b", ("カフェ・喫茶",)),
                "3": ex.PlaceDetail("3", "c", ("ラーメン屋", "麺類専門店")),
            },
        )

    def test_by_genre(self):
        self.assertEqual(ex.by_genre(self.rows), [("飲食店", 2), ("カフェ・甘味", 1)])

    def test_by_category_keeps_google_wording(self):
        self.assertEqual(
            dict(ex.by_category(self.rows)), {"ラーメン屋": 2, "カフェ・喫茶": 1}
        )

    def test_crosstab_orders_people_by_volume(self):
        people, genres, cells = ex.genre_crosstab(self.rows)
        self.assertEqual(people, ["Alice", "Bob"])
        self.assertEqual(genres[0], "飲食店")
        self.assertEqual(cells[("Alice", "カフェ・甘味")], 1)
        self.assertEqual(cells.get(("Bob", "カフェ・甘味"), 0), 0)

    def test_aggregations_tolerate_rows_that_were_never_enriched(self):
        plain = [make_row("x", "9")]
        self.assertEqual(ex.by_genre(plain), [(ex.UNCLASSIFIED, 1)])
        self.assertEqual(ex.by_category(plain), [])


if __name__ == "__main__":
    unittest.main()
