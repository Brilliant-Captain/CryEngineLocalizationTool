from __future__ import annotations

from cryengine_localization.gui import build_cli_args, gui_available


def test_gui_available_is_boolean() -> None:
    assert isinstance(gui_available(), bool)


def test_gui_build_args_only_contains_explicit_paths() -> None:
    args = build_cli_args("source.pak", "translations.csv", "out.pak", "manifest.json", "zh-CN")

    assert args == [
        "build",
        "source.pak",
        "translations.csv",
        "--output-pak",
        "out.pak",
        "--manifest",
        "manifest.json",
        "--language",
        "zh-CN",
        "--overlay-mode",
        "standalone",
    ]
