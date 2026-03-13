from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pz_mod_sync.install import install_mod_folder, validate_required_modids
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
