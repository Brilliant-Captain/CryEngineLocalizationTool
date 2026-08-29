from __future__ import annotations

import hashlib

import pytest

from cryengine_localization.core.catalog import CatalogEntry
from cryengine_localization.core.stale import reconcile_catalog, validate_translation


def entry(resource_id: str, text: str, translation: str = "") -> CatalogEntry:
    return CatalogEntry(
        resource_id=resource_id,
        source_path="x.json",
        text_key=resource_id,
        original_text=text,
        original_hash=hashlib.sha256(text.encode()).hexdigest(),
        translation=translation,
    )


def test_reconcile_marks_stale_orphaned_and_new() -> None:
    old = [entry("same", "old", "旧译文"), entry("gone", "gone")]
    current = [entry("same", "changed"), entry("new", "new")]

    result = {item.resource_id: item for item in reconcile_catalog(old, current)}

    assert result["same"].status == "stale"
    assert result["same"].translation == ""
    assert result["gone"].status == "orphaned"
    assert result["new"].status == "new"


def test_reconcile_keeps_translation_when_hash_is_unchanged() -> None:
    old = [entry("same", "same", "保持")]
    current = [entry("same", "same")]

    result = reconcile_catalog(old, current)

    assert result[0].status == "active"
    assert result[0].translation == "保持"


def test_placeholder_mismatch_is_rejected() -> None:
    with pytest.raises(ValueError, match="placeholder"):
        validate_translation("Hello {name}", "你好")

    validate_translation("Hello {name} %s", "你好 {name} %s")

