from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import json
from pathlib import Path
import re

from .install import discover_mod_folders, parse_mod_id


_WORKSHOP_INDEX_CACHE_FILE = ".pzmods-workshop-index.json"


@dataclass(slots=True)
class GeneratedManifestData:
    manifest: dict
    installed_modids: list[str]
    matched_modids: list[str]
    workshop_item_ids: list[str]
    unmatched_modids: list[str]


def build_installed_meta_index(pz_mods_dir: Path) -> dict[str, set[str]]:
    index: dict[str, set[str]] = {}
    if not pz_mods_dir.exists():
        return index

    for child in pz_mods_dir.iterdir():
        if not child.is_dir():
            continue
        meta = child / ".pzmods-meta.json"
        if not meta.exists():
            continue
        try:
            raw = json.loads(meta.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(raw, dict):
            continue
        mod_id = str(raw.get("mod_id", "")).strip()
        workshop_item_id = str(raw.get("workshop_item_id", "")).strip()
        if mod_id and workshop_item_id.isdigit():
            index.setdefault(mod_id, set()).add(workshop_item_id)
    return index


def discover_installed_modids(pz_mods_dir: Path) -> list[str]:
    if not pz_mods_dir.exists():
        return []

    modids: set[str] = set()
    for child in pz_mods_dir.iterdir():
        if not child.is_dir():
            continue
        for mod_info in child.rglob("mod.info"):
            modid = parse_mod_id(mod_info)
            if modid:
                modids.add(modid)

    return sorted(modids, key=str.lower)


_WORKSHOP_ID_RE = re.compile(r"(?:sharedfiles|workshop)/filedetails/\?id=(\d+)", re.IGNORECASE)


def _extract_primary_workshop_id_from_folder(mod_folder: Path) -> str | None:
    candidates = list(mod_folder.rglob("workshopPage.txt")) + list(mod_folder.rglob("workshoppage.txt"))
    if not candidates:
        return None

    counts: dict[str, int] = {}
    order: list[str] = []
    for file in candidates:
        try:
            text = file.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for m in _WORKSHOP_ID_RE.finditer(text):
            wid = m.group(1)
            if wid not in counts:
                counts[wid] = 0
                order.append(wid)
            counts[wid] += 1

    if not counts:
        return None
    # Most frequent id in workshopPage files is usually the main mod page.
    best_count = max(counts.values())
    best_ids = {wid for wid, c in counts.items() if c == best_count}
    for wid in order:
        if wid in best_ids:
            return wid
    return None


def build_local_workshop_hint_index(pz_mods_dir: Path, target_modids: set[str] | None = None) -> dict[str, set[str]]:
    index: dict[str, set[str]] = {}
    if not pz_mods_dir.exists():
        return index

    for child in pz_mods_dir.iterdir():
        if not child.is_dir():
            continue
        hinted_workshop_id = _extract_primary_workshop_id_from_folder(child)
        if not hinted_workshop_id:
            continue

        folder_modids: set[str] = set()
        for mod_info in child.rglob("mod.info"):
            modid = parse_mod_id(mod_info)
            if modid:
                if target_modids is not None and modid not in target_modids:
                    continue
                folder_modids.add(modid)

        for modid in folder_modids:
            index.setdefault(modid, set()).add(hinted_workshop_id)
    return index


def build_workshop_modid_index(workshop_content_dir: Path, target_modids: set[str] | None = None) -> dict[str, set[str]]:
    index: dict[str, set[str]] = {}
    if not workshop_content_dir.exists():
        return index

    cache_path = workshop_content_dir / _WORKSHOP_INDEX_CACHE_FILE
    cache_items: dict[str, dict] = {}
    cache_dirty = False
    try:
        if cache_path.exists():
            raw = json.loads(cache_path.read_text(encoding="utf-8"))
            cache_items = dict((raw or {}).get("items") or {})
    except Exception:
        cache_items = {}

    seen_item_ids: set[str] = set()

    for child in workshop_content_dir.iterdir():
        if not child.is_dir() or not child.name.isdigit():
            continue
        item_id = child.name
        seen_item_ids.add(item_id)

        dir_mtime = int(child.stat().st_mtime)
        cached = cache_items.get(item_id)
        cached_mtime = int(cached.get("mtime", -1)) if isinstance(cached, dict) else -1
        if isinstance(cached, dict) and cached_mtime == dir_mtime:
            modids = [str(x) for x in (cached.get("modids") or []) if str(x).strip()]
        else:
            modids = sorted({modid for modid, _mod_dir in discover_mod_folders(child)}, key=str.lower)
            cache_items[item_id] = {
                "mtime": dir_mtime,
                "modids": modids,
            }
            cache_dirty = True

        for modid in modids:
            if target_modids is not None and modid not in target_modids:
                continue
            index.setdefault(modid, set()).add(item_id)

    # Remove stale cache records for workshop items that no longer exist.
    stale_ids = [item_id for item_id in list(cache_items.keys()) if item_id not in seen_item_ids]
    if stale_ids:
        for item_id in stale_ids:
            cache_items.pop(item_id, None)
        cache_dirty = True

    if cache_dirty:
        payload = {
            "version": 1,
            "items": cache_items,
        }
        tmp_path = cache_path.with_suffix(cache_path.suffix + ".tmp")
        tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp_path.replace(cache_path)

    return index


def generate_manifest_from_installed(
    pz_mods_dir: Path,
    workshop_content_dir: Path,
    name: str,
    app_id: int = 108600,
    include_unmatched_modids: bool = False,
) -> GeneratedManifestData:
    installed_modids = discover_installed_modids(pz_mods_dir)
    meta_index = build_installed_meta_index(pz_mods_dir)

    unresolved = {modid for modid in installed_modids if modid not in meta_index}
    if unresolved:
        index = build_workshop_modid_index(workshop_content_dir, target_modids=unresolved)
        local_hints = build_local_workshop_hint_index(pz_mods_dir, target_modids=unresolved)
    else:
        index = {}
        local_hints = {}

    workshop_ids_set: set[str] = set()
    matched: list[str] = []
    unmatched: list[str] = []
    for modid in installed_modids:
        ids = meta_index.get(modid) or index.get(modid) or local_hints.get(modid)
        if not ids:
            unmatched.append(modid)
            continue
        matched.append(modid)
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
            "mods_to_enable": installed_modids if include_unmatched_modids else matched,
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
        matched_modids=matched,
        workshop_item_ids=workshop_item_ids,
        unmatched_modids=unmatched,
    )
