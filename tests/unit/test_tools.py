from __future__ import annotations

from cryengine_localization.core.tools import ToolInfo, discover_tools, probe_python_module


def test_probe_python_module_reports_missing_module(tmp_path) -> None:
    result = probe_python_module("python-that-does-not-exist", "fontTools")

    assert result.available is False
    assert result.name == "fontTools"


def test_discover_tools_includes_structured_results(monkeypatch) -> None:
    monkeypatch.setattr(
        "cryengine_localization.core.tools.probe_command",
        lambda name, candidates=(), version_args=("--version",): ToolInfo(
            name=name, path=f"/fake/{name}", version="test", available=True
        ),
    )
    monkeypatch.setattr(
        "cryengine_localization.core.tools.probe_python_module",
        lambda executable, module: ToolInfo(module, str(executable), "test", True),
    )

    report = discover_tools()

    assert report["python"].available is True
    assert report["fontTools"].available is True
    assert report["ffdec"].name == "ffdec"


def test_discover_tools_accepts_ffdec_environment_override(monkeypatch) -> None:
    monkeypatch.setenv("FFDEC_CLI", "fake-ffdec")
    monkeypatch.setattr(
        "cryengine_localization.core.tools.probe_command",
        lambda name, candidates=(), version_args=("--version",): ToolInfo(
            name=name, path=str(next(iter(candidates), "")), version="test", available=True
        ),
    )
    monkeypatch.setattr(
        "cryengine_localization.core.tools.probe_python_module",
        lambda executable, module: ToolInfo(module, str(executable), "test", True),
    )

    report = discover_tools()

    assert report["ffdec"].path == "fake-ffdec"
