import json
import zipfile

from cryengine_localization.adapters.pak_decrypt import (
    decrypt_pak,
    decrypt_pak_tree,
    discover_public_key,
)


def _zip(path, name="Localization/english/text.xml", payload=b"<Workbook />"):
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(name, payload)


def test_decrypt_pak_copies_plain_zip_and_validates(tmp_path):
    source = tmp_path / "source.pak"
    output = tmp_path / "out" / "source.pak"
    key = tmp_path / "key.der"
    helper = tmp_path / "helper.exe"
    _zip(source)
    key.write_bytes(b"key")
    helper.write_bytes(b"helper")

    result = decrypt_pak(source, output, decryptor=helper, public_key=key)

    assert result.status == "copied"
    assert result.encrypted is False
    assert result.entry_count == 1
    with zipfile.ZipFile(output) as archive:
        assert archive.read("Localization/english/text.xml") == b"<Workbook />"


def test_decrypt_pak_tree_extract_preserves_relative_pak_directory(tmp_path):
    source_root = tmp_path / "game"
    source = source_root / "TheLandOfPain" / "gamedata.pak"
    output_root = tmp_path / "decrypted"
    report = tmp_path / "report.json"
    source.parent.mkdir(parents=True)
    _zip(source, "Localization/english/MainMenu.json", b"{}")
    key = tmp_path / "key.der"
    helper = tmp_path / "helper.exe"
    key.write_bytes(b"key")
    helper.write_bytes(b"helper")

    results, report_path = decrypt_pak_tree(
        source_root,
        output_root,
        decryptor=helper,
        public_key=key,
        mode="extract",
        report_path=report,
    )

    assert len(results) == 1
    assert results[0].extracted_count == 1
    assert (
        output_root / "TheLandOfPain" / "gamedata" / "Localization" / "english" / "MainMenu.json"
    ).read_bytes() == b"{}"
    assert report_path == report
    assert json.loads(report.read_text(encoding="utf-8"))["succeeded"] == 1


def test_discover_public_key_extracts_embedded_rsa_der(tmp_path):
    game = tmp_path / "game"
    module = game / "bin" / "CryGameSDK.dll"
    module.parent.mkdir(parents=True)
    prefix = bytes.fromhex("30 81 89 02 81 81 00")
    suffix = bytes.fromhex("02 03 01 00 01")
    key = prefix + bytes(range(128)) + suffix
    module.write_bytes(b"header" + key + b"tail")

    output = tmp_path / "public.der"
    result = discover_public_key(game, output_key=output)

    assert result.module_path.endswith("CryGameSDK.dll")
    assert result.offset == 6
    assert output.read_bytes() == key
    assert len(output.read_bytes()) == 140
