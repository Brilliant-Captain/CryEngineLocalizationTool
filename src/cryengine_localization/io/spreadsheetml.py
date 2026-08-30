"""CryEngine SpreadsheetML localization catalog support."""

from __future__ import annotations

import codecs
import hashlib
from dataclasses import dataclass
from typing import Iterable
from xml.dom import Node, minidom
from xml.parsers.expat import ExpatError

from cryengine_localization.core.catalog import CatalogEntry


SPREADSHEET_NS = "urn:schemas-microsoft-com:office:spreadsheet"
_KEY_HEADERS = ("KEY", "AUDIO_FILENAME", "PICK UP")


@dataclass
class _SpreadsheetRecord:
    text_key: str
    original_text: str
    translation_text: str
    row: minidom.Element
    translation_cell: minidom.Element | None
    translation_column: int
    resource_id: str = ""


def _element_children(element: minidom.Element, local_name: str) -> list[minidom.Element]:
    return [
        child
        for child in element.childNodes
        if child.nodeType == Node.ELEMENT_NODE
        and child.namespaceURI == SPREADSHEET_NS
        and child.localName == local_name
    ]


def _element_text(element: minidom.Element | None) -> str:
    if element is None:
        return ""
    values: list[str] = []

    def collect(node: Node) -> None:
        if node.nodeType in (Node.TEXT_NODE, Node.CDATA_SECTION_NODE):
            values.append(node.data)
        else:
            for child in node.childNodes:
                collect(child)

    collect(element)
    return "".join(values)


def _cell_text(cell: minidom.Element | None) -> str:
    if cell is None:
        return ""
    data = _element_children(cell, "Data")
    return _element_text(data[0]) if data else ""


def _row_cells(row: minidom.Element) -> dict[int, minidom.Element]:
    cells: dict[int, minidom.Element] = {}
    column = 1
    for cell in _element_children(row, "Cell"):
        explicit = cell.getAttributeNS(SPREADSHEET_NS, "Index")
        if explicit:
            try:
                column = int(explicit)
            except ValueError as exc:
                raise ValueError(f"invalid SpreadsheetML cell index: {explicit!r}") from exc
        cells[column] = cell
        increment = 1
        merged = cell.getAttributeNS(SPREADSHEET_NS, "MergeAcross")
        if merged:
            try:
                increment += int(merged)
            except ValueError as exc:
                raise ValueError(f"invalid SpreadsheetML merge count: {merged!r}") from exc
        column += increment
    return cells


def _parse_document(raw: bytes | str) -> tuple[minidom.Document, bool]:
    encoded = raw.encode("utf-8") if isinstance(raw, str) else raw
    had_bom = encoded.startswith(codecs.BOM_UTF8)
    try:
        document = minidom.parseString(encoded)
    except (ExpatError, UnicodeError) as exc:
        raise ValueError("invalid SpreadsheetML XML") from exc
    root = document.documentElement
    if root.namespaceURI != SPREADSHEET_NS or root.localName != "Workbook":
        raise ValueError("XML is not a SpreadsheetML workbook")
    return document, had_bom


def _header_columns(rows: list[minidom.Element]) -> tuple[int, int, int, int] | None:
    for index, row in enumerate(rows):
        cells = _row_cells(row)
        values = {column: _cell_text(cell).strip().upper() for column, cell in cells.items()}
        if "TRANSLATED TEXT" not in values.values():
            continue
        key_column = next(
            (column for name in _KEY_HEADERS for column, value in values.items() if value == name),
            None,
        )
        original_column = next(
            (column for column, value in values.items() if value == "ORIGINAL TEXT"), None
        )
        translation_column = next(
            (column for column, value in values.items() if value == "TRANSLATED TEXT"), None
        )
        if key_column is not None and original_column is not None and translation_column is not None:
            return index, key_column, original_column, translation_column
    return None


def _records(document: minidom.Document, source_path: str) -> list[_SpreadsheetRecord]:
    records: list[_SpreadsheetRecord] = []
    for worksheet in document.getElementsByTagNameNS(SPREADSHEET_NS, "Worksheet"):
        for table in worksheet.getElementsByTagNameNS(SPREADSHEET_NS, "Table"):
            rows = _element_children(table, "Row")
            header = _header_columns(rows)
            if header is None:
                continue
            header_index, key_column, original_column, translation_column = header
            for row in rows[header_index + 1 :]:
                cells = _row_cells(row)
                key = _cell_text(cells.get(key_column)).strip()
                original = _cell_text(cells.get(original_column))
                translation = _cell_text(cells.get(translation_column))
                if key and (original or translation):
                    records.append(
                        _SpreadsheetRecord(
                            key,
                            original,
                            translation,
                            row,
                            cells.get(translation_column),
                            translation_column,
                        )
                    )
    counts: dict[str, int] = {}
    for record in records:
        counts[record.text_key] = counts.get(record.text_key, 0) + 1
    seen: dict[str, int] = {}
    for record in records:
        seen[record.text_key] = seen.get(record.text_key, 0) + 1
        resource_id = f"{source_path}:{record.text_key}"
        if counts[record.text_key] > 1:
            resource_id += f"#{seen[record.text_key]}"
        record.resource_id = resource_id
    return records


def _to_catalog(record: _SpreadsheetRecord, source_path: str) -> CatalogEntry:
    existing_translation = (
        record.translation_text
        if record.translation_text and record.translation_text != record.original_text
        else ""
    )
    return CatalogEntry(
        resource_id=record.resource_id,
        source_path=source_path,
        text_key=record.text_key,
        original_text=record.original_text,
        original_hash=hashlib.sha256(record.original_text.encode("utf-8")).hexdigest(),
        translation=existing_translation,
    )


def catalog_from_spreadsheetml_bytes(source_path: str, raw: bytes | str) -> list[CatalogEntry]:
    """Extract stable catalog entries from a CryEngine Excel XML workbook."""

    document, _had_bom = _parse_document(raw)
    return [_to_catalog(record, source_path) for record in _records(document, source_path)]


def _ensure_translation_data(
    document: minidom.Document, record: _SpreadsheetRecord
) -> minidom.Element:
    cell = record.translation_cell
    if cell is None:
        cell = document.createElementNS(SPREADSHEET_NS, "Cell")
        cell.setAttributeNS(SPREADSHEET_NS, "ss:Index", str(record.translation_column))
        cells = _row_cells(record.row)
        next_cell = next(
            (cells[column] for column in sorted(cells) if column > record.translation_column),
            None,
        )
        if next_cell is None:
            record.row.appendChild(cell)
        else:
            record.row.insertBefore(cell, next_cell)
        record.translation_cell = cell
    data_nodes = _element_children(cell, "Data")
    if data_nodes:
        return data_nodes[0]
    data = document.createElementNS(SPREADSHEET_NS, "Data")
    data.setAttributeNS(SPREADSHEET_NS, "ss:Type", "String")
    cell.appendChild(data)
    return data


def _set_element_text(document: minidom.Document, element: minidom.Element, value: str) -> None:
    while element.firstChild is not None:
        element.removeChild(element.firstChild)
    element.appendChild(document.createTextNode(value))


def apply_catalog_to_spreadsheetml_bytes(
    source_path: str,
    raw: bytes | str,
    entries: Iterable[CatalogEntry],
) -> bytes:
    """Apply translations to SpreadsheetML while preserving non-translation cells."""

    document, had_bom = _parse_document(raw)
    records = _records(document, source_path)
    current = {record.resource_id: (record, _to_catalog(record, source_path)) for record in records}
    by_key_hash: dict[tuple[str, str], list[tuple[_SpreadsheetRecord, CatalogEntry]]] = {}
    for record, entry in current.values():
        by_key_hash.setdefault((entry.text_key, entry.original_hash), []).append((record, entry))
    for requested in entries:
        match = current.get(requested.resource_id)
        if match is None:
            candidates = by_key_hash.get((requested.text_key, requested.original_hash), [])
            match = candidates.pop(0) if candidates else None
        if match is None:
            raise ValueError(f"translation resource is absent from source: {requested.resource_id}")
        record, entry = match
        if entry.original_hash != requested.original_hash:
            raise ValueError(f"source changed since catalog export: {requested.resource_id}")
        data = _ensure_translation_data(document, record)
        _set_element_text(document, data, requested.translation)
    output = document.toxml(encoding="utf-8")
    return codecs.BOM_UTF8 + output if had_bom else output
