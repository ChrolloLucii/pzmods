from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pz_mod_sync.install import discover_mod_folders, install_mod_folder, validate_required_modids
from pz_mod_sync.paths import detect_pz_user_dir


class PathAndInstallTests(unittest.TestCase):
    @patch("platform.system", return_value="Windows")
    def test_detect_pz_user_dir_windows(self, _):
        p = detect_pz_user_dir(None)
        self.assertEqual(p.name, "Zomboid")

    def test_install_copy_idempotent_and_validate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "src_mod"
            src.mkdir(parents=True)
            (src / "mod.info").write_text("name=Test\nid=MyMod\n", encoding="utf-8")
            (src / "file.txt").write_text("hello", encoding="utf-8")

            dest_mods = root / "mods"
            changed1, modid1 = install_mod_folder(src, dest_mods, mode="copy")
            changed2, modid2 = install_mod_folder(src, dest_mods, mode="copy")

            self.assertTrue(changed1)
            self.assertFalse(changed2)
            self.assertEqual(modid1, "MyMod")
            self.assertEqual(modid2, "MyMod")

            missing = validate_required_modids(dest_mods, ["MyMod", "OtherMod"])
            self.assertEqual(missing, ["OtherMod"])

    def test_discover_prefers_shallower_duplicate_modid(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = root / "mods" / "CarHUD"
            nested = base / "42"
            base.mkdir(parents=True)
            nested.mkdir(parents=True)

            (base / "mod.info").write_text("name=X\nid=CarHUD\nversionMin=41.0\n", encoding="utf-8")
            (nested / "mod.info").write_text("name=X\nid=CarHUD\nversionMin=42.0\n", encoding="utf-8")

            found = discover_mod_folders(root)
            self.assertEqual(len(found), 1)
            self.assertEqual(found[0][0], "CarHUD")
            self.assertEqual(found[0][1], base)

    def test_discover_selects_shared_parent_for_versioned_variants(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            parent = root / "mods" / "TempMod"
            v4212 = parent / "42.12"
            v4213 = parent / "42.13"
            v4212.mkdir(parents=True)
            v4213.mkdir(parents=True)

            (v4212 / "mod.info").write_text("name=T\nid=TempMod\n", encoding="utf-8")
            (v4213 / "mod.info").write_text("name=T\nid=TempMod\n", encoding="utf-8")

            found = discover_mod_folders(root)
            self.assertEqual(len(found), 1)
            self.assertEqual(found[0][0], "TempMod")
            self.assertEqual(found[0][1], parent)

    def test_install_from_parent_without_root_mod_info_uses_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_parent = root / "source" / "TempMod"
            source_parent.mkdir(parents=True)
            (source_parent / "42.12").mkdir()
            (source_parent / "42.13").mkdir()
            (source_parent / "42.12" / "mod.info").write_text("name=T\nid=TempMod\n", encoding="utf-8")
            (source_parent / "42.13" / "mod.info").write_text("name=T\nid=TempMod\n", encoding="utf-8")

            dest_mods = root / "mods"
            changed, modid = install_mod_folder(source_parent, dest_mods, mode="copy", mod_id_override="TempMod")
            self.assertTrue(changed)
            self.assertEqual(modid, "TempMod")
            self.assertTrue((dest_mods / "TempMod" / "42.12" / "mod.info").exists())
            self.assertTrue((dest_mods / "TempMod" / "42.13" / "mod.info").exists())

            missing = validate_required_modids(dest_mods, ["TempMod", "MissingOne"])
            self.assertEqual(missing, ["MissingOne"])
