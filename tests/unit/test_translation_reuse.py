from __future__ import annotations

from cryengine_localization.core.catalog import CatalogEntry
from cryengine_localization.core.translation_reuse import reuse_translations


def _entry(
    resource_id: str,
    source_path: str,
    text_key: str,
    original_hash: str,
    *,
    translation: str = "",
    source_archive: str = "",
) -> CatalogEntry:
    return CatalogEntry(
        resource_id=resource_id,
        source_path=source_path,
        text_key=text_key,
        original_text=text_key,
        original_hash=original_hash,
        translation=translation,
        source_archive=source_archive,
    )


def test_reuse_translations_prefers_unqualified_resource_id_then_hash_fallback() -> None:
    target = [
        _entry(
            "Assets/GameData.pak::Localization/english/Main.json:exact#2",
            "Localization/english/Main.json",
            "exact",
            "hash-1",
            source_archive="Assets/GameData.pak",
        ),
        _entry(
            "Assets/GameData.pak::Localization/english/Main.json:fallback-new-id",
            "Localization/english/Main.json",
            "fallback",
            "hash-2",
            source_archive="Assets/GameData.pak",
        ),
        _entry(
            "Assets/GameData.pak::Localization/english/Main.json:keep",
            "Localization/english/Main.json",
            "keep",
            "hash-3",
            translation="新译文",
            source_archive="Assets/GameData.pak",
        ),
    ]
    old = [
        _entry("Localization/english/Main.json:exact#2", "Localization/english/Main.json", "exact", "hash-1", translation="精确"),
        _entry("old-fallback", "Localization/english/Main.json", "fallback", "hash-2", translation="兜底"),
        _entry("old-keep", "Localization/english/Main.json", "keep", "hash-3", translation="旧译文"),
    ]

    merged, report = reuse_translations(target, old)

    assert [entry.translation for entry in merged] == ["精确", "兜底", "新译文"]
    assert report.exact_resource_id_matches == 1
    assert report.hash_fallback_matches == 1
    assert report.preserved_existing_translations == 1


def test_reuse_translations_reports_ambiguous_hash_matches_without_copying() -> None:
    target = [
        _entry(
            "Assets/GameData.pak::Localization/english/Main.json:target",
            "Localization/english/Main.json",
            "same",
            "hash",
            source_archive="Assets/GameData.pak",
        )
    ]
    old = [
        _entry("old-one", "Localization/english/Main.json", "same", "hash", translation="甲"),
        _entry("old-two", "Localization/english/Main.json", "same", "hash", translation="乙"),
    ]

    merged, report = reuse_translations(target, old)

    assert merged[0].translation == ""
    assert report.ambiguous_hash_matches == (
        "Assets/GameData.pak::Localization/english/Main.json:target",
    )
