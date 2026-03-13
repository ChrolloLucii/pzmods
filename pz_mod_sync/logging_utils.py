from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from .models import SyncReport


def setup_logging(logs_dir: Path) -> logging.Logger:
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_file = logs_dir / f"pzmods-{datetime.now().strftime('%Y%m%d-%H%M%S')}.log"

    logger = logging.getLogger("pz_mod_sync")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter("%(message)s"))

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))

    logger.addHandler(console)
    logger.addHandler(file_handler)
    logger.info("Log file: %s", log_file)
    return logger


def report_to_json(report: SyncReport) -> str:
    return json.dumps(
        {
            "downloaded_items": report.downloaded_items,
            "installed_mods": report.installed_mods,
            "skipped_mods": report.skipped_mods,
            "missing_modids": report.missing_modids,
            "warnings": report.warnings,
            "errors": report.errors,
        },
        indent=2,
    )
