from __future__ import annotations

import inspect

from cryengine_localization.gui import build_cli_args, gui_available, launch_gui


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


def test_gui_declares_a_batch_tab_that_delegates_to_core_workflows() -> None:
    source = inspect.getsource(launch_gui)

    assert "_build_batch_tab" in source
    assert "export_batch_profile_catalog" in source
    assert "build_batch_profile" in source
    assert "reuse_batch_profile_translations" in source
