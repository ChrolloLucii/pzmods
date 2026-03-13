from __future__ import annotations

import unittest

from pz_mod_sync.manifest_utils import merge_workshop_items


class ManifestUtilsTests(unittest.TestCase):
    def test_merge_workshop_items_deduplicates(self):
        existing = [
            {"publishedfileid": "111", "display_name": "A"},
            {"publishedfileid": "222", "display_name": "B"},
        ]
        incoming = [
            {"publishedfileid": "222", "display_name": "B2"},
            {"publishedfileid": "333", "display_name": "C"},
        ]

        merged, added = merge_workshop_items(existing, incoming)
        self.assertEqual(added, 1)
        self.assertEqual([x["publishedfileid"] for x in merged], ["111", "222", "333"])
