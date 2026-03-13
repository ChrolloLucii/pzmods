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
    mods: dict[str, Path] = {}
    for mod_info in workshop_item_dir.rglob("mod.info"):
        mod_dir = mod_info.parent
        mod_id = parse_mod_id(mod_info)
        if mod_id:
            mods[mod_id] = mod_dir
    return sorted(mods.items(), key=lambda x: x[0].lower())


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


def _read_signature(dest_mod_dir: Path) -> str | None:
    meta = _meta_path(dest_mod_dir)
    if not meta.exists():
        return None
    try:
        return str(json.loads(meta.read_text(encoding="utf-8")).get("source_signature"))
    except Exception:
        return None


def _write_signature(dest_mod_dir: Path, signature: str) -> None:
    _meta_path(dest_mod_dir).write_text(json.dumps({"source_signature": signature}, indent=2), encoding="utf-8")


def install_mod_folder(source_mod_dir: Path, target_mods_dir: Path, mode: str = "copy") -> tuple[bool, str]:
    target_mods_dir.mkdir(parents=True, exist_ok=True)

    mod_id = parse_mod_id(source_mod_dir / "mod.info")
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
        _write_signature(temp_dest, source_sig)
        if destination.exists():
            shutil.rmtree(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        os.replace(temp_dest, destination)

    return True, mod_id


def validate_required_modids(mods_dir: Path, required_modids: list[str]) -> list[str]:
    missing: list[str] = []
    for modid in required_modids:
        mod_path = mods_dir / modid
        if not mod_path.exists() or not (mod_path / "mod.info").exists():
            missing.append(modid)
    return missing
