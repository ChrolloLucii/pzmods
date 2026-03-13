from __future__ import annotations

import subprocess
from pathlib import Path

from .models import WorkshopItem


class SteamCmdError(Exception):
    pass


def _chunks(items: list[WorkshopItem], size: int) -> list[list[WorkshopItem]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def _run_steamcmd_once(
    steamcmd_exe: Path,
    app_id: int,
    items: list[WorkshopItem],
    steam_username: str,
) -> int:
    cmd = [str(steamcmd_exe), *build_workshop_download_args(app_id, items, steam_username)]
    proc = subprocess.Popen(cmd)
    return proc.wait()


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

    # Large one-shot command lines can make SteamCMD unstable on some systems.
    # Download in batches to reduce crashes and improve reliability.
    batch_size = 20
    failed_batches: list[list[WorkshopItem]] = []

    for batch in _chunks(items, batch_size):
        code = _run_steamcmd_once(steamcmd_exe, app_id, batch, steam_username)
        if code != 0:
            failed_batches.append(batch)

    if not failed_batches:
        return

    # Retry failed batches item-by-item to recover from transient SteamCMD crashes.
    failed_item_ids: list[str] = []
    last_code: int | None = None
    for batch in failed_batches:
        for item in batch:
            code = _run_steamcmd_once(steamcmd_exe, app_id, [item], steam_username)
            if code != 0:
                failed_item_ids.append(item.publishedfileid)
                last_code = code

    if failed_item_ids:
        raise SteamCmdError(
            f"SteamCMD failed for {len(failed_item_ids)} item(s), last status {last_code}, ids={','.join(failed_item_ids)}"
        )
