"""Small JSON-backed locale catalog with safe fallback behavior."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any, Mapping


class LocaleError(ValueError):
    """A locale resource is malformed or unavailable."""


def _validate_resource(value: Any, requested: str) -> tuple[str, str, dict[str, str]]:
    if not isinstance(value, Mapping):
        raise LocaleError(f"locale {requested!r} must be an object")
    unknown = sorted(set(value) - {"locale", "name", "strings"})
    if unknown:
        raise LocaleError(f"locale {requested!r} contains unknown field(s): {', '.join(unknown)}")
    locale = value.get("locale")
    name = value.get("name")
    strings = value.get("strings")
    if not isinstance(locale, str) or not locale.strip():
        raise LocaleError(f"locale {requested!r} has an invalid locale field")
    if locale != requested:
        raise LocaleError(f"locale resource {requested!r} declares {locale!r}")
    if not isinstance(name, str) or not name.strip():
        raise LocaleError(f"locale {requested!r} has an invalid name field")
    if not isinstance(strings, Mapping) or any(not isinstance(key, str) or not isinstance(item, str) for key, item in strings.items()):
        raise LocaleError(f"locale {requested!r}.strings must map strings to strings")
    return locale, name, dict(strings)


def _read_json(path: Path | Any, locale: str) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
        value = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LocaleError(f"unable to read locale {locale!r}: {exc}") from exc
    return value


def _built_in_path(locale: str) -> Any | None:
    candidate = resources.files("cryengine_localization.locales").joinpath(f"{locale}.json")
    return candidate if candidate.is_file() else None


def _external_paths(locale: str, locale_dir: str | Path | None) -> list[Path]:
    roots: list[Path] = []
    if locale_dir:
        roots.append(Path(locale_dir).expanduser())
    environment = os.environ.get("CRYENGINE_LOCALE_DIR")
    if environment:
        roots.append(Path(environment).expanduser())
    roots.extend(
        [
            Path(sys.executable).resolve().parent / "locales",
            Path.cwd() / "locales",
        ]
    )
    unique: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        key = str(root.resolve()).casefold()
        if key not in seen:
            seen.add(key)
            unique.append(root / f"{locale}.json")
    return unique


@dataclass(frozen=True)
class LocaleCatalog:
    """A locale and its English fallback catalog."""

    locale: str
    name: str
    strings: Mapping[str, str]
    fallback: "LocaleCatalog | None" = None

    def get(self, key: str, **values: object) -> str:
        template = self.strings.get(key)
        if template is None and self.fallback is not None:
            return self.fallback.get(key, **values)
        if template is None:
            template = key
        if values:
            try:
                return template.format(**values)
            except (KeyError, IndexError, ValueError):
                return template
        return template


def load_locale(locale: str = "zh-CN", *, locale_dir: str | Path | None = None) -> LocaleCatalog:
    """Load a locale, preferring external files over built-ins."""

    if not isinstance(locale, str) or not locale.strip():
        raise LocaleError("locale must be a non-empty string")
    source: Path | Any | None = next((path for path in _external_paths(locale, locale_dir) if path.is_file()), None)
    if source is None:
        source = _built_in_path(locale)
    if source is None:
        raise LocaleError(f"locale is unavailable: {locale}")
    value = _read_json(source, locale)
    actual, name, strings = _validate_resource(value, locale)
    fallback = None
    if actual != "en-US":
        fallback = load_locale("en-US", locale_dir=locale_dir)
    return LocaleCatalog(actual, name, strings, fallback)


def available_locales(*, locale_dir: str | Path | None = None) -> dict[str, str]:
    """Return locale identifiers mapped to display names."""

    files: dict[str, Path | Any] = {}
    package_root = resources.files("cryengine_localization.locales")
    for item in package_root.iterdir():
        if item.is_file() and item.name.endswith(".json"):
            files[item.name[:-5]] = item
    roots: list[Path] = []
    if locale_dir:
        roots.append(Path(locale_dir).expanduser())
    environment = os.environ.get("CRYENGINE_LOCALE_DIR")
    if environment:
        roots.append(Path(environment).expanduser())
    roots.extend([Path(sys.executable).resolve().parent / "locales", Path.cwd() / "locales"])
    for root in roots:
        if not root.is_dir():
            continue
        for item in root.glob("*.json"):
            files[item.stem] = item
    result: dict[str, str] = {}
    for identifier, path in sorted(files.items()):
        try:
            _actual, name, _strings = _validate_resource(_read_json(path, identifier), identifier)
        except LocaleError:
            continue
        result[identifier] = name
    return result
