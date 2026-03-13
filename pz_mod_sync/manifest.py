from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .models import InstallSection, Manifest, PzSection, SteamCmdSection, WorkshopItem


class ManifestError(Exception):
    pass


def _load_text(path_or_url: str) -> str:
    parsed = urlparse(path_or_url)
    if parsed.scheme in {"http", "https"}:
        if parsed.scheme != "https":
            raise ManifestError("Only HTTPS manifest URLs are allowed.")
        req = Request(path_or_url, headers={"User-Agent": "pz-mod-sync/0.1"})
        with urlopen(req, timeout=30) as resp:
            return resp.read().decode("utf-8")

    path = Path(path_or_url).expanduser().resolve()
    if not path.exists():
        raise ManifestError(f"Manifest file not found: {path}")
    return path.read_text(encoding="utf-8")


def load_manifest(path_or_url: str) -> Manifest:
    try:
        data = json.loads(_load_text(path_or_url))
    except json.JSONDecodeError as exc:
        raise ManifestError(f"Invalid JSON manifest: {exc}") from exc

    try:
        steam_section = data["steamcmd"]
        pz_section = data["project_zomboid"]
    except KeyError as exc:
        raise ManifestError(f"Missing required manifest field: {exc}") from exc

    items: list[WorkshopItem] = []
    for item in steam_section.get("workshop_items", []):
        pfid = str(item["publishedfileid"]).strip()
        if not pfid.isdigit():
            raise ManifestError(f"Invalid publishedfileid: {pfid}")
        items.append(WorkshopItem(publishedfileid=pfid, display_name=item.get("display_name")))

    if not items:
        raise ManifestError("Manifest must include at least one workshop item.")

    mods_to_enable = [str(x).strip() for x in pz_section.get("mods_to_enable", []) if str(x).strip()]
    if not mods_to_enable:
        raise ManifestError("Manifest must include at least one project_zomboid.mods_to_enable value.")

    install_raw = data.get("install", {})
    install_mode = str(install_raw.get("mode", "copy")).lower()
    if install_mode not in {"copy", "symlink"}:
        raise ManifestError("install.mode must be either 'copy' or 'symlink'.")

    manifest = Manifest(
        version=str(data.get("version", "")),
        name=str(data.get("name", "Unnamed Modpack")),
        updated_at=str(data.get("updated_at", "")),
        steamcmd=SteamCmdSection(app_id=int(steam_section.get("app_id", 108600)), workshop_items=items),
        project_zomboid=PzSection(mods_to_enable=mods_to_enable),
        install=InstallSection(
            mode=install_mode,
            pz_user_dir_override=str(install_raw.get("pz_user_dir_override", "")),
            allow_extra_local_mods=bool(install_raw.get("allow_extra_local_mods", True)),
        ),
    )
    return manifest
