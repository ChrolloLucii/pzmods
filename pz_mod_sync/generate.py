from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from .install import discover_mod_folders, parse_mod_id


@dataclass(slots=True)
class GeneratedManifestData:
    manifest: dict
    installed_modids: list[str]
    workshop_item_ids: list[str]
    unmatched_modids: list[str]


def discover_installed_modids(pz_mods_dir: Path) -> list[str]:
    if not pz_mods_dir.exists():
        return []

    modids: set[str] = set()
    for child in pz_mods_dir.iterdir():
        if not child.is_dir():
            continue
        mod_info = child / "mod.info"
        if not mod_info.exists():
            continue
        modid = parse_mod_id(mod_info)
        if modid:
            modids.add(modid)

    return sorted(modids, key=str.lower)


def build_workshop_modid_index(workshop_content_dir: Path) -> dict[str, set[str]]:
    index: dict[str, set[str]] = {}
    if not workshop_content_dir.exists():
        return index

    for child in workshop_content_dir.iterdir():
        if not child.is_dir() or not child.name.isdigit():
            continue
        item_id = child.name
        for modid, _mod_dir in discover_mod_folders(child):
            index.setdefault(modid, set()).add(item_id)
    return index


def generate_manifest_from_installed(
    pz_mods_dir: Path,
    workshop_content_dir: Path,
    name: str,
    app_id: int = 108600,
) -> GeneratedManifestData:
    installed_modids = discover_installed_modids(pz_mods_dir)
    index = build_workshop_modid_index(workshop_content_dir)

    workshop_ids_set: set[str] = set()
    unmatched: list[str] = []
    for modid in installed_modids:
        ids = index.get(modid)
        if not ids:
            unmatched.append(modid)
            continue
        workshop_ids_set.update(ids)

    workshop_item_ids = sorted(workshop_ids_set, key=lambda x: int(x))
    workshop_items = [{"publishedfileid": wid, "display_name": f"Workshop Item {wid}"} for wid in workshop_item_ids]

    manifest = {
        "version": "1",
        "name": name,
        "updated_at": str(date.today()),
        "steamcmd": {
            "app_id": app_id,
            "workshop_items": workshop_items,
        },
        "project_zomboid": {
            "mods_to_enable": installed_modids,
        },
        "install": {
            "mode": "copy",
            "pz_user_dir_override": "",
            "allow_extra_local_mods": True,
        },
    }

    return GeneratedManifestData(
        manifest=manifest,
        installed_modids=installed_modids,
        workshop_item_ids=workshop_item_ids,
        unmatched_modids=unmatched,
    )
