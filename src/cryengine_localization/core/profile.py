"""Validated, game-agnostic project profiles for GUI and CLI workflows."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path, PurePath
from typing import Any, Mapping


PROFILE_SCHEMA_VERSION = 1
OVERLAY_MODES = ("standalone", "english-path-overlay")


class ProfileError(ValueError):
    """A project profile is malformed or fails validation."""


def _require_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ProfileError(f"{label} must be an object")
    return value


def _require_string(value: Any, label: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        raise ProfileError(f"{label} must be a non-empty string")
    return value


def _reject_unknown(data: Mapping[str, Any], allowed: set[str], label: str) -> None:
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise ProfileError(f"{label} contains unknown field(s): {', '.join(unknown)}")


@dataclass(frozen=True)
class FontSlot:
    """One DefineFont slot replacement."""

    character_id: int
    font_file: str

    @classmethod
    def from_dict(cls, value: Any, label: str = "font slot") -> "FontSlot":
        data = _require_mapping(value, label)
        _reject_unknown(data, {"character_id", "font_file"}, label)
        identifier = data.get("character_id")
        if isinstance(identifier, bool) or not isinstance(identifier, int) or identifier <= 0:
            raise ProfileError(f"{label}.character_id must be a positive integer")
        return cls(identifier, _require_string(data.get("font_file"), f"{label}.font_file"))

    def to_dict(self) -> dict[str, Any]:
        return {"character_id": self.character_id, "font_file": self.font_file}


@dataclass(frozen=True)
class FontProfile:
    """Optional GFX font replacement settings."""

    enabled: bool = False
    source_gfx: str = ""
    output_gfx: str = ""
    ffdec: str = ""
    python: str = ""
    output_pak: str = ""
    coverage_font: str = ""
    coverage_text: str = ""
    subset_output_font: str = ""
    slots: tuple[FontSlot, ...] = ()

    @classmethod
    def from_dict(cls, value: Any) -> "FontProfile":
        data = _require_mapping(value, "font")
        _reject_unknown(data, {"enabled", "source_gfx", "output_gfx", "ffdec", "python", "output_pak", "coverage_font", "coverage_text", "subset_output_font", "slots"}, "font")
        enabled = data.get("enabled", False)
        if not isinstance(enabled, bool):
            raise ProfileError("font.enabled must be a boolean")
        raw_slots = data.get("slots", [])
        if not isinstance(raw_slots, list):
            raise ProfileError("font.slots must be an array")
        slots = tuple(FontSlot.from_dict(item, f"font.slots[{index}]") for index, item in enumerate(raw_slots))
        result = cls(
            enabled=enabled,
            source_gfx=_require_string(data.get("source_gfx", ""), "font.source_gfx", allow_empty=True),
            output_gfx=_require_string(data.get("output_gfx", ""), "font.output_gfx", allow_empty=True),
            ffdec=_require_string(data.get("ffdec", ""), "font.ffdec", allow_empty=True),
            python=_require_string(data.get("python", ""), "font.python", allow_empty=True),
            output_pak=_require_string(data.get("output_pak", ""), "font.output_pak", allow_empty=True),
            coverage_font=_require_string(data.get("coverage_font", ""), "font.coverage_font", allow_empty=True),
            coverage_text=_require_string(data.get("coverage_text", ""), "font.coverage_text", allow_empty=True),
            subset_output_font=_require_string(data.get("subset_output_font", ""), "font.subset_output_font", allow_empty=True),
            slots=slots,
        )
        result.validate()
        return result

    def validate(self) -> "FontProfile":
        identifiers = [slot.character_id for slot in self.slots]
        if len(identifiers) != len(set(identifiers)):
            raise ProfileError("font.slots contains duplicate character_id values")
        if self.enabled:
            for value, label in (
                (self.source_gfx, "font.source_gfx"),
                (self.output_gfx, "font.output_gfx"),
                (self.output_pak, "font.output_pak"),
            ):
                _require_string(value, label)
            if not self.slots:
                raise ProfileError("font.slots must not be empty when fonts are enabled")
        return self

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "source_gfx": self.source_gfx,
            "output_gfx": self.output_gfx,
            "ffdec": self.ffdec,
            "python": self.python,
            "output_pak": self.output_pak,
            "coverage_font": self.coverage_font,
            "coverage_text": self.coverage_text,
            "subset_output_font": self.subset_output_font,
            "slots": [slot.to_dict() for slot in self.slots],
        }


@dataclass(frozen=True)
class BatchProfile:
    """Optional settings for full-game scan and overlay build workflows."""

    enabled: bool = False
    game_root: str = ""
    catalog_csv: str = ""
    legacy_translation_csv: str = ""
    scan_report: str = ""
    translation_overlay_pak: str = ""
    manifest: str = ""
    font_file: str = ""
    font_overlay_pak: str = ""
    ffdec: str = ""

    @classmethod
    def from_dict(cls, value: Any) -> "BatchProfile":
        data = _require_mapping(value, "batch")
        _reject_unknown(
            data,
            {
                "enabled",
                "game_root",
                "catalog_csv",
                "legacy_translation_csv",
                "scan_report",
                "translation_overlay_pak",
                "manifest",
                "font_file",
                "font_overlay_pak",
                "ffdec",
            },
            "batch",
        )
        enabled = data.get("enabled", False)
        if not isinstance(enabled, bool):
            raise ProfileError("batch.enabled must be a boolean")
        result = cls(
            enabled=enabled,
            game_root=_require_string(data.get("game_root", ""), "batch.game_root", allow_empty=True),
            catalog_csv=_require_string(data.get("catalog_csv", ""), "batch.catalog_csv", allow_empty=True),
            legacy_translation_csv=_require_string(data.get("legacy_translation_csv", ""), "batch.legacy_translation_csv", allow_empty=True),
            scan_report=_require_string(data.get("scan_report", ""), "batch.scan_report", allow_empty=True),
            translation_overlay_pak=_require_string(data.get("translation_overlay_pak", ""), "batch.translation_overlay_pak", allow_empty=True),
            manifest=_require_string(data.get("manifest", ""), "batch.manifest", allow_empty=True),
            font_file=_require_string(data.get("font_file", ""), "batch.font_file", allow_empty=True),
            font_overlay_pak=_require_string(data.get("font_overlay_pak", ""), "batch.font_overlay_pak", allow_empty=True),
            ffdec=_require_string(data.get("ffdec", ""), "batch.ffdec", allow_empty=True),
        )
        return result.validate()

    def validate(self) -> "BatchProfile":
        if bool(self.font_file) != bool(self.font_overlay_pak):
            raise ProfileError("batch.font_file and batch.font_overlay_pak must be supplied together")
        return self

    def require_scan(self) -> "BatchProfile":
        if not self.enabled:
            raise ProfileError("batch workflow is not enabled")
        for value, label in (
            (self.game_root, "batch.game_root"),
            (self.catalog_csv, "batch.catalog_csv"),
            (self.scan_report, "batch.scan_report"),
        ):
            _require_string(value, label)
        return self

    def require_dry_run(self) -> "BatchProfile":
        self.require_scan()
        return self

    def require_build(self) -> "BatchProfile":
        self.require_dry_run()
        for value, label in (
            (self.translation_overlay_pak, "batch.translation_overlay_pak"),
            (self.manifest, "batch.manifest"),
        ):
            _require_string(value, label)
        return self

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "game_root": self.game_root,
            "catalog_csv": self.catalog_csv,
            "legacy_translation_csv": self.legacy_translation_csv,
            "scan_report": self.scan_report,
            "translation_overlay_pak": self.translation_overlay_pak,
            "manifest": self.manifest,
            "font_file": self.font_file,
            "font_overlay_pak": self.font_overlay_pak,
            "ffdec": self.ffdec,
        }


@dataclass(frozen=True)
class InstallFile:
    """A generated file and its relative destination inside a project root."""

    source: str
    destination: str

    @classmethod
    def from_dict(cls, value: Any, label: str = "install file") -> "InstallFile":
        data = _require_mapping(value, label)
        _reject_unknown(data, {"source", "destination"}, label)
        return cls(
            _require_string(data.get("source"), f"{label}.source"),
            _require_string(data.get("destination"), f"{label}.destination"),
        )

    def to_dict(self) -> dict[str, str]:
        return {"source": self.source, "destination": self.destination}


@dataclass(frozen=True)
class InstallProfile:
    """Optional guarded installation settings."""

    game_root: str = ""
    backup_dir: str = ""
    record: str = ""
    files: tuple[InstallFile, ...] = ()
    process_names: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, value: Any) -> "InstallProfile":
        data = _require_mapping(value, "install")
        _reject_unknown(data, {"game_root", "backup_dir", "record", "files", "process_names"}, "install")
        raw_files = data.get("files", [])
        raw_process_names = data.get("process_names", [])
        if not isinstance(raw_files, list):
            raise ProfileError("install.files must be an array")
        if not isinstance(raw_process_names, list) or any(not isinstance(item, str) for item in raw_process_names):
            raise ProfileError("install.process_names must be an array of strings")
        result = cls(
            game_root=_require_string(data.get("game_root", ""), "install.game_root", allow_empty=True),
            backup_dir=_require_string(data.get("backup_dir", ""), "install.backup_dir", allow_empty=True),
            record=_require_string(data.get("record", ""), "install.record", allow_empty=True),
            files=tuple(InstallFile.from_dict(item, f"install.files[{index}]") for index, item in enumerate(raw_files)),
            process_names=tuple(raw_process_names),
        )
        return result.validate()

    def validate(self) -> "InstallProfile":
        for index, item in enumerate(self.files):
            normalized = item.destination.replace("\\", "/")
            path = PurePath(normalized)
            parts = [part for part in path.parts if part not in ("", ".")]
            if path.is_absolute() or not parts or ".." in parts or ":" in parts[0]:
                raise ProfileError(f"install.files[{index}].destination must be relative")
        return self

    def to_dict(self) -> dict[str, Any]:
        return {
            "game_root": self.game_root,
            "backup_dir": self.backup_dir,
            "record": self.record,
            "files": [item.to_dict() for item in self.files],
            "process_names": list(self.process_names),
        }


@dataclass(frozen=True)
class ProjectProfile:
    """Generic CryEngine workflow configuration shared by GUI and CLI."""

    name: str = ""
    engine_version: str | None = None
    source_pak: str = ""
    translation_csv: str = ""
    output_pak: str = ""
    manifest: str = ""
    language: str = "zh-CN"
    ui_language: str = "zh-CN"
    overlay_mode: str = "standalone"
    font: FontProfile = field(default_factory=FontProfile)
    batch: BatchProfile = field(default_factory=BatchProfile)
    install: InstallProfile = field(default_factory=InstallProfile)
    schema_version: int = PROFILE_SCHEMA_VERSION

    def validate(self, *, require_files: bool = False) -> "ProjectProfile":
        if self.schema_version != PROFILE_SCHEMA_VERSION:
            raise ProfileError(f"unsupported schema_version: {self.schema_version}")
        for value, label in ((self.name, "name"), (self.language, "language")):
            _require_string(value, label)
        if not self.batch.enabled:
            for value, label in (
                (self.source_pak, "source_pak"),
                (self.translation_csv, "translation_csv"),
                (self.output_pak, "output_pak"),
                (self.manifest, "manifest"),
            ):
                _require_string(value, label)
        if self.engine_version is not None:
            _require_string(self.engine_version, "engine_version")
        if self.overlay_mode not in OVERLAY_MODES:
            raise ProfileError(f"overlay_mode must be one of: {', '.join(OVERLAY_MODES)}")
        self.font.validate()
        self.batch.validate()
        self.install.validate()
        if require_files:
            if not self.batch.enabled:
                for value, label in (
                    (self.source_pak, "source_pak"),
                    (self.translation_csv, "translation_csv"),
                ):
                    if not Path(value).expanduser().is_file():
                        raise ProfileError(f"{label} does not exist: {value}")
        return self

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "name": self.name,
            "engine_version": self.engine_version,
            "source_pak": self.source_pak,
            "translation_csv": self.translation_csv,
            "output_pak": self.output_pak,
            "manifest": self.manifest,
            "language": self.language,
            "ui_language": self.ui_language,
            "overlay_mode": self.overlay_mode,
            "font": self.font.to_dict(),
            "batch": self.batch.to_dict(),
            "install": self.install.to_dict(),
        }

    @classmethod
    def from_dict(cls, value: Any) -> "ProjectProfile":
        data = _require_mapping(value, "profile")
        _reject_unknown(
            data,
            {
                "schema_version",
                "name",
                "engine_version",
                "source_pak",
                "translation_csv",
                "output_pak",
                "manifest",
                "language",
                "ui_language",
                "overlay_mode",
                "font",
                "batch",
                "install",
            },
            "profile",
        )
        schema_version = data.get("schema_version", PROFILE_SCHEMA_VERSION)
        if isinstance(schema_version, bool) or not isinstance(schema_version, int):
            raise ProfileError("schema_version must be an integer")
        engine_version = data.get("engine_version")
        if engine_version is not None and not isinstance(engine_version, str):
            raise ProfileError("engine_version must be a string or null")
        profile = cls(
            name=_require_string(data.get("name", ""), "name", allow_empty=True),
            engine_version=engine_version,
            source_pak=_require_string(data.get("source_pak", ""), "source_pak", allow_empty=True),
            translation_csv=_require_string(data.get("translation_csv", ""), "translation_csv", allow_empty=True),
            output_pak=_require_string(data.get("output_pak", ""), "output_pak", allow_empty=True),
            manifest=_require_string(data.get("manifest", ""), "manifest", allow_empty=True),
            language=_require_string(data.get("language", "zh-CN"), "language", allow_empty=True),
            ui_language=_require_string(data.get("ui_language", "zh-CN"), "ui_language", allow_empty=True),
            overlay_mode=_require_string(data.get("overlay_mode", "standalone"), "overlay_mode", allow_empty=True),
            font=FontProfile.from_dict(data.get("font", {})),
            batch=BatchProfile.from_dict(data.get("batch", {})),
            install=InstallProfile.from_dict(data.get("install", {})),
            schema_version=schema_version,
        )
        return profile


def save_profile(profile: ProjectProfile, path: str | Path, *, validate: bool = True) -> Path:
    """Write a profile as UTF-8 JSON and return its resolved path."""

    if validate:
        profile.validate()
    destination = Path(path).expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(profile.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return destination


def load_profile(path: str | Path, *, validate: bool = True) -> ProjectProfile:
    """Load a profile from UTF-8 JSON."""

    source = Path(path).expanduser().resolve()
    try:
        data = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProfileError(f"unable to read profile {source}: {exc}") from exc
    profile = ProjectProfile.from_dict(data)
    if validate:
        profile.validate()
    return profile
