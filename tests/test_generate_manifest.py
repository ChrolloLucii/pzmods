from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from pz_mod_sync.generate import generate_manifest_from_installed


class GenerateManifestTests(unittest.TestCase):
    def test_generate_manifest_from_installed_with_workshop_mapping(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pz_mods = root / "Zomboid" / "mods"
            pz_mods.mkdir(parents=True)

            (pz_mods / "CarPackA").mkdir()
            (pz_mods / "CarPackA" / "mod.info").write_text("name=A\nid=CarPackA\n", encoding="utf-8")

            (pz_mods / "LocalOnly").mkdir()
            (pz_mods / "LocalOnly" / "mod.info").write_text("name=L\nid=LocalOnly\n", encoding="utf-8")

            workshop_root = root / "steamapps" / "workshop" / "content" / "108600"
            item_dir = workshop_root / "123"
            (item_dir / "mods" / "CarPackA").mkdir(parents=True)
            (item_dir / "mods" / "CarPackA" / "mod.info").write_text("name=A\nid=CarPackA\n", encoding="utf-8")

            generated = generate_manifest_from_installed(
                pz_mods_dir=pz_mods,
                workshop_content_dir=workshop_root,
                name="Generated",
                app_id=108600,
            )

            self.assertIn("CarPackA", generated.installed_modids)
            self.assertIn("LocalOnly", generated.installed_modids)
            self.assertEqual(generated.workshop_item_ids, ["123"])
            self.assertEqual(generated.unmatched_modids, ["LocalOnly"])
            self.assertEqual(generated.manifest["steamcmd"]["workshop_items"][0]["publishedfileid"], "123")
