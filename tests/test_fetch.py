"""URL handling. Only the offline paths are exercised."""

import unittest

from gmaplist.fetch import ListFetchError, build_url, resolve_list_id


class TestResolveListId(unittest.TestCase):
    def test_bare_id(self):
        self.assertEqual(resolve_list_id("aB3dEfGhIjKlMnOpQrStUv"), "aB3dEfGhIjKlMnOpQrStUv")

    def test_data_url(self):
        url = "https://www.google.com/maps/@/data=!3m1!4b1!4m3!11m2!2saB3dEfGhIjKlMnOpQrStUv!3e3?entry=tts"
        self.assertEqual(resolve_list_id(url), "aB3dEfGhIjKlMnOpQrStUv")

    def test_canonical_url(self):
        url = "https://www.google.com/maps/placelists/list/aB3dEfGhIjKlMnOpQrStUv"
        self.assertEqual(resolve_list_id(url), "aB3dEfGhIjKlMnOpQrStUv")

    def test_garbage_is_rejected_without_a_request(self):
        with self.assertRaises(ListFetchError):
            resolve_list_id("just some text")


class TestBuildUrl(unittest.TestCase):
    def test_contains_id_and_page_size(self):
        url = build_url("ABC0123456789xyz", page_size=500)
        self.assertIn("!1sABC0123456789xyz!", url)
        self.assertIn("!4i500", url)
        self.assertIn("hl=ja", url)
