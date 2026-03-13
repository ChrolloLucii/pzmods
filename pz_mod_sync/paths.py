from __future__ import annotations

import os
import platform
from pathlib import Path


def get_user_home() -> Path:
    return Path.home()


def detect_pz_user_dir(override: str | None = None) -> Path:
    if override:
        return Path(override).expanduser().resolve()

    system = platform.system().lower()
    home = get_user_home()
    if system == "windows":
        return (home / "Zomboid").resolve()
    if system == "linux":
        return (home / "Zomboid").resolve()
    if system == "darwin":
        return (home / "Zomboid").resolve()
    return (home / "Zomboid").resolve()


def detect_app_data_dir() -> Path:
    system = platform.system().lower()
    home = get_user_home()

    if system == "windows":
        appdata = os.environ.get("APPDATA")
        base = Path(appdata) if appdata else home / "AppData" / "Roaming"
        return (base / "pz-mod-sync").resolve()
    if system == "darwin":
        return (home / "Library" / "Application Support" / "pz-mod-sync").resolve()
    return (home / ".local" / "share" / "pz-mod-sync").resolve()


def detect_steamcmd_path(explicit: str | None = None) -> Path | None:
    if explicit:
        path = Path(explicit).expanduser().resolve()
        return path if path.exists() else None

    system = platform.system().lower()
    candidates: list[Path] = []

    if system == "windows":
        candidates.extend(
            [
                Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)")) / "SteamCMD" / "steamcmd.exe",
                Path("C:/steamcmd/steamcmd.exe"),
                Path.home() / "steamcmd" / "steamcmd.exe",
            ]
        )
    else:
        candidates.extend([Path.home() / "steamcmd" / "steamcmd.sh", Path("/usr/games/steamcmd")])

    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()

    return None


def workshop_dir_from_steamcmd(steamcmd_exe: Path, app_id: int) -> Path:
    root = steamcmd_exe.parent
    return (root / "steamapps" / "workshop" / "content" / str(app_id)).resolve()
