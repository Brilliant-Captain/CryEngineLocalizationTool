from __future__ import annotations

import hashlib
import json

from cryengine_localization.core.manifest import build_manifest, write_manifest


def test_manifest_contains_reproducibility_fields(tmp_path) -> None:
    source = tmp_path / "source.pak"
    source.write_bytes(b"source")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()

    manifest = build_manifest(
        tool_version="0.1.0",
        engine_version="5.x",
        target_language="zh-CN",
        source_packages=[{"path": "source.pak", "sha256": digest}],
        replacements=[{"path": "Localization/zh-CN/MainMenu.json"}],
        font_strategy={"mode": "subset", "character_ids": [7, 16]},
        build_time_utc="2026-01-01T00:00:00Z",
        output_sha256="output-hash",
    )
    path = tmp_path / "manifest.json"
    write_manifest(manifest, path)

    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["target_language"] == "zh-CN"
    assert loaded["source_packages"][0]["sha256"] == digest
    assert loaded["font_strategy"]["character_ids"] == [7, 16]
    assert loaded["output_sha256"] == "output-hash"

