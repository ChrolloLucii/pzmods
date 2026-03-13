from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path


@dataclass(slots=True)
class UserConfig:
    steamcmd_path: str = ""
    steam_username: str = ""
    pz_user_dir: str = ""
    download_cache_dir: str = ""
    last_manifest: str = ""


def _config_path(app_data_dir: Path) -> Path:
    return app_data_dir / "config.json"


def load_user_config(app_data_dir: Path) -> UserConfig:
    path = _config_path(app_data_dir)
    if not path.exists():
        return UserConfig()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return UserConfig(**{k: data.get(k, "") for k in UserConfig.__dataclass_fields__.keys()})
    except Exception:
        return UserConfig()


def save_user_config(app_data_dir: Path, config: UserConfig) -> None:
    app_data_dir.mkdir(parents=True, exist_ok=True)
    path = _config_path(app_data_dir)
    path.write_text(json.dumps(asdict(config), indent=2), encoding="utf-8")
