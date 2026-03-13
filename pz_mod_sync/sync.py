from __future__ import annotations

import logging
from pathlib import Path

from .install import discover_mod_folders, install_mod_folder, validate_required_modids
from .manifest import Manifest
from .models import SyncReport
from .steamcmd import run_steamcmd_download


def _workshop_item_present(item_dir: Path) -> bool:
    if not item_dir.exists() or not item_dir.is_dir():
        return False
    try:
        next(item_dir.rglob("mod.info"))
        return True
    except StopIteration:
        return False


def run_sync(
    manifest: Manifest,
    steamcmd_exe: Path,
    workshop_content_dir: Path,
    pz_mods_dir: Path,
    steam_username: str,
    install_mode: str,
    logger: logging.Logger,
    download_mode: str = "always",
    steamcmd_admin: bool = False,
) -> SyncReport:
    report = SyncReport()

    items_to_download = manifest.steamcmd.workshop_items
    if download_mode == "missing-only":
        items_to_download = [
            item
            for item in manifest.steamcmd.workshop_items
            if not _workshop_item_present(workshop_content_dir / item.publishedfileid)
        ]
    elif download_mode == "none":
        items_to_download = []

    if items_to_download:
        logger.info("Starting SteamCMD download/update for %s items...", len(items_to_download))
        run_steamcmd_download(
            steamcmd_exe=steamcmd_exe,
            app_id=manifest.steamcmd.app_id,
            items=items_to_download,
            steam_username=steam_username,
            run_as_admin=steamcmd_admin,
        )
        report.downloaded_items = [item.publishedfileid for item in items_to_download]
    else:
        logger.info("Skipping SteamCMD download step (download_mode=%s).", download_mode)

    logger.info("Installing mods into %s", pz_mods_dir)
    for item in manifest.steamcmd.workshop_items:
        item_dir = workshop_content_dir / item.publishedfileid
        if not item_dir.exists():
            report.errors.append(f"Workshop item directory missing after download: {item_dir}")
            continue

        found_mods = discover_mod_folders(item_dir)
        if not found_mods:
            report.warnings.append(f"No mod.info files found in workshop item {item.publishedfileid}")
            continue

        for mod_id, source_mod_dir in found_mods:
            try:
                changed, modid = install_mod_folder(
                    source_mod_dir,
                    pz_mods_dir,
                    mode=install_mode,
                    mod_id_override=mod_id,
                    workshop_item_id=item.publishedfileid,
                )
                if changed:
                    report.installed_mods.append(modid)
                else:
                    report.skipped_mods.append(modid)
            except Exception as exc:
                report.errors.append(f"Failed to install mod from {source_mod_dir}: {exc}")

    report.missing_modids = validate_required_modids(pz_mods_dir, manifest.project_zomboid.mods_to_enable)
    return report


def run_validate(manifest: Manifest, pz_mods_dir: Path) -> SyncReport:
    report = SyncReport()
    report.missing_modids = validate_required_modids(pz_mods_dir, manifest.project_zomboid.mods_to_enable)
    return report


def run_doctor(steamcmd_exe: Path | None, pz_user_dir: Path, pz_mods_dir: Path) -> list[str]:
    results: list[str] = []

    if steamcmd_exe and steamcmd_exe.exists():
        results.append(f"OK: SteamCMD found at {steamcmd_exe}")
    else:
        results.append("ERROR: SteamCMD not found. Install SteamCMD and set --steamcmd or config.steamcmd_path")

    if pz_user_dir.exists():
        results.append(f"OK: Project Zomboid user dir found at {pz_user_dir}")
    else:
        results.append(f"WARN: Project Zomboid user dir does not exist yet: {pz_user_dir}")

    try:
        pz_mods_dir.mkdir(parents=True, exist_ok=True)
        test_file = pz_mods_dir / ".pzmods-write-test"
        test_file.write_text("ok", encoding="utf-8")
        test_file.unlink(missing_ok=True)
        results.append(f"OK: Mods dir is writable: {pz_mods_dir}")
    except Exception as exc:
        results.append(f"ERROR: Mods dir not writable: {pz_mods_dir} ({exc})")

    return results
