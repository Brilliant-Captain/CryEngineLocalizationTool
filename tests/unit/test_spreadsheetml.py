from __future__ import annotations

import hashlib

import pytest

from cryengine_localization.core.catalog import CatalogEntry
from cryengine_localization.io.spreadsheetml import (
    apply_catalog_to_spreadsheetml_bytes,
    catalog_from_spreadsheetml_bytes,
)


SPREADSHEET = b'''<?xml version="1.0"?>
<?mso-application progid="Excel.Sheet"?>
<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet"
 xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet">
 <Worksheet ss:Name="Sheet1"><Table>
  <Row><Cell><Data ss:Type="String">KEY</Data></Cell><Cell><Data ss:Type="String">ORIGINAL TEXT</Data></Cell><Cell><Data ss:Type="String">TRANSLATED TEXT</Data></Cell><Cell><Data ss:Type="String">CONTEXT</Data></Cell></Row>
  <Row><Cell><Data ss:Type="String">ui_start</Data></Cell><Cell><Data ss:Type="String">Start</Data></Cell><Cell><Data ss:Type="String">Start</Data></Cell><Cell><Data ss:Type="String">Menu</Data></Cell></Row>
  <Row><Cell><Data ss:Type="String">ui_exit</Data></Cell><Cell><Data ss:Type="String">Exit</Data></Cell><Cell/><Cell><Data ss:Type="String">Menu</Data></Cell></Row>
  <Row><Cell><Data ss:Type="String">ui_save</Data></Cell><Cell><Data ss:Type="String">Save</Data></Cell><Cell><Data ss:Type="String">Save now</Data></Cell></Row>
 </Table></Worksheet>
</Workbook>'''


def test_spreadsheetml_catalog_extracts_original_and_existing_translation() -> None:
    entries = catalog_from_spreadsheetml_bytes("english_xml/text_ui_menus.xml", SPREADSHEET)

    assert [entry.text_key for entry in entries] == ["ui_start", "ui_exit", "ui_save"]
    assert [entry.original_text for entry in entries] == ["Start", "Exit", "Save"]
    assert [entry.translation for entry in entries] == ["", "", "Save now"]
    assert entries[0].original_hash == hashlib.sha256(b"Start").hexdigest()


def test_spreadsheetml_apply_changes_only_translation_cell() -> None:
    entry = CatalogEntry(
        "english_xml/text_ui_menus.xml:ui_exit",
        "english_xml/text_ui_menus.xml",
        "ui_exit",
        "Exit",
        hashlib.sha256(b"Exit").hexdigest(),
        "\u9000\u51fa",
    )

    output = apply_catalog_to_spreadsheetml_bytes(
        "english_xml/text_ui_menus.xml", SPREADSHEET, [entry]
    )
    entries = catalog_from_spreadsheetml_bytes("english_xml/text_ui_menus.xml", output)

    assert next(item for item in entries if item.text_key == "ui_exit").translation == "\u9000\u51fa"
    assert next(item for item in entries if item.text_key == "ui_start").original_text == "Start"
    assert b"mso-application" in output
    assert b"Menu" in output


def test_spreadsheetml_apply_rejects_changed_original() -> None:
    entry = CatalogEntry(
        "english_xml/text_ui_menus.xml:ui_start",
        "english_xml/text_ui_menus.xml",
        "ui_start",
        "Old Start",
        hashlib.sha256(b"Old Start").hexdigest(),
        "\u5f00\u59cb",
    )

    with pytest.raises(ValueError, match="source changed"):
        apply_catalog_to_spreadsheetml_bytes(
            "english_xml/text_ui_menus.xml", SPREADSHEET, [entry]
        )


def test_spreadsheetml_uses_audio_filename_for_dialog_keys() -> None:
    raw = SPREADSHEET.replace(b"KEY", b"AUDIO_FILENAME").replace(b"ui_start", b"npc/line_01")

    entries = catalog_from_spreadsheetml_bytes("english_xml/dialog.xml", raw)

    assert entries[0].text_key == "npc/line_01"
