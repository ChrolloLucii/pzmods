from __future__ import annotations

import subprocess
from pathlib import Path

from .models import WorkshopItem


class SteamCmdError(Exception):
    pass


def build_workshop_download_args(app_id: int, items: list[WorkshopItem], steam_username: str) -> list[str]:
    args = ["+login", steam_username]
    for item in items:
        args.extend(["+workshop_download_item", str(app_id), item.publishedfileid, "validate"])
    args.append("+quit")
    return args


def run_steamcmd_download(
    steamcmd_exe: Path,
    app_id: int,
    items: list[WorkshopItem],
    steam_username: str,
) -> None:
    if not steam_username.strip():
        raise SteamCmdError("Steam username is required for login.")

    cmd = [str(steamcmd_exe), *build_workshop_download_args(app_id, items, steam_username)]
    proc = subprocess.Popen(cmd)
    code = proc.wait()
    if code != 0:
        raise SteamCmdError(f"SteamCMD exited with status {code}.")
