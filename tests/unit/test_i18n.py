from __future__ import annotations

import json

import pytest

from cryengine_localization.i18n import LocaleError, available_locales, load_locale


def test_builtin_locales_include_simplified_chinese_and_english() -> None:
    locales = available_locales()

    assert "zh-CN" in locales
    assert "en-US" in locales
    assert load_locale("zh-CN").get("app.title") != load_locale("en-US").get("app.title")


def test_locale_falls_back_to_english_then_key() -> None:
    catalog = load_locale("zh-CN")

    assert catalog.get("button.save")
    assert catalog.get("only.in.english") == "only.in.english"


def test_external_locale_overrides_builtin_and_supports_formatting(tmp_path) -> None:
    locale_dir = tmp_path / "locales"
    locale_dir.mkdir()
    (locale_dir / "en-US.json").write_text(
        json.dumps(
            {
                "locale": "en-US",
                "name": "Custom English",
                "strings": {"app.title": "Custom {name}"},
            }
        ),
        encoding="utf-8",
    )

    catalog = load_locale("en-US", locale_dir=locale_dir)

    assert catalog.name == "Custom English"
    assert catalog.get("app.title", name="Tool") == "Custom Tool"


def test_malformed_locale_resource_is_rejected(tmp_path) -> None:
    locale_dir = tmp_path / "locales"
    locale_dir.mkdir()
    (locale_dir / "xx-XX.json").write_text("[]", encoding="utf-8")

    with pytest.raises(LocaleError, match="object"):
        load_locale("xx-XX", locale_dir=locale_dir)
