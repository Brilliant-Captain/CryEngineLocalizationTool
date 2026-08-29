from __future__ import annotations

import io
import zipfile

import pytest

from cryengine_localization.adapters.pak import (
    DuplicateEntryError,
    UnsafeEntryPathError,
    build_pak,
    normalize_entry_path,
    scan_pak,
)


def test_normalize_entry_path_rejects_traversal_and_absolute_paths() -> None:
    for value in ("../escape.txt", r"..\escape.txt", "/absolute.txt", "C:/drive.txt"):
        with pytest.raises(UnsafeEntryPathError):
            normalize_entry_path(value)


def test_build_pak_is_deterministic_and_scan_reports_entries(tmp_path) -> None:
    first = tmp_path / "first.pak"
    second = tmp_path / "second.pak"
    entries = {"b.txt": b"B", "a/hello.json": b"{\"hello\": \"world\"}"}

    build_pak(entries, first)
    build_pak(entries, second)

    assert first.read_bytes() == second.read_bytes()
    archive = scan_pak(first)
    assert [entry.path for entry in archive.entries] == ["a/hello.json", "b.txt"]
    assert archive.entries[0].size == len(entries["a/hello.json"])


def test_scan_rejects_casefold_duplicate_entries(tmp_path) -> None:
    path = tmp_path / "duplicate.pak"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("A.txt", b"one")
        archive.writestr("a.txt", b"two")

    with pytest.raises(DuplicateEntryError):
        scan_pak(path)


def test_build_rejects_duplicate_normalized_paths(tmp_path) -> None:
    with pytest.raises(DuplicateEntryError):
        build_pak({"a.txt": b"one", "A.TXT": b"two"}, tmp_path / "dup.pak")

