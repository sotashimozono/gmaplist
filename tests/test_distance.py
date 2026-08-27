"""Distance and per-contributor geography.

The haversine assertions are checked against analytic values rather than
against the implementation's own output: one degree of latitude is a known
fraction of the sphere, so a wrong radius or a swapped lat/lng shows up.
"""

import math
import unittest

from gmaplist import analyze
from gmaplist.model import Author, Place

R = analyze.EARTH_RADIUS_KM
DEG = math.pi * R / 180.0  # one degree of great circle, in km


def row(name, lat, lng, who="Alice"):
    return {
        "place": Place(name=name, lat=lat, lng=lng, added_by=Author(who, who)),
        "prefecture": None,
        "prefecture_source": "none",
        "city": "",
        "country": "",
        "block": "abroad",
    }


class TestHaversine(unittest.TestCase):
    def test_one_degree_of_latitude(self):
        self.assertAlmostEqual(analyze.haversine_km((0, 0), (1, 0)), DEG, places=6)
        self.assertAlmostEqual(analyze.haversine_km((10, 5), (11, 5)), DEG, places=6)

    def test_one_degree_of_longitude_on_the_equator(self):
        self.assertAlmostEqual(analyze.haversine_km((0, 0), (0, 1)), DEG, places=6)

    def test_agrees_with_the_spherical_law_of_cosines(self):
        # A different formula for the same quantity. Note that this is not the
        # distance along the parallel: at 60 degrees north that overstates the
        # great-circle distance by about half a metre per degree, which is
        # exactly the kind of near-miss a loose tolerance would hide.
        for lat, dlng in ((60.0, 1.0), (35.0, 4.0), (-20.0, 30.0)):
            phi = math.radians(lat)
            cos_theta = math.sin(phi) ** 2 + math.cos(phi) ** 2 * math.cos(
                math.radians(dlng)
            )
            expected = R * math.acos(min(1.0, max(-1.0, cos_theta)))
            self.assertAlmostEqual(
                analyze.haversine_km((lat, 0.0), (lat, dlng)), expected, places=6
            )

    def test_longitude_shrinks_with_latitude(self):
        equator = analyze.haversine_km((0.0, 0.0), (0.0, 1.0))
        high = analyze.haversine_km((60.0, 0.0), (60.0, 1.0))
        self.assertLess(high, equator)
        self.assertAlmostEqual(high / equator, math.cos(math.radians(60)), places=4)

    def test_quarter_of_the_equator(self):
        self.assertAlmostEqual(
            analyze.haversine_km((0, 0), (0, 90)), math.pi * R / 2, places=6
        )

    def test_antipodes(self):
        self.assertAlmostEqual(
            analyze.haversine_km((0, 0), (0, 180)), math.pi * R, places=6
        )

    def test_symmetric_and_zero(self):
        a, b = (35.5, 139.5), (34.7, 135.5)
        self.assertAlmostEqual(analyze.haversine_km(a, b), analyze.haversine_km(b, a))
        self.assertEqual(analyze.haversine_km(a, a), 0.0)


class TestDistances(unittest.TestCase):
    def setUp(self):
        self.anchor = (0.0, 0.0)
        self.rows = [
            row("far", 3.0, 0.0),
            row("near", 1.0, 0.0),
            row("mid", 2.0, 0.0),
            row("nowhere", None, None),
        ]

    def test_sorted_nearest_first_and_unlocated_dropped(self):
        pairs = analyze.distances_from(self.rows, self.anchor)
        self.assertEqual([r["place"].name for r, _ in pairs], ["near", "mid", "far"])

    def test_summary_counts_only_located_rows(self):
        s = analyze.distance_summary(self.rows, self.anchor)
        self.assertEqual(s["count"], 3)
        self.assertAlmostEqual(s["median_km"], 2 * DEG, places=6)

    def test_summary_bands_partition_every_row(self):
        s = analyze.distance_summary(self.rows, self.anchor)
        self.assertEqual(sum(n for _, _, n in s["bands"]), s["count"])

    def test_empty_input_does_not_divide_by_zero(self):
        s = analyze.distance_summary([row("nowhere", None, None)], self.anchor)
        self.assertEqual(s["count"], 0)
        self.assertEqual(s["median_km"], 0.0)


class TestContributorGeography(unittest.TestCase):
    def test_tight_cluster_has_near_zero_spread(self):
        rows = [row(f"p{i}", 10.0, 20.0, "Tight") for i in range(5)]
        stats = analyze.contributor_geography(rows)
        self.assertEqual(stats[0]["count"], 5)
        self.assertAlmostEqual(stats[0]["spread_km"], 0.0, places=6)

    def test_spread_is_median_distance_from_own_centroid(self):
        # Symmetric about the equator, so the centroid is (0, 0) and every
        # point sits one degree away.
        rows = [row("n", 1.0, 0.0, "Wide"), row("s", -1.0, 0.0, "Wide")]
        stats = analyze.contributor_geography(rows)
        self.assertAlmostEqual(stats[0]["centroid"][0], 0.0, places=9)
        self.assertAlmostEqual(stats[0]["spread_km"], DEG, places=6)

    def test_anchor_distance_is_optional(self):
        rows = [row("p", 1.0, 0.0, "Alice")]
        self.assertIsNone(analyze.contributor_geography(rows)[0]["anchor_km"])
        with_anchor = analyze.contributor_geography(rows, (0.0, 0.0))
        self.assertAlmostEqual(with_anchor[0]["anchor_km"], DEG, places=6)

    def test_rows_without_coordinates_are_skipped(self):
        rows = [row("p", 1.0, 0.0, "Alice"), row("q", None, None, "Alice")]
        self.assertEqual(analyze.contributor_geography(rows)[0]["count"], 1)


if __name__ == "__main__":
    unittest.main()
