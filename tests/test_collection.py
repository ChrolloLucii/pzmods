from __future__ import annotations

import unittest

from pz_mod_sync.collection import CollectionError, normalize_collection_id, normalize_workshop_item_id


class CollectionTests(unittest.TestCase):
    def test_normalize_collection_id_plain(self):
        self.assertEqual(normalize_collection_id("3652192243"), "3652192243")

    def test_normalize_collection_id_url(self):
        self.assertEqual(
            normalize_collection_id("https://steamcommunity.com/workshop/filedetails/?id=3652192243"),
            "3652192243",
        )

    def test_normalize_collection_id_invalid(self):
        with self.assertRaises(CollectionError):
            normalize_collection_id("abc")

    def test_normalize_workshop_item_id_plain(self):
        self.assertEqual(normalize_workshop_item_id("3635591071"), "3635591071")

    def test_normalize_workshop_item_id_url(self):
        self.assertEqual(
            normalize_workshop_item_id("https://steamcommunity.com/sharedfiles/filedetails/?id=3635591071"),
            "3635591071",
        )

    def test_normalize_workshop_item_id_invalid(self):
        with self.assertRaises(CollectionError):
            normalize_workshop_item_id("https://example.com/no-id")
