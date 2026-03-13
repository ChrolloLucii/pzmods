from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class WorkshopItem:
    publishedfileid: str
    display_name: str | None = None


@dataclass(slots=True)
class SteamCmdSection:
    app_id: int
    workshop_items: list[WorkshopItem]


@dataclass(slots=True)
class PzSection:
    mods_to_enable: list[str]


@dataclass(slots=True)
class InstallSection:
    mode: str = "copy"
    pz_user_dir_override: str = ""
    allow_extra_local_mods: bool = True


@dataclass(slots=True)
class Manifest:
    version: str
    name: str
    updated_at: str
    steamcmd: SteamCmdSection
    project_zomboid: PzSection
    install: InstallSection = field(default_factory=InstallSection)


@dataclass(slots=True)
class SyncPaths:
    steamcmd_exe: Path
    pz_user_dir: Path
    pz_mods_dir: Path
    workshop_content_dir: Path
    app_data_dir: Path
    logs_dir: Path


@dataclass(slots=True)
class SyncReport:
    downloaded_items: list[str] = field(default_factory=list)
    installed_mods: list[str] = field(default_factory=list)
    skipped_mods: list[str] = field(default_factory=list)
    missing_modids: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
