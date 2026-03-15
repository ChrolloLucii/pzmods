from __future__ import annotations

import json
import logging
import threading
import traceback
from datetime import date
from pathlib import Path
from tkinter import BooleanVar, StringVar, Tk, filedialog, messagebox
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText

from .collection import (
    CollectionError,
    fetch_collection_children,
    fetch_workshop_item_titles,
    normalize_collection_id,
    normalize_workshop_item_id,
)
from .config import load_user_config, save_user_config
from .generate import generate_manifest_from_installed
from .logging_utils import report_to_json
from .manifest import ManifestError, load_manifest
from .manifest_utils import merge_workshop_items
from .paths import detect_app_data_dir, detect_pz_user_dir, detect_steamcmd_path, workshop_dir_from_steamcmd
from .sync import run_doctor, run_sync, run_validate


class _TextHandler(logging.Handler):
    def __init__(self, callback):
        super().__init__()
        self._callback = callback

    def emit(self, record: logging.LogRecord) -> None:
        self._callback(self.format(record))


class PzModsGui:
    def __init__(self, root: Tk):
        self.root = root
        self.root.title("PZ Mod Sync")
        self.root.geometry("980x720")

        self.app_data_dir = detect_app_data_dir()
        self.config = load_user_config(self.app_data_dir)

        detected_steamcmd = detect_steamcmd_path(self.config.steamcmd_path)
        detected_pz = detect_pz_user_dir(self.config.pz_user_dir)

        self.manifest_var = StringVar(value=self.config.last_manifest or "sample-manifest/server.json")
        self.steamcmd_var = StringVar(value=str(detected_steamcmd) if detected_steamcmd else self.config.steamcmd_path)
        self.steam_user_var = StringVar(value=self.config.steam_username)
        self.pzdir_var = StringVar(value=str(detected_pz) if detected_pz else "")
        self.cache_var = StringVar(value=self.config.download_cache_dir)
        self.install_mode_var = StringVar(value="copy")
        self.download_mode_var = StringVar(value="missing-only")
        self.steamcmd_admin_var = BooleanVar(value=False)
        self.collection_var = StringVar(value="")
        self.mod_item_var = StringVar(value="")
        self.output_var = StringVar(value="sample-manifest/server.json")
        self.include_unmatched_var = BooleanVar(value=False)

        self._build_ui()
        self._append_log("Ready.")

    def _build_ui(self) -> None:
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except Exception:
            pass

        main = ttk.Frame(self.root, padding=12)
        main.pack(fill="both", expand=True)

        top = ttk.LabelFrame(main, text="Settings", padding=10)
        top.pack(fill="x")

        self._row(top, 0, "Manifest", self.manifest_var, browse_file=True)
        self._row(top, 1, "SteamCMD", self.steamcmd_var, browse_file=True)
        self._row(top, 2, "Steam user", self.steam_user_var)
        self._row(top, 3, "PZ user dir", self.pzdir_var, browse_dir=True)
        self._row(top, 4, "Workshop cache", self.cache_var, browse_dir=True)

        options = ttk.Frame(top)
        options.grid(row=5, column=0, columnspan=3, sticky="ew", pady=(8, 2))
        options.columnconfigure(1, weight=1)
        options.columnconfigure(3, weight=1)

        ttk.Label(options, text="Install mode").grid(row=0, column=0, sticky="w", padx=(0, 8))
        ttk.Combobox(options, textvariable=self.install_mode_var, values=["copy", "symlink"], state="readonly", width=14).grid(
            row=0, column=1, sticky="w"
        )

        ttk.Label(options, text="Download mode").grid(row=0, column=2, sticky="w", padx=(16, 8))
        ttk.Combobox(
            options,
            textvariable=self.download_mode_var,
            values=["always", "missing-only", "none"],
            state="readonly",
            width=14,
        ).grid(row=0, column=3, sticky="w")

        ttk.Checkbutton(options, text="Run SteamCMD as admin", variable=self.steamcmd_admin_var).grid(
            row=0, column=4, sticky="w", padx=(16, 0)
        )

        actions = ttk.LabelFrame(main, text="Actions", padding=10)
        actions.pack(fill="x", pady=(10, 0))

        btns = ttk.Frame(actions)
        btns.pack(fill="x")
        self.buttons: list[ttk.Button] = []
        self._add_button(btns, "Sync", self.on_sync)
        self._add_button(btns, "Validate", self.on_validate)
        self._add_button(btns, "Doctor", self.on_doctor)
        self._add_button(btns, "Generate manifest", self.on_generate)

        coll = ttk.Frame(actions)
        coll.pack(fill="x", pady=(8, 0))
        coll.columnconfigure(1, weight=1)

        ttk.Label(coll, text="Collection URL/ID").grid(row=0, column=0, sticky="w", padx=(0, 8))
        ttk.Entry(coll, textvariable=self.collection_var).grid(row=0, column=1, sticky="ew")
        ttk.Button(coll, text="Parse collection -> output", command=lambda: self._run_bg(self.on_parse_collection)).grid(
            row=0, column=2, padx=(8, 0)
        )
        ttk.Button(coll, text="Merge collection -> manifest", command=lambda: self._run_bg(self.on_merge_collection)).grid(
            row=0, column=3, padx=(8, 0)
        )

        mod_row = ttk.Frame(actions)
        mod_row.pack(fill="x", pady=(8, 0))
        mod_row.columnconfigure(1, weight=1)
        ttk.Label(mod_row, text="Workshop mod URL/ID").grid(row=0, column=0, sticky="w", padx=(0, 8))
        ttk.Entry(mod_row, textvariable=self.mod_item_var).grid(row=0, column=1, sticky="ew")
        ttk.Button(mod_row, text="Add mod -> manifest", command=lambda: self._run_bg(self.on_add_mod_item)).grid(
            row=0, column=2, padx=(8, 0)
        )

        out = ttk.Frame(actions)
        out.pack(fill="x", pady=(8, 0))
        out.columnconfigure(1, weight=1)
        ttk.Label(out, text="Output/target manifest").grid(row=0, column=0, sticky="w", padx=(0, 8))
        ttk.Entry(out, textvariable=self.output_var).grid(row=0, column=1, sticky="ew")
        ttk.Button(out, text="Browse", command=self._browse_output).grid(row=0, column=2, padx=(8, 0))
        ttk.Checkbutton(out, text="Include unmatched local ModIDs", variable=self.include_unmatched_var).grid(
            row=0, column=3, padx=(10, 0), sticky="w"
        )

        log_frame = ttk.LabelFrame(main, text="Log", padding=10)
        log_frame.pack(fill="both", expand=True, pady=(10, 0))
        self.log_box = ScrolledText(log_frame, wrap="word", height=18)
        self.log_box.pack(fill="both", expand=True)

    def _row(self, parent, row: int, label: str, var: StringVar, browse_file: bool = False, browse_dir: bool = False) -> None:
        parent.columnconfigure(1, weight=1)
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=(0, 8), pady=3)
        ttk.Entry(parent, textvariable=var).grid(row=row, column=1, sticky="ew", pady=3)
        if browse_file:
            ttk.Button(parent, text="Browse", command=lambda v=var: self._browse_file(v)).grid(row=row, column=2, padx=(8, 0), pady=3)
        if browse_dir:
            ttk.Button(parent, text="Browse", command=lambda v=var: self._browse_dir(v)).grid(row=row, column=2, padx=(8, 0), pady=3)

    def _add_button(self, parent, title: str, action) -> None:
        b = ttk.Button(parent, text=title, command=lambda a=action: self._run_bg(a))
        b.pack(side="left", padx=(0, 8))
        self.buttons.append(b)

    def _browse_file(self, var: StringVar) -> None:
        p = filedialog.askopenfilename()
        if p:
            var.set(p)

    def _browse_dir(self, var: StringVar) -> None:
        p = filedialog.askdirectory()
        if p:
            var.set(p)

    def _browse_output(self) -> None:
        p = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON", "*.json"), ("All", "*.*")])
        if p:
            self.output_var.set(p)

    def _append_log(self, text: str) -> None:
        self.log_box.insert("end", text + "\n")
        self.log_box.see("end")

    def _append_log_threadsafe(self, text: str) -> None:
        self.root.after(0, lambda: self._append_log(text))

    def _set_busy(self, busy: bool) -> None:
        state = "disabled" if busy else "normal"
        for b in self.buttons:
            b.configure(state=state)

    def _logger(self) -> logging.Logger:
        logger = logging.getLogger("pz_mod_sync_gui")
        logger.setLevel(logging.INFO)
        logger.handlers.clear()
        h = _TextHandler(self._append_log_threadsafe)
        h.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(h)
        return logger

    def _run_bg(self, func) -> None:
        self._set_busy(True)

        def worker():
            try:
                func()
            except Exception as exc:
                self._append_log_threadsafe(f"ERROR: {exc}")
                self._append_log_threadsafe(traceback.format_exc())
                self.root.after(0, lambda: messagebox.showerror("PZ Mod Sync", str(exc)))
            finally:
                self.root.after(0, lambda: self._set_busy(False))

        threading.Thread(target=worker, daemon=True).start()

    def _save_common_config(self, workshop_dir: Path | None = None) -> None:
        self.config.steamcmd_path = self.steamcmd_var.get().strip()
        self.config.steam_username = self.steam_user_var.get().strip()
        self.config.pz_user_dir = self.pzdir_var.get().strip()
        if workshop_dir is not None:
            self.config.download_cache_dir = str(workshop_dir)
        self.config.last_manifest = self.manifest_var.get().strip()
        save_user_config(self.app_data_dir, self.config)

    def on_doctor(self) -> None:
        steamcmd = detect_steamcmd_path(self.steamcmd_var.get().strip() or self.config.steamcmd_path)
        pz_user = detect_pz_user_dir(self.pzdir_var.get().strip() or self.config.pz_user_dir)
        lines = run_doctor(steamcmd, pz_user, pz_user / "mods")
        for line in lines:
            self._append_log(line)

    def on_validate(self) -> None:
        manifest = load_manifest(self.manifest_var.get().strip())
        pz_user = detect_pz_user_dir(self.pzdir_var.get().strip() or self.config.pz_user_dir or manifest.install.pz_user_dir_override)
        report = run_validate(manifest, pz_user / "mods")
        self._append_log(report_to_json(report))
        self._save_common_config()
        if report.missing_modids:
            self.root.after(0, lambda: messagebox.showwarning("Validate", "Some ModIDs are missing."))
        else:
            self.root.after(0, lambda: messagebox.showinfo("Validate", "All required ModIDs are present."))

    def on_sync(self) -> None:
        manifest = load_manifest(self.manifest_var.get().strip())
        steamcmd = detect_steamcmd_path(self.steamcmd_var.get().strip() or self.config.steamcmd_path)
        if not steamcmd:
            raise ManifestError("SteamCMD not found.")

        steam_user = self.steam_user_var.get().strip() or self.config.steam_username
        if not steam_user:
            raise ManifestError("Steam username is required.")

        pz_user = detect_pz_user_dir(self.pzdir_var.get().strip() or self.config.pz_user_dir)
        workshop_dir = (
            Path(self.cache_var.get().strip()).expanduser().resolve()
            if self.cache_var.get().strip()
            else workshop_dir_from_steamcmd(steamcmd, manifest.steamcmd.app_id)
        )

        logger = self._logger()
        report = run_sync(
            manifest=manifest,
            steamcmd_exe=steamcmd,
            workshop_content_dir=workshop_dir,
            pz_mods_dir=pz_user / "mods",
            steam_username=steam_user,
            install_mode=self.install_mode_var.get().strip() or "copy",
            logger=logger,
            download_mode=self.download_mode_var.get().strip() or "always",
            steamcmd_admin=bool(self.steamcmd_admin_var.get()),
        )
        self._append_log(report_to_json(report))
        self._save_common_config(workshop_dir=workshop_dir)
        if report.errors or report.missing_modids:
            self.root.after(0, lambda: messagebox.showwarning("Sync", "Sync finished with warnings/errors. Check log."))
        else:
            self.root.after(0, lambda: messagebox.showinfo("Sync", "Sync finished successfully."))

    def on_parse_collection(self) -> None:
        collection_id = normalize_collection_id(self.collection_var.get().strip())
        item_ids = fetch_collection_children(collection_id)
        titles = fetch_workshop_item_titles(item_ids)
        workshop_items = [
            {"publishedfileid": item_id, "display_name": titles.get(item_id, f"Workshop Item {item_id}")}
            for item_id in item_ids
        ]
        out_path = Path(self.output_var.get().strip() or "sample-manifest/collection.json").expanduser().resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": "1",
            "name": "Generated from Steam Collection",
            "updated_at": str(date.today()),
            "steamcmd": {"app_id": 108600, "workshop_items": workshop_items},
            "project_zomboid": {"mods_to_enable": ["REPLACE_WITH_REAL_MODIDS_AFTER_SYNC"]},
            "install": {"mode": "copy", "pz_user_dir_override": "", "allow_extra_local_mods": True},
        }
        out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        self._append_log(f"Saved manifest: {out_path}")

    def on_merge_collection(self) -> None:
        manifest_path = Path(self.manifest_var.get().strip()).expanduser().resolve()
        if not manifest_path.exists():
            raise ManifestError(f"Manifest not found: {manifest_path}")

        collection_id = normalize_collection_id(self.collection_var.get().strip())
        item_ids = fetch_collection_children(collection_id)
        titles = fetch_workshop_item_titles(item_ids)
        incoming = [
            {"publishedfileid": item_id, "display_name": titles.get(item_id, f"Workshop Item {item_id}")}
            for item_id in item_ids
        ]

        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        steam = data.setdefault("steamcmd", {})
        steam.setdefault("app_id", 108600)
        current = steam.setdefault("workshop_items", [])
        merged, added = merge_workshop_items(current, incoming)
        steam["workshop_items"] = merged
        data.setdefault("version", "1")
        data.setdefault("name", "PZ Modpack")
        data.setdefault("updated_at", "")
        data.setdefault("project_zomboid", {}).setdefault("mods_to_enable", ["REPLACE_WITH_REAL_MODIDS_AFTER_SYNC"])
        data.setdefault("install", {"mode": "copy", "pz_user_dir_override": "", "allow_extra_local_mods": True})
        manifest_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        self._append_log(f"Merged collection items: +{added}. Total={len(merged)}")

    def on_add_mod_item(self) -> None:
        manifest_path = Path(self.manifest_var.get().strip()).expanduser().resolve()
        if not manifest_path.exists():
            raise ManifestError(f"Manifest not found: {manifest_path}")

        item_id = normalize_workshop_item_id(self.mod_item_var.get().strip())
        titles = fetch_workshop_item_titles([item_id])
        incoming = [{"publishedfileid": item_id, "display_name": titles.get(item_id, f"Workshop Item {item_id}")}]

        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        steam = data.setdefault("steamcmd", {})
        steam.setdefault("app_id", 108600)
        current = steam.setdefault("workshop_items", [])
        merged, added = merge_workshop_items(current, incoming)
        steam["workshop_items"] = merged
        data.setdefault("version", "1")
        data.setdefault("name", "PZ Modpack")
        data.setdefault("updated_at", "")
        data.setdefault("project_zomboid", {}).setdefault("mods_to_enable", ["REPLACE_WITH_REAL_MODIDS_AFTER_SYNC"])
        data.setdefault("install", {"mode": "copy", "pz_user_dir_override": "", "allow_extra_local_mods": True})
        manifest_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

        if added:
            self._append_log(f"Added mod item: {item_id}")
        else:
            self._append_log(f"Mod item already exists: {item_id}")

    def on_generate(self) -> None:
        pz_user = detect_pz_user_dir(self.pzdir_var.get().strip() or self.config.pz_user_dir)
        steamcmd = detect_steamcmd_path(self.steamcmd_var.get().strip() or self.config.steamcmd_path)
        if self.cache_var.get().strip():
            workshop_dir = Path(self.cache_var.get().strip()).expanduser().resolve()
        elif self.config.download_cache_dir:
            workshop_dir = Path(self.config.download_cache_dir).expanduser().resolve()
        elif steamcmd:
            workshop_dir = workshop_dir_from_steamcmd(steamcmd, 108600)
        else:
            workshop_dir = Path(".")

        out_path = Path(self.output_var.get().strip() or "sample-manifest/from-installed.json").expanduser().resolve()
        data = generate_manifest_from_installed(
            pz_mods_dir=pz_user / "mods",
            workshop_content_dir=workshop_dir,
            name="Generated from installed mods",
            app_id=108600,
            include_unmatched_modids=bool(self.include_unmatched_var.get()),
        )
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(data.manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        self._append_log(
            f"Saved {out_path}; installed={len(data.installed_modids)} matched={len(data.matched_modids)} workshop_items={len(data.workshop_item_ids)}"
        )


def launch_gui() -> int:
    root = Tk()
    PzModsGui(root)
    root.mainloop()
    return 0
