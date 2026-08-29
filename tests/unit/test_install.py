from __future__ import annotations

import json

import pytest

from cryengine_localization.core.install import (
    GameRunningError,
    InstallItem,
    InstallationError,
    install_files,
    plan_install,
    rollback_install,
)


def test_plan_install_rejects_destination_outside_game_root(tmp_path) -> None:
    (tmp_path / "game").mkdir()
    source = tmp_path / "patch.pak"
    source.write_bytes(b"patch")

    with pytest.raises(InstallationError, match="inside game root"):
        plan_install(tmp_path / "game", [InstallItem(source, "../outside.pak")])


def test_install_backup_and_rollback_restore_original(tmp_path, monkeypatch) -> None:
    game = tmp_path / "game"
    game.mkdir()
    destination = game / "Assets" / "patch.pak"
    destination.parent.mkdir()
    destination.write_bytes(b"original")
    source = tmp_path / "new.pak"
    source.write_bytes(b"new")
    monkeypatch.setattr("cryengine_localization.core.install.ensure_game_not_running", lambda *_args, **_kwargs: None)

    record = install_files(
        game,
        [InstallItem(source, "Assets/patch.pak")],
        backup_dir=tmp_path / "backup",
    )

    assert destination.read_bytes() == b"new"
    assert record.items[0].backup_sha256
    rollback_install(record)
    assert destination.read_bytes() == b"original"


def test_install_aborts_when_game_process_is_running(tmp_path, monkeypatch) -> None:
    game = tmp_path / "game"
    game.mkdir()
    source = tmp_path / "new.pak"
    source.write_bytes(b"new")
    monkeypatch.setattr(
        "cryengine_localization.core.install.ensure_game_not_running",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(GameRunningError("WarOfRights.exe")),
    )

    with pytest.raises(GameRunningError):
        install_files(game, [InstallItem(source, "Assets/new.pak")], backup_dir=tmp_path / "backup")
    assert not (game / "Assets" / "new.pak").exists()


def test_rollback_rejects_tampered_backup(tmp_path, monkeypatch) -> None:
    game = tmp_path / "game"
    game.mkdir()
    (game / "new.pak").write_bytes(b"original")
    source = tmp_path / "new.pak"
    source.write_bytes(b"new")
    monkeypatch.setattr("cryengine_localization.core.install.ensure_game_not_running", lambda *_args, **_kwargs: None)
    record = install_files(game, [InstallItem(source, "new.pak")], backup_dir=tmp_path / "backup")
    record.items[0].backup_path.write_bytes(b"tampered")

    with pytest.raises(InstallationError, match="backup hash"):
        rollback_install(record)


def test_rollback_rejects_record_destination_outside_root(tmp_path) -> None:
    from cryengine_localization.core.install import InstalledItem, InstallationRecord

    record = InstallationRecord(
        game_root=tmp_path / "game",
        backup_dir=tmp_path / "backup",
        items=[
            InstalledItem(
                source=tmp_path / "source",
                destination=tmp_path / "outside",
                backup_path=None,
                backup_sha256=None,
                installed_sha256="hash",
                destination_existed=False,
            )
        ],
        created_at_utc="now",
    )

    with pytest.raises(InstallationError, match="outside game root"):
        rollback_install(record)
