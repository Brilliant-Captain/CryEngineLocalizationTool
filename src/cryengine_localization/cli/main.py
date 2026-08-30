"""Command-line entry points for the localization toolkit."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from cryengine_localization import __version__
from cryengine_localization.adapters.cryengine import identify_project
from cryengine_localization.adapters.pak import build_pak, extract_pak, scan_pak
from cryengine_localization.adapters.gfxfont import (
    inspect_font_coverage,
    replace_font_slots,
    scan_gfx_fonts,
    subset_font,
)
from cryengine_localization.adapters.textures import (
    encode_image_file_to_dds,
    parse_dds_header,
    replace_texture_in_pak,
)
from cryengine_localization.adapters.war_of_rights import preview_language_config, write_language_config
from cryengine_localization.core.apply import apply_catalog_to_pak, plan_translation_changes
from cryengine_localization.core.manifest import build_manifest, sha256_file, write_manifest
from cryengine_localization.core.install import (
    InstallItem,
    install_files,
    plan_install,
    read_install_record,
    rollback_install,
    record_to_dict,
    write_install_record,
)
from cryengine_localization.core.tools import discover_tools
from cryengine_localization.core.profile import ProjectProfile, load_profile, save_profile
from cryengine_localization.core.workflow import (
    build_profile,
    catalog_from_pak,
    export_profile_catalog,
    install_profile,
    plan_profile_changes,
    plan_profile_install,
    rollback_profile,
)
from cryengine_localization.io.csv_codec import export_catalog, import_catalog


def _print_json(value: object) -> None:
    """Print JSON safely on Windows consoles using legacy code pages."""

    text = json.dumps(value, ensure_ascii=False, indent=2)
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    try:
        text.encode(encoding)
    except (LookupError, UnicodeEncodeError):
        text = json.dumps(value, ensure_ascii=True, indent=2)
    sys.stdout.write(text + "\n")


def _cmd_identify(args: argparse.Namespace) -> int:
    info = identify_project(args.path)
    _print_json(
        {
            "path": str(info.path),
            "engine": info.engine,
            "confidence": info.confidence,
            "has_cryproject": info.has_cryproject,
            "has_assets": info.has_assets,
            "pak_files": [str(path) for path in info.pak_files],
            "engine_version": info.engine_version,
            "engine_version_source": info.engine_version_source,
            "engine_generation_hint": info.engine_generation_hint,
        }
    )
    return 0


def _cmd_pak_list(args: argparse.Namespace) -> int:
    archive = scan_pak(args.path)
    for entry in archive.entries:
        print(f"{entry.size:>10}  {entry.path}")
    return 0


def _cmd_pak_extract(args: argparse.Namespace) -> int:
    written = extract_pak(args.path, args.output, match=args.match, overwrite=args.overwrite)
    print(f"extracted {len(written)} files to {Path(args.output).resolve()}")
    return 0


def _cmd_pak_build(args: argparse.Namespace) -> int:
    root = Path(args.input).expanduser().resolve()
    if not root.is_dir():
        raise NotADirectoryError(root)
    output_path = Path(args.output).expanduser().resolve()
    entries = {
        path.relative_to(root).as_posix(): path
        for path in root.rglob("*")
        if path.is_file()
        and not path.name.endswith(".partial")
        and path.resolve() != output_path
    }
    output = build_pak(entries, output_path)
    print(output)
    return 0


def _cmd_catalog_export(args: argparse.Namespace) -> int:
    entries = catalog_from_pak(args.path)
    export_catalog(entries, args.output)
    print(f"exported {len(entries)} rows to {Path(args.output).resolve()}")
    return 0


def _cmd_apply(args: argparse.Namespace) -> int:
    entries = import_catalog(args.csv)
    if args.english_only:
        entries = [
            entry
            for entry in entries
            if entry.source_path.casefold().startswith("localization/english/")
        ]
    changes = plan_translation_changes(entries)
    if args.dry_run:
        _print_json([change.__dict__ for change in changes])
        return 0
    if not args.source_pak or not args.output_pak:
        raise ValueError("non-dry-run apply requires --source-pak and --output-pak")
    apply_catalog_to_pak(args.source_pak, entries, args.output_pak)
    print(f"wrote {Path(args.output_pak).resolve()}")
    return 0


def _cmd_build(args: argparse.Namespace) -> int:
    entries = import_catalog(args.csv)
    if args.overlay_mode == "english-path-overlay":
        entries = [
            entry
            for entry in entries
            if entry.source_path.casefold().startswith("localization/english/")
        ]
    output = Path(args.output_pak).expanduser().resolve()
    source = Path(args.source_pak).expanduser().resolve()
    changes = apply_catalog_to_pak(str(source), entries, str(output))
    replacements = [
        {
            "source_path": change.source_path,
            "text_key": change.text_key,
            "translation_sha256": hashlib.sha256(change.translation.encode("utf-8")).hexdigest(),
        }
        for change in changes
    ]
    manifest = build_manifest(
        tool_version=__version__,
        engine_version=args.engine_version,
        target_language=args.language,
        source_packages=[{"path": source.name, "sha256": sha256_file(source)}],
        replacements=replacements,
        font_strategy={"mode": args.font_mode, "character_ids": args.font_character_id},
        output_sha256=sha256_file(output),
        project=args.project,
        overlay_mode=args.overlay_mode,
    )
    write_manifest(manifest, args.manifest)
    print(f"wrote {output}")
    print(f"manifest {Path(args.manifest).expanduser().resolve()}")
    return 0


def _cmd_font_scan(args: argparse.Namespace) -> int:
    slots = scan_gfx_fonts(args.gfx, args.ffdec)
    _print_json([slot.__dict__ for slot in slots])
    return 0


def _cmd_font_replace(args: argparse.Namespace) -> int:
    replacements: dict[int, str] = {}
    for specification in args.slot:
        identifier, separator, font_file = specification.partition("=")
        if not separator or not identifier.isdigit() or not font_file:
            raise ValueError(f"invalid --slot value {specification!r}; expected ID=FONT_FILE")
        replacements[int(identifier)] = font_file
    output = replace_font_slots(
        args.gfx,
        args.output_gfx,
        replacements,
        ffdec_cli=args.ffdec,
    )
    print(output)
    return 0


def _font_python(executable: str | None) -> str:
    if executable:
        return executable
    info = discover_tools().get("fontTools")
    if info is None or not info.available or not info.path:
        raise RuntimeError("fontTools is unavailable; install with `pip install '.[fonts]'` or pass --python")
    return info.path


def _cmd_font_subset(args: argparse.Namespace) -> int:
    output = subset_font(
        args.font,
        args.text,
        args.output_font,
        python_executable=args.python,
    )
    print(output)
    return 0


def _cmd_font_coverage(args: argparse.Namespace) -> int:
    coverage = inspect_font_coverage(
        args.font,
        args.text,
        python_executable=args.python,
    )
    _print_json(coverage.__dict__)
    return 0


def _cmd_texture_inspect(args: argparse.Namespace) -> int:
    metadata = parse_dds_header(Path(args.dds).read_bytes())
    _print_json(metadata.__dict__)
    return 0


def _cmd_texture_encode(args: argparse.Namespace) -> int:
    output = encode_image_file_to_dds(args.image, args.output_dds, mipmaps=not args.no_mipmaps)
    print(output)
    return 0


def _cmd_texture_replace(args: argparse.Namespace) -> int:
    output = replace_texture_in_pak(
        args.source_pak,
        args.entry,
        args.replacement,
        args.output_pak,
        require_alpha=args.require_alpha,
    )
    print(output)
    return 0


def _cmd_config_preview(args: argparse.Namespace) -> int:
    text = Path(args.config).read_text(encoding="utf-8")
    preview = preview_language_config(text, args.language)
    _print_json({"after": preview.after, "diff": list(preview.diff)})
    return 0


def _cmd_config_write(args: argparse.Namespace) -> int:
    output = write_language_config(args.config, args.output, args.language)
    print(output)
    return 0


def _cmd_tools_doctor(args: argparse.Namespace) -> int:
    report = discover_tools(ffdec=args.ffdec)
    _print_json({name: info.as_dict() for name, info in report.items()})
    return 0


def _parse_install_items(specifications: list[str]) -> list[InstallItem]:
    items: list[InstallItem] = []
    for specification in specifications:
        source, separator, destination = specification.partition("=")
        if not separator or not source or not destination:
            raise ValueError(f"invalid --file value {specification!r}; expected SOURCE=GAME_RELATIVE_PATH")
        items.append(InstallItem(Path(source), destination))
    if not items:
        raise ValueError("at least one --file SOURCE=GAME_RELATIVE_PATH is required")
    return items


def _cmd_install(args: argparse.Namespace) -> int:
    items = _parse_install_items(args.file)
    if args.dry_run:
        planned = plan_install(args.game_root, items)
        _print_json(
            [
                {
                    "source": str(item.source),
                    "destination": str(item.destination),
                    "destination_existed": item.destination_existed,
                    "backup_sha256": item.backup_sha256,
                    "installed_sha256": item.installed_sha256,
                }
                for item in planned
            ]
        )
        return 0
    record = install_files(
        args.game_root,
        items,
        backup_dir=args.backup_dir,
        process_names=tuple(args.process_name),
    )
    write_install_record(record, args.record)
    print(f"installed {len(record.items)} files")
    print(f"record {Path(args.record).expanduser().resolve()}")
    return 0


def _cmd_rollback(args: argparse.Namespace) -> int:
    record = read_install_record(args.record)
    rollback_install(record)
    print(f"restored {len(record.items)} files")
    return 0


def _cmd_profile_init(args: argparse.Namespace) -> int:
    path = Path(args.output).expanduser().resolve()
    if path.exists() and not args.overwrite:
        raise FileExistsError(f"profile already exists; pass --overwrite to replace: {path}")
    save_profile(ProjectProfile(), path, validate=False)
    print(f"wrote {path}")
    return 0


def _cmd_profile_validate(args: argparse.Namespace) -> int:
    profile = load_profile(args.profile)
    _print_json(profile.to_dict())
    return 0


def _cmd_profile_show(args: argparse.Namespace) -> int:
    profile = load_profile(args.profile, validate=False)
    _print_json(profile.to_dict())
    return 0


def _cmd_workflow_export_csv(args: argparse.Namespace) -> int:
    profile = load_profile(args.profile)
    output, count = export_profile_catalog(profile, overwrite=args.overwrite)
    print(f"exported {count} rows to {output}")
    return 0


def _cmd_workflow_dry_run(args: argparse.Namespace) -> int:
    changes = plan_profile_changes(load_profile(args.profile))
    _print_json([change.__dict__ for change in changes])
    return 0


def _cmd_workflow_build(args: argparse.Namespace) -> int:
    output, manifest, _changes = build_profile(load_profile(args.profile))
    print(f"wrote {output}")
    print(f"manifest {manifest}")
    return 0


def _cmd_workflow_install(args: argparse.Namespace) -> int:
    profile = load_profile(args.profile)
    if args.dry_run:
        planned = plan_profile_install(profile)
        _print_json(
            [
                {
                    "source": str(item.source),
                    "destination": str(item.destination),
                    "destination_existed": item.destination_existed,
                    "backup_sha256": item.backup_sha256,
                    "installed_sha256": item.installed_sha256,
                }
                for item in planned
            ]
        )
        return 0
    record = install_profile(profile)
    print(f"installed {len(record.items)} files")
    print(f"record {Path(profile.install.record).expanduser().resolve()}")
    return 0


def _cmd_workflow_rollback(args: argparse.Namespace) -> int:
    record = rollback_profile(load_profile(args.profile))
    print(f"restored {len(record.items)} files")
    return 0


def _cmd_gui(args: argparse.Namespace) -> int:
    from cryengine_localization.gui import launch_gui

    launch_gui(ui_language=args.ui_language)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cry-localize", description=__doc__)
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)

    identify = sub.add_parser("identify", help="identify a CryEngine project")
    identify.add_argument("path")
    identify.set_defaults(func=_cmd_identify)

    pak = sub.add_parser("pak", help="inspect or build a PAK")
    pak_sub = pak.add_subparsers(dest="pak_command", required=True)
    pak_list = pak_sub.add_parser("list")
    pak_list.add_argument("path")
    pak_list.set_defaults(func=_cmd_pak_list)
    pak_extract = pak_sub.add_parser("extract")
    pak_extract.add_argument("path")
    pak_extract.add_argument("output")
    pak_extract.add_argument("--match")
    pak_extract.add_argument("--overwrite", action="store_true")
    pak_extract.set_defaults(func=_cmd_pak_extract)
    pak_build = pak_sub.add_parser("build")
    pak_build.add_argument("input")
    pak_build.add_argument("output")
    pak_build.set_defaults(func=_cmd_pak_build)

    catalog = sub.add_parser("catalog", help="export a translation catalog")
    catalog_sub = catalog.add_subparsers(dest="catalog_command", required=True)
    catalog_export = catalog_sub.add_parser("export")
    catalog_export.add_argument("path")
    catalog_export.add_argument("--output", required=True)
    catalog_export.set_defaults(func=_cmd_catalog_export)

    profile = sub.add_parser("profile", help="create and validate a generic project profile")
    profile_sub = profile.add_subparsers(dest="profile_command", required=True)
    profile_init = profile_sub.add_parser("init")
    profile_init.add_argument("--output", required=True)
    profile_init.add_argument("--overwrite", action="store_true")
    profile_init.set_defaults(func=_cmd_profile_init)
    profile_validate = profile_sub.add_parser("validate")
    profile_validate.add_argument("profile")
    profile_validate.set_defaults(func=_cmd_profile_validate)
    profile_show = profile_sub.add_parser("show")
    profile_show.add_argument("profile")
    profile_show.set_defaults(func=_cmd_profile_show)

    apply = sub.add_parser("apply", help="preview or apply a translation table")
    apply.add_argument("csv")
    apply.add_argument("--dry-run", action="store_true")
    apply.add_argument(
        "--english-only",
        action="store_true",
        help="only apply Localization/english entries (recommended for War of Rights overlay)",
    )
    apply.add_argument("--source-pak")
    apply.add_argument("--output-pak")
    apply.set_defaults(func=_cmd_apply)

    build = sub.add_parser("build", help="apply translations and write a PAK plus manifest")
    build.add_argument("source_pak")
    build.add_argument("csv")
    build.add_argument("--output-pak", required=True)
    build.add_argument("--manifest", required=True)
    build.add_argument("--language", default="zh-CN")
    build.add_argument("--engine-version")
    build.add_argument("--project")
    build.add_argument(
        "--overlay-mode",
        choices=("standalone", "english-path-overlay"),
        default="standalone",
        help="record how the output PAK should be loaded",
    )
    build.add_argument("--font-mode", choices=("none", "full", "subset"), default="none")
    build.add_argument("--font-character-id", action="append", type=int, default=[])
    build.set_defaults(func=_cmd_build)

    font = sub.add_parser("font", help="inspect GFX fonts")
    font_sub = font.add_subparsers(dest="font_command", required=True)
    font_scan = font_sub.add_parser("scan")
    font_scan.add_argument("gfx")
    font_scan.add_argument("--ffdec")
    font_scan.set_defaults(func=_cmd_font_scan)
    font_replace = font_sub.add_parser("replace")
    font_replace.add_argument("gfx")
    font_replace.add_argument("--output-gfx", required=True)
    font_replace.add_argument("--ffdec")
    font_replace.add_argument("--slot", action="append", required=True, help="FONT_ID=FONT_FILE")
    font_replace.set_defaults(func=_cmd_font_replace)
    font_subset = font_sub.add_parser("subset")
    font_subset.add_argument("font")
    font_subset.add_argument("text")
    font_subset.add_argument("--output-font", required=True)
    font_subset.add_argument("--python")
    font_subset.set_defaults(func=_cmd_font_subset)
    font_coverage = font_sub.add_parser("coverage")
    font_coverage.add_argument("font")
    font_coverage.add_argument("text")
    font_coverage.add_argument("--python")
    font_coverage.set_defaults(func=_cmd_font_coverage)

    texture = sub.add_parser("texture", help="inspect or replace DDS textures")
    texture_sub = texture.add_subparsers(dest="texture_command", required=True)
    texture_inspect = texture_sub.add_parser("inspect")
    texture_inspect.add_argument("dds")
    texture_inspect.set_defaults(func=_cmd_texture_inspect)
    texture_encode = texture_sub.add_parser("encode")
    texture_encode.add_argument("image")
    texture_encode.add_argument("--output-dds", required=True)
    texture_encode.add_argument("--no-mipmaps", action="store_true")
    texture_encode.set_defaults(func=_cmd_texture_encode)
    texture_replace = texture_sub.add_parser("replace")
    texture_replace.add_argument("source_pak")
    texture_replace.add_argument("entry")
    texture_replace.add_argument("replacement")
    texture_replace.add_argument("--output-pak", required=True)
    texture_replace.add_argument("--require-alpha", action="store_true")
    texture_replace.set_defaults(func=_cmd_texture_replace)

    config = sub.add_parser("config", help="preview game configuration changes")
    config_sub = config.add_subparsers(dest="config_command", required=True)
    config_preview = config_sub.add_parser("preview")
    config_preview.add_argument("config")
    config_preview.add_argument("--language", default="english")
    config_preview.set_defaults(func=_cmd_config_preview)
    config_write = config_sub.add_parser("write")
    config_write.add_argument("config")
    config_write.add_argument("--output", required=True)
    config_write.add_argument("--language", default="english")
    config_write.set_defaults(func=_cmd_config_write)

    tools = sub.add_parser("tools", help="diagnose optional external tools")
    tools_sub = tools.add_subparsers(dest="tools_command", required=True)
    doctor = tools_sub.add_parser("doctor")
    doctor.add_argument("--ffdec")
    doctor.set_defaults(func=_cmd_tools_doctor)

    install = sub.add_parser("install", help="install generated files with backup and rollback")
    install.add_argument("--game-root", required=True)
    install.add_argument("--backup-dir", required=True)
    install.add_argument("--record", required=True)
    install.add_argument("--file", action="append", default=[], help="SOURCE=GAME_RELATIVE_PATH")
    install.add_argument("--process-name", action="append", default=[])
    install.add_argument("--dry-run", action="store_true")
    install.set_defaults(func=_cmd_install)

    rollback = sub.add_parser("rollback", help="restore an install record")
    rollback.add_argument("record")
    rollback.set_defaults(func=_cmd_rollback)

    workflow = sub.add_parser("workflow", help="run a complete workflow from a project profile")
    workflow_sub = workflow.add_subparsers(dest="workflow_command", required=True)
    workflow_export = workflow_sub.add_parser("export-csv")
    workflow_export.add_argument("profile")
    workflow_export.add_argument("--overwrite", action="store_true")
    workflow_export.set_defaults(func=_cmd_workflow_export_csv)
    workflow_dry_run = workflow_sub.add_parser("dry-run")
    workflow_dry_run.add_argument("profile")
    workflow_dry_run.set_defaults(func=_cmd_workflow_dry_run)
    workflow_build = workflow_sub.add_parser("build")
    workflow_build.add_argument("profile")
    workflow_build.set_defaults(func=_cmd_workflow_build)
    workflow_install = workflow_sub.add_parser("install")
    workflow_install.add_argument("profile")
    workflow_install.add_argument("--dry-run", action="store_true")
    workflow_install.set_defaults(func=_cmd_workflow_install)
    workflow_rollback = workflow_sub.add_parser("rollback")
    workflow_rollback.add_argument("profile")
    workflow_rollback.set_defaults(func=_cmd_workflow_rollback)

    gui = sub.add_parser("gui", help="launch the optional Tkinter interface")
    gui.add_argument("--ui-language", default="zh-CN", help="GUI locale, for example zh-CN or en-US")
    gui.set_defaults(func=_cmd_gui)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
