from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path


def parse_mod_id(mod_info_path: Path) -> str | None:
    try:
        for line in mod_info_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            stripped = line.strip()
            if stripped.lower().startswith("id="):
                modid = stripped.split("=", 1)[1].strip()
                return modid or None
    except OSError:
        return None
    return None


def discover_mod_folders(workshop_item_dir: Path) -> list[tuple[str, Path]]:
    variants: dict[str, list[Path]] = {}
    for mod_info in workshop_item_dir.rglob("mod.info"):
        mod_dir = mod_info.parent
        mod_id = parse_mod_id(mod_info)
        if mod_id:
            variants.setdefault(mod_id, []).append(mod_dir)

    selected: dict[str, Path] = {}
    for mod_id, dirs in variants.items():
        unique_dirs = sorted(set(dirs), key=lambda p: (len(p.parts), p.as_posix().lower()))
        if len(unique_dirs) == 1:
            selected[mod_id] = unique_dirs[0]
            continue

        # 1) Prefer a path that is an ancestor of all other variant dirs.
        ancestor_candidates = [
            cand
            for cand in unique_dirs
            if all(other == cand or other.is_relative_to(cand) for other in unique_dirs)
        ]
        if ancestor_candidates:
            selected[mod_id] = sorted(
                ancestor_candidates,
                key=lambda p: len(p.relative_to(workshop_item_dir).parts),
            )[0]
            continue

        # 2) If variants are sibling version folders (42, 42.13, common), install
        #    their shared parent so the whole mod layout is preserved.
        common_parent = unique_dirs[0].parent
        if all(p.parent == common_parent for p in unique_dirs):
            selected[mod_id] = common_parent
            continue

        # 3) Fallback: pick shallowest path.
        selected[mod_id] = sorted(
            unique_dirs,
            key=lambda p: len(p.relative_to(workshop_item_dir).parts),
        )[0]

    return sorted(selected.items(), key=lambda x: x[0].lower())


def _signature_for_dir(path: Path) -> str:
    h = hashlib.sha256()
    files = sorted([p for p in path.rglob("*") if p.is_file()], key=lambda p: p.as_posix().lower())
    for file in files:
        rel = file.relative_to(path).as_posix()
        st = file.stat()
        h.update(rel.encode("utf-8", errors="ignore"))
        h.update(str(st.st_size).encode())
        h.update(str(int(st.st_mtime)).encode())
    return h.hexdigest()


def _meta_path(dest_mod_dir: Path) -> Path:
    return dest_mod_dir / ".pzmods-meta.json"


def _read_meta(dest_mod_dir: Path) -> dict | None:
    meta = _meta_path(dest_mod_dir)
    if not meta.exists():
        return None
    try:
        raw = json.loads(meta.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else None
    except Exception:
        return None


def _read_signature(dest_mod_dir: Path) -> str | None:
    meta = _read_meta(dest_mod_dir)
    if not meta:
        return None
    sig = meta.get("source_signature")
    return str(sig) if sig is not None else None


def _write_meta(
    dest_mod_dir: Path,
    signature: str,
    *,
    mod_id: str,
    workshop_item_id: str | None = None,
    source_mod_dir: Path | None = None,
) -> None:
    payload: dict[str, str] = {
        "source_signature": signature,
        "mod_id": mod_id,
    }
    if workshop_item_id:
        payload["workshop_item_id"] = workshop_item_id
    if source_mod_dir is not None:
        payload["source_mod_dir"] = str(source_mod_dir)
    _meta_path(dest_mod_dir).write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _find_mod_id_recursively(source_mod_dir: Path, expected_mod_id: str | None = None) -> str | None:
    found: list[str] = []
    for mod_info in source_mod_dir.rglob("mod.info"):
        mid = parse_mod_id(mod_info)
        if not mid:
            continue
        if expected_mod_id and mid == expected_mod_id:
            return mid
        found.append(mid)
    return found[0] if found else None


def install_mod_folder(
    source_mod_dir: Path,
    target_mods_dir: Path,
    mode: str = "copy",
    mod_id_override: str | None = None,
    workshop_item_id: str | None = None,
) -> tuple[bool, str]:
    target_mods_dir.mkdir(parents=True, exist_ok=True)

    mod_id = mod_id_override or parse_mod_id(source_mod_dir / "mod.info")
    if not mod_id:
        mod_id = _find_mod_id_recursively(source_mod_dir, expected_mod_id=mod_id_override)
    if not mod_id:
        raise ValueError(f"No valid mod.info ID found in {source_mod_dir}")

    destination = target_mods_dir / mod_id
    source_sig = _signature_for_dir(source_mod_dir)
    current_sig = _read_signature(destination) if destination.exists() and destination.is_dir() else None
    if current_sig == source_sig:
        return False, mod_id

    if mode == "symlink":
        if destination.is_symlink() and destination.resolve() == source_mod_dir.resolve():
            return False, mod_id
        if destination.exists() or destination.is_symlink():
            if destination.is_dir() and not destination.is_symlink():
                shutil.rmtree(destination)
            else:
                destination.unlink(missing_ok=True)
        os.symlink(source_mod_dir, destination, target_is_directory=True)
        return True, mod_id

    with tempfile.TemporaryDirectory(prefix=f"pzmods-{mod_id}-", dir=target_mods_dir.parent) as tmp:
        temp_dest = Path(tmp) / mod_id
        shutil.copytree(source_mod_dir, temp_dest)
        _write_meta(
            temp_dest,
            source_sig,
            mod_id=mod_id,
            workshop_item_id=workshop_item_id,
            source_mod_dir=source_mod_dir,
        )
        if destination.exists():
            shutil.rmtree(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        os.replace(temp_dest, destination)

    return True, mod_id


def validate_required_modids(mods_dir: Path, required_modids: list[str]) -> list[str]:
    installed_modids: set[str] = set()
    if mods_dir.exists():
        for mod_info in mods_dir.rglob("mod.info"):
            mid = parse_mod_id(mod_info)
            if mid:
                installed_modids.add(mid)

    missing: list[str] = []
    for modid in required_modids:
        if modid not in installed_modids:
            missing.append(modid)
    return missing
