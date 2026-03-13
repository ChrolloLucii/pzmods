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
            self.assertEqual(generated.matched_modids, ["CarPackA"])
            self.assertEqual(generated.workshop_item_ids, ["123"])
            self.assertEqual(generated.unmatched_modids, ["LocalOnly"])
            self.assertEqual(generated.manifest["steamcmd"]["workshop_items"][0]["publishedfileid"], "123")
            self.assertEqual(generated.manifest["project_zomboid"]["mods_to_enable"], ["CarPackA"])

            generated_with_unmatched = generate_manifest_from_installed(
                pz_mods_dir=pz_mods,
                workshop_content_dir=workshop_root,
                name="Generated",
                app_id=108600,
                include_unmatched_modids=True,
            )
            self.assertIn("LocalOnly", generated_with_unmatched.manifest["project_zomboid"]["mods_to_enable"])

    def test_generate_manifest_uses_recursive_modinfo_and_workshop_page_hints(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pz_mods = root / "Zomboid" / "mods"
            pz_mods.mkdir(parents=True)

            # ModID exists only in nested version folder (common B42 layout)
            nested_mod = pz_mods / "TempModPack"
            (nested_mod / "42.13").mkdir(parents=True)
            (nested_mod / "42.13" / "mod.info").write_text("name=T\nid=TempMod\n", encoding="utf-8")
            (nested_mod / "workshopPage.txt").write_text(
                "https://steamcommunity.com/sharedfiles/filedetails/?id=2832136889",
                encoding="utf-8",
            )

            # No workshop cache mapping provided, only local hint should work.
            workshop_root = root / "empty-workshop-cache"
            workshop_root.mkdir(parents=True)

            generated = generate_manifest_from_installed(
                pz_mods_dir=pz_mods,
                workshop_content_dir=workshop_root,
                name="Generated",
                app_id=108600,
            )

            self.assertIn("TempMod", generated.installed_modids)
            self.assertIn("TempMod", generated.matched_modids)
            self.assertEqual(generated.workshop_item_ids, ["2832136889"])
            self.assertEqual(generated.unmatched_modids, [])

    def test_generate_manifest_uses_local_install_metadata_mapping(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pz_mods = root / "Zomboid" / "mods"
            pz_mods.mkdir(parents=True)

            mod = pz_mods / "MetaMappedMod"
            mod.mkdir()
            (mod / "mod.info").write_text("name=M\nid=MetaMapped\n", encoding="utf-8")
            (mod / ".pzmods-meta.json").write_text(
                '{"mod_id":"MetaMapped","workshop_item_id":"999999999"}',
                encoding="utf-8",
            )

            workshop_root = root / "steamapps" / "workshop" / "content" / "108600"
            workshop_root.mkdir(parents=True)

            generated = generate_manifest_from_installed(
                pz_mods_dir=pz_mods,
                workshop_content_dir=workshop_root,
                name="Generated",
                app_id=108600,
            )

            self.assertEqual(generated.matched_modids, ["MetaMapped"])
            self.assertEqual(generated.workshop_item_ids, ["999999999"])
            self.assertEqual(generated.unmatched_modids, [])
