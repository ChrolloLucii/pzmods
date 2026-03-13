from __future__ import annotations

import ctypes
import os
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
    run_as_admin: bool = False,
) -> int:
    cmd = [str(steamcmd_exe), *build_workshop_download_args(app_id, items, steam_username)]

    if run_as_admin and os.name == "nt":
        return _run_steamcmd_once_windows_admin(Path(cmd[0]), cmd[1:])

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


def _run_steamcmd_once_windows_admin(exe_path: Path, args: list[str]) -> int:
    SEE_MASK_NOCLOSEPROCESS = 0x00000040
    SW_SHOWNORMAL = 1
    INFINITE = 0xFFFFFFFF

    class SHELLEXECUTEINFOW(ctypes.Structure):
        _fields_ = [
            ("cbSize", ctypes.c_uint32),
            ("fMask", ctypes.c_ulong),
            ("hwnd", ctypes.c_void_p),
            ("lpVerb", ctypes.c_wchar_p),
            ("lpFile", ctypes.c_wchar_p),
            ("lpParameters", ctypes.c_wchar_p),
            ("lpDirectory", ctypes.c_wchar_p),
            ("nShow", ctypes.c_int),
            ("hInstApp", ctypes.c_void_p),
            ("lpIDList", ctypes.c_void_p),
            ("lpClass", ctypes.c_wchar_p),
            ("hkeyClass", ctypes.c_void_p),
            ("dwHotKey", ctypes.c_uint32),
            ("hIcon", ctypes.c_void_p),
            ("hProcess", ctypes.c_void_p),
        ]

    params = subprocess.list2cmdline(args)
    sei = SHELLEXECUTEINFOW()
    sei.cbSize = ctypes.sizeof(SHELLEXECUTEINFOW)
    sei.fMask = SEE_MASK_NOCLOSEPROCESS
    sei.hwnd = None
    sei.lpVerb = "runas"
    sei.lpFile = str(exe_path)
    sei.lpParameters = params
    sei.lpDirectory = str(exe_path.parent)
    sei.nShow = SW_SHOWNORMAL

    shell32 = ctypes.windll.shell32
    kernel32 = ctypes.windll.kernel32

    ok = shell32.ShellExecuteExW(ctypes.byref(sei))
    if not ok:
        err = ctypes.GetLastError()
        if err == 1223:
            raise SteamCmdError("UAC elevation cancelled by user.")
        raise SteamCmdError(f"Failed to start SteamCMD as admin. WinError={err}")

    try:
        kernel32.WaitForSingleObject(sei.hProcess, INFINITE)
        exit_code = ctypes.c_uint32()
        if kernel32.GetExitCodeProcess(sei.hProcess, ctypes.byref(exit_code)) == 0:
            err = ctypes.GetLastError()
            raise SteamCmdError(f"Failed to get SteamCMD exit code. WinError={err}")
        return int(exit_code.value)
    finally:
        if sei.hProcess:
            kernel32.CloseHandle(sei.hProcess)


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
    run_as_admin: bool = False,
) -> None:
    if not steam_username.strip():
        raise SteamCmdError("Steam username is required for login.")

    # Large one-shot command lines can make SteamCMD unstable on some systems.
    # Download in batches to reduce crashes and improve reliability.
    batch_size = len(items) if run_as_admin else 20
    failed_batches: list[tuple[list[WorkshopItem], int]] = []

    for batch in _chunks(items, batch_size):
        code = _run_steamcmd_once(steamcmd_exe, app_id, batch, steam_username, run_as_admin=run_as_admin)
        if code != 0:
            failed_batches.append((batch, code))

    if not failed_batches:
        return

    # Retry each failed batch once. Avoid item-by-item relaunch loops that can
    # repeatedly trigger Steam login/guard prompts and appear to hang.
    final_failed: list[tuple[list[WorkshopItem], int]] = []
    for batch, first_code in failed_batches:
        retry_code = _run_steamcmd_once(steamcmd_exe, app_id, batch, steam_username, run_as_admin=run_as_admin)
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
