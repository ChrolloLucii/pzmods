from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from pz_mod_sync.manifest import ManifestError, load_manifest


class ManifestTests(unittest.TestCase):
    def test_load_manifest_from_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "m.json"
            path.write_text(
                json.dumps(
                    {
                        "version": "1",
                        "name": "x",
                        "updated_at": "2026-03-13",
                        "steamcmd": {
                            "app_id": 108600,
                            "workshop_items": [{"publishedfileid": "123"}],
                        },
                        "project_zomboid": {"mods_to_enable": ["A"]},
                        "install": {"mode": "copy"},
                    }
                ),
                encoding="utf-8",
            )
            m = load_manifest(str(path))
            self.assertEqual(m.steamcmd.app_id, 108600)
            self.assertEqual(m.steamcmd.workshop_items[0].publishedfileid, "123")

    def test_invalid_manifest_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.json"
            path.write_text("{}", encoding="utf-8")
            with self.assertRaises(ManifestError):
                load_manifest(str(path))
