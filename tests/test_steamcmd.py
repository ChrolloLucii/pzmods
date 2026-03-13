from __future__ import annotations

import unittest

from pz_mod_sync.models import WorkshopItem
from pz_mod_sync.steamcmd import _chunks, build_workshop_download_args


class SteamCmdTests(unittest.TestCase):
    def test_build_args(self):
        args = build_workshop_download_args(
            app_id=108600,
            steam_username="myuser",
            items=[WorkshopItem(publishedfileid="111"), WorkshopItem(publishedfileid="222")],
        )
        self.assertEqual(args[0:2], ["+login", "myuser"])
        self.assertIn("+workshop_download_item", args)
        self.assertEqual(args[-1], "+quit")

    def test_chunks(self):
        items = [WorkshopItem(publishedfileid=str(i)) for i in range(1, 46)]
        batched = _chunks(items, 20)
        self.assertEqual(len(batched), 3)
        self.assertEqual(len(batched[0]), 20)
        self.assertEqual(len(batched[1]), 20)
        self.assertEqual(len(batched[2]), 5)
