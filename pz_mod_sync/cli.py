from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .collection import (
    CollectionError,
    fetch_collection_children,
    fetch_workshop_item_titles,
    normalize_collection_id,
    normalize_workshop_item_id,
)
from .config import UserConfig, load_user_config, save_user_config
from .generate import generate_manifest_from_installed
from .logging_utils import report_to_json, setup_logging
from .manifest_utils import merge_workshop_items
from .manifest import ManifestError, load_manifest
from .paths import detect_app_data_dir, detect_pz_user_dir, detect_steamcmd_path, workshop_dir_from_steamcmd
from .sync import run_doctor, run_sync, run_validate


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pzmods", description="Project Zomboid mod sync via SteamCMD")
    sub = parser.add_subparsers(dest="command", required=True)

    sync_cmd = sub.add_parser("sync", help="Download/update and install modpack")
    sync_cmd.add_argument("--manifest", required=True, help="Manifest path or HTTPS URL")
    sync_cmd.add_argument("--steamcmd", default="", help="Path to steamcmd executable")
    sync_cmd.add_argument("--steam-user", default="", help="Steam username (password entered in SteamCMD)")
    sync_cmd.add_argument("--pzdir", default="", help="Project Zomboid user dir override")
    sync_cmd.add_argument("--cache", default="", help="Workshop content dir override")
    sync_cmd.add_argument("--install-mode", choices=["copy", "symlink"], default="", help="Install mode override")
    sync_cmd.add_argument(
        "--download-mode",
        choices=["always", "missing-only", "none"],
        default="always",
        help="SteamCMD behavior: always update all, only missing items, or skip download step",
    )
    sync_cmd.add_argument(
        "--steamcmd-admin",
        action="store_true",
        help="Run SteamCMD with Windows UAC elevation (Run as Administrator)",
    )

    validate_cmd = sub.add_parser("validate", help="Validate required ModIDs are present")
    validate_cmd.add_argument("--manifest", required=True, help="Manifest path or HTTPS URL")
    validate_cmd.add_argument("--pzdir", default="", help="Project Zomboid user dir override")

    doctor_cmd = sub.add_parser("doctor", help="Check SteamCMD and local paths")
    doctor_cmd.add_argument("--steamcmd", default="", help="Path to steamcmd executable")
    doctor_cmd.add_argument("--pzdir", default="", help="Project Zomboid user dir override")

    sub.add_parser("print-paths", help="Print auto-detected paths")

    coll_cmd = sub.add_parser("parse-collection", help="Convert Steam Workshop collection to manifest")
    coll_cmd.add_argument("--collection", required=True, help="Collection URL or ID")
    coll_cmd.add_argument("--out", default="pz-modpack.generated.json", help="Output manifest path")
    coll_cmd.add_argument("--name", default="Generated from Steam Collection", help="Manifest display name")

    merge_coll_cmd = sub.add_parser("merge-collection", help="Append collection workshop items into existing local manifest")
    merge_coll_cmd.add_argument("--manifest", required=True, help="Local manifest JSON path")
    merge_coll_cmd.add_argument("--collection", required=True, help="Collection URL or ID")

    add_item_cmd = sub.add_parser("add-workshop-item", help="Append a Steam Workshop item URL/ID to local manifest")
    add_item_cmd.add_argument("--manifest", required=True, help="Local manifest JSON path")
    add_item_cmd.add_argument("--item", required=True, help="Workshop item URL or ID")

    gen_cmd = sub.add_parser("generate-manifest", help="Generate manifest from currently installed mods")
    gen_cmd.add_argument("--out", default="pz-modpack.from-installed.json", help="Output manifest path")
    gen_cmd.add_argument("--name", default="Generated from installed mods", help="Manifest display name")
    gen_cmd.add_argument("--pzdir", default="", help="Project Zomboid user dir override")
    gen_cmd.add_argument("--cache", default="", help="Workshop content dir override")
    gen_cmd.add_argument("--app-id", default=108600, type=int, help="Steam app id (default: 108600)")
    gen_cmd.add_argument(
        "--include-unmatched-modids",
        action="store_true",
        help="Also include local ModIDs that could not be mapped to Workshop items",
    )
    return parser


def _resolve_runtime(args: argparse.Namespace, config: UserConfig):
    app_data_dir = detect_app_data_dir()

    steamcmd = detect_steamcmd_path(args.steamcmd or config.steamcmd_path)
    pz_user = detect_pz_user_dir(getattr(args, "pzdir", "") or config.pz_user_dir)
    pz_mods = pz_user / "mods"

    return app_data_dir, steamcmd, pz_user, pz_mods


def cmd_sync(args: argparse.Namespace) -> int:
    app_data_dir = detect_app_data_dir()
    config = load_user_config(app_data_dir)
    logger = setup_logging(app_data_dir / "logs")

    try:
        manifest = load_manifest(args.manifest)
    except ManifestError as exc:
        print(f"Manifest error: {exc}")
        return 2

    _, steamcmd, pz_user, pz_mods = _resolve_runtime(args, config)
    if not steamcmd:
        print("SteamCMD not found. Use --steamcmd or set config.steamcmd_path.")
        return 2

    install_mode = args.install_mode or manifest.install.mode
    steam_user = args.steam_user or config.steam_username
    if not steam_user:
        steam_user = input("Steam username: ").strip()
    if not steam_user:
        print("Steam username is required.")
        return 2

    workshop_dir = Path(args.cache).expanduser().resolve() if args.cache else workshop_dir_from_steamcmd(steamcmd, manifest.steamcmd.app_id)

    report = run_sync(
        manifest=manifest,
        steamcmd_exe=steamcmd,
        workshop_content_dir=workshop_dir,
        pz_mods_dir=pz_mods,
        steam_username=steam_user,
        install_mode=install_mode,
        logger=logger,
        download_mode=args.download_mode,
        steamcmd_admin=bool(args.steamcmd_admin),
    )

    config.steamcmd_path = str(steamcmd)
    config.steam_username = steam_user
    config.pz_user_dir = str(pz_user)
    config.download_cache_dir = str(workshop_dir)
    config.last_manifest = args.manifest
    save_user_config(app_data_dir, config)

    print(report_to_json(report))
    if report.errors or report.missing_modids:
        return 1
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    app_data_dir = detect_app_data_dir()
    config = load_user_config(app_data_dir)

    try:
        manifest = load_manifest(args.manifest)
    except ManifestError as exc:
        print(f"Manifest error: {exc}")
        return 2

    pz_user = detect_pz_user_dir(args.pzdir or config.pz_user_dir or manifest.install.pz_user_dir_override)
    report = run_validate(manifest, pz_user / "mods")
    print(report_to_json(report))
    return 1 if report.missing_modids else 0


def cmd_doctor(args: argparse.Namespace) -> int:
    app_data_dir = detect_app_data_dir()
    config = load_user_config(app_data_dir)
    _, steamcmd, pz_user, pz_mods = _resolve_runtime(args, config)

    lines = run_doctor(steamcmd, pz_user, pz_mods)
    for line in lines:
        print(line)

    return 1 if any(line.startswith("ERROR") for line in lines) else 0


def cmd_print_paths() -> int:
    app_data_dir = detect_app_data_dir()
    config = load_user_config(app_data_dir)
    steamcmd = detect_steamcmd_path(config.steamcmd_path)
    pz_user = detect_pz_user_dir(config.pz_user_dir)

    print(f"app_data_dir={app_data_dir}")
    print(f"steamcmd={steamcmd}")
    print(f"pz_user_dir={pz_user}")
    print(f"pz_mods_dir={pz_user / 'mods'}")
    return 0


def cmd_parse_collection(args: argparse.Namespace) -> int:
    try:
        collection_id = normalize_collection_id(args.collection)
        item_ids = fetch_collection_children(collection_id)
        titles = fetch_workshop_item_titles(item_ids)
    except CollectionError as exc:
        print(f"Collection error: {exc}")
        return 2
    except Exception as exc:
        print(f"Collection fetch failed: {exc}")
        return 2

    workshop_items = [
        {
            "publishedfileid": item_id,
            "display_name": titles.get(item_id, f"Workshop Item {item_id}"),
        }
        for item_id in item_ids
    ]

    manifest = {
        "version": "1",
        "name": args.name,
        "updated_at": "",
        "steamcmd": {
            "app_id": 108600,
            "workshop_items": workshop_items,
        },
        "project_zomboid": {
            "mods_to_enable": [
                "REPLACE_WITH_REAL_MODIDS_AFTER_SYNC"
            ]
        },
        "install": {
            "mode": "copy",
            "pz_user_dir_override": "",
            "allow_extra_local_mods": True,
        },
    }

    out_path = Path(args.out).expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Collection ID: {collection_id}")
    print(f"Workshop items: {len(item_ids)}")
    print(f"Saved manifest: {out_path}")
    return 0


def cmd_add_workshop_item(args: argparse.Namespace) -> int:
    try:
        item_id = normalize_workshop_item_id(args.item)
    except CollectionError as exc:
        print(f"Workshop item error: {exc}")
        return 2

    manifest_path = Path(args.manifest).expanduser().resolve()
    if not manifest_path.exists():
        print(f"Manifest not found: {manifest_path}")
        return 2

    try:
        manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"Failed to read manifest JSON: {exc}")
        return 2

    steam_section = manifest_data.setdefault("steamcmd", {})
    workshop_items = steam_section.setdefault("workshop_items", [])
    existing_ids = {str(x.get("publishedfileid", "")).strip() for x in workshop_items if isinstance(x, dict)}
    if item_id in existing_ids:
        print(f"Already exists in manifest: {item_id}")
        return 0

    try:
        title = fetch_workshop_item_titles([item_id]).get(item_id, f"Workshop Item {item_id}")
    except Exception:
        title = f"Workshop Item {item_id}"
    workshop_items.append({"publishedfileid": item_id, "display_name": title})

    steam_section.setdefault("app_id", 108600)
    manifest_data.setdefault("version", "1")
    manifest_data.setdefault("name", "PZ Modpack")
    manifest_data.setdefault("updated_at", "")
    manifest_data.setdefault("project_zomboid", {}).setdefault("mods_to_enable", ["REPLACE_WITH_REAL_MODIDS_AFTER_SYNC"])
    manifest_data.setdefault(
        "install",
        {
            "mode": "copy",
            "pz_user_dir_override": "",
            "allow_extra_local_mods": True,
        },
    )

    manifest_path.write_text(json.dumps(manifest_data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Added workshop item: {item_id}")
    print(f"Manifest updated: {manifest_path}")
    return 0


def cmd_merge_collection(args: argparse.Namespace) -> int:
    manifest_path = Path(args.manifest).expanduser().resolve()
    if not manifest_path.exists():
        print(f"Manifest not found: {manifest_path}")
        return 2

    try:
        collection_id = normalize_collection_id(args.collection)
        item_ids = fetch_collection_children(collection_id)
        titles = fetch_workshop_item_titles(item_ids)
    except CollectionError as exc:
        print(f"Collection error: {exc}")
        return 2
    except Exception as exc:
        print(f"Collection fetch failed: {exc}")
        return 2

    try:
        manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"Failed to read manifest JSON: {exc}")
        return 2

    incoming_items = [
        {
            "publishedfileid": item_id,
            "display_name": titles.get(item_id, f"Workshop Item {item_id}"),
        }
        for item_id in item_ids
    ]

    steam_section = manifest_data.setdefault("steamcmd", {})
    steam_section.setdefault("app_id", 108600)
    existing = steam_section.setdefault("workshop_items", [])
    merged, added = merge_workshop_items(existing, incoming_items)
    steam_section["workshop_items"] = merged

    manifest_data.setdefault("version", "1")
    manifest_data.setdefault("name", "PZ Modpack")
    manifest_data.setdefault("updated_at", "")
    manifest_data.setdefault("project_zomboid", {}).setdefault("mods_to_enable", ["REPLACE_WITH_REAL_MODIDS_AFTER_SYNC"])
    manifest_data.setdefault(
        "install",
        {
            "mode": "copy",
            "pz_user_dir_override": "",
            "allow_extra_local_mods": True,
        },
    )

    manifest_path.write_text(json.dumps(manifest_data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Collection ID: {collection_id}")
    print(f"Collection items fetched: {len(item_ids)}")
    print(f"Added to manifest: {added}")
    print(f"Total workshop items in manifest: {len(merged)}")
    print(f"Manifest updated: {manifest_path}")
    return 0


def cmd_generate_manifest(args: argparse.Namespace) -> int:
    app_data_dir = detect_app_data_dir()
    config = load_user_config(app_data_dir)

    pz_user = detect_pz_user_dir(args.pzdir or config.pz_user_dir)
    pz_mods = pz_user / "mods"

    steamcmd = detect_steamcmd_path(config.steamcmd_path)
    if args.cache:
        workshop_dir = Path(args.cache).expanduser().resolve()
    elif config.download_cache_dir:
        workshop_dir = Path(config.download_cache_dir).expanduser().resolve()
    elif steamcmd:
        workshop_dir = workshop_dir_from_steamcmd(steamcmd, args.app_id)
    else:
        workshop_dir = Path(".")

    data = generate_manifest_from_installed(
        pz_mods_dir=pz_mods,
        workshop_content_dir=workshop_dir,
        name=args.name,
        app_id=args.app_id,
        include_unmatched_modids=bool(args.include_unmatched_modids),
    )

    if not data.installed_modids:
        print(f"No installed mods found in: {pz_mods}")
        return 1

    out_path = Path(args.out).expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(data.manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Installed ModIDs: {len(data.installed_modids)}")
    print(f"Matched ModIDs: {len(data.matched_modids)}")
    print(f"Mapped workshop items: {len(data.workshop_item_ids)}")
    if data.unmatched_modids:
        print(f"Unmatched local ModIDs (likely local/non-workshop mods): {len(data.unmatched_modids)}")
    print(f"Saved manifest: {out_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "sync":
        return cmd_sync(args)
    if args.command == "validate":
        return cmd_validate(args)
    if args.command == "doctor":
        return cmd_doctor(args)
    if args.command == "print-paths":
        return cmd_print_paths()
    if args.command == "parse-collection":
        return cmd_parse_collection(args)
    if args.command == "add-workshop-item":
        return cmd_add_workshop_item(args)
    if args.command == "merge-collection":
        return cmd_merge_collection(args)
    if args.command == "generate-manifest":
        return cmd_generate_manifest(args)

    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
