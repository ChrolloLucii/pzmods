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
    try:
        return proc.wait()
    except KeyboardInterrupt as exc:
        try:
            proc.terminate()
        except Exception:
            pass
        raise SteamCmdError("SteamCMD interrupted by user.") from exc


def _format_exit_code(code: int) -> str:
    if code < 0:
        return str(code)
    return f"{code} (0x{code:08X})"


def _looks_like_windows_crash(code: int) -> bool:
    return code >= 0xC0000000


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
    failed_batches: list[tuple[list[WorkshopItem], int]] = []

    for batch in _chunks(items, batch_size):
        code = _run_steamcmd_once(steamcmd_exe, app_id, batch, steam_username)
        if code != 0:
            failed_batches.append((batch, code))

    if not failed_batches:
        return

    # Retry each failed batch once. Avoid item-by-item relaunch loops that can
    # repeatedly trigger Steam login/guard prompts and appear to hang.
    final_failed: list[tuple[list[WorkshopItem], int]] = []
    for batch, first_code in failed_batches:
        retry_code = _run_steamcmd_once(steamcmd_exe, app_id, batch, steam_username)
        if retry_code != 0:
            final_failed.append((batch, retry_code))
        elif _looks_like_windows_crash(first_code):
            # Crash recovered on retry; continue.
            continue

    if final_failed:
        failed_ids = [item.publishedfileid for batch, _ in final_failed for item in batch]
        last_code = final_failed[-1][1]
        raise SteamCmdError(
            "SteamCMD failed after retry. "
            f"last status={_format_exit_code(last_code)}; failed_items={len(failed_ids)}; ids={','.join(failed_ids)}"
        )
