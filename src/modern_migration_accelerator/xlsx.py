from __future__ import annotations

import re
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from io import BytesIO


MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS = {"m": MAIN_NS, "r": REL_NS}


@dataclass(frozen=True)
class XlsxSheet:
    name: str
    rows: list[list[str]]


def xlsx_bytes_to_sheets(content: bytes) -> list[XlsxSheet]:
    """Read basic worksheet text from an .xlsx file without external dependencies."""
    with zipfile.ZipFile(BytesIO(content)) as archive:
        shared_strings = _read_shared_strings(archive)
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        relationships = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        relationship_targets = {
            rel.attrib["Id"]: rel.attrib["Target"]
            for rel in relationships
            if rel.attrib.get("Type", "").endswith("/worksheet")
        }

        sheets: list[XlsxSheet] = []
        for sheet in workbook.findall("m:sheets/m:sheet", NS):
            sheet_name = sheet.attrib.get("name", "Sheet")
            relationship_id = sheet.attrib.get(f"{{{REL_NS}}}id")
            if not relationship_id or relationship_id not in relationship_targets:
                continue
            worksheet_path = _workbook_target_to_archive_path(relationship_targets[relationship_id])
            worksheet = ET.fromstring(archive.read(worksheet_path))
            rows = _read_rows(worksheet, shared_strings)
            sheets.append(XlsxSheet(name=sheet_name, rows=rows))
        return sheets


def xlsx_bytes_to_text(content: bytes) -> str:
    parts: list[str] = []
    for sheet in xlsx_bytes_to_sheets(content):
        parts.append(f"## Sheet: {sheet.name}")
        for row in sheet.rows:
            parts.append("\t".join(_clean_cell(cell) for cell in row))
        parts.append("")
    return "\n".join(parts).strip()


def parse_xlsx_text_sheets(content: str) -> dict[str, list[list[str]]]:
    sheets: dict[str, list[list[str]]] = {}
    current_sheet: str | None = None

    for line in content.splitlines():
        if line.startswith("## Sheet: "):
            current_sheet = line.removeprefix("## Sheet: ").strip()
            sheets[current_sheet] = []
            continue
        if current_sheet is None or not line.strip():
            continue
        sheets[current_sheet].append(line.split("\t"))

    return sheets


def rows_as_dicts(rows: list[list[str]]) -> list[dict[str, str]]:
    if not rows:
        return []

    headers = [_normalize_header(value) for value in rows[0]]
    output: list[dict[str, str]] = []
    for row in rows[1:]:
        item = {}
        for index, header in enumerate(headers):
            if not header:
                continue
            item[header] = row[index].strip() if index < len(row) else ""
        if any(value for value in item.values()):
            output.append(item)
    return output


def _read_shared_strings(archive: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []

    root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    strings: list[str] = []
    for item in root.findall("m:si", NS):
        texts = [node.text or "" for node in item.findall(".//m:t", NS)]
        strings.append("".join(texts))
    return strings


def _workbook_target_to_archive_path(target: str) -> str:
    normalized = target.replace("\\", "/").lstrip("/")
    if normalized.startswith("xl/"):
        return normalized
    return f"xl/{normalized}"


def _read_rows(worksheet: ET.Element, shared_strings: list[str]) -> list[list[str]]:
    rows: list[list[str]] = []
    for row in worksheet.findall("m:sheetData/m:row", NS):
        values: list[str] = []
        for cell in row.findall("m:c", NS):
            column_index = _cell_column_index(cell.attrib.get("r", ""))
            if column_index is None:
                values.append(_read_cell(cell, shared_strings))
                continue
            while len(values) <= column_index:
                values.append("")
            values[column_index] = _read_cell(cell, shared_strings)
        if any(value.strip() for value in values):
            rows.append(values)
    return rows


def _read_cell(cell: ET.Element, shared_strings: list[str]) -> str:
    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        return "".join(node.text or "" for node in cell.findall(".//m:t", NS))

    value_node = cell.find("m:v", NS)
    if value_node is None or value_node.text is None:
        return ""

    raw_value = value_node.text
    if cell_type == "s":
        try:
            return shared_strings[int(raw_value)]
        except (IndexError, ValueError):
            return raw_value
    return raw_value


def _clean_cell(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("\t", " ")).strip()


def _normalize_header(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")


def _cell_column_index(cell_reference: str) -> int | None:
    match = re.match(r"([A-Z]+)", cell_reference.upper())
    if not match:
        return None

    index = 0
    for character in match.group(1):
        index = index * 26 + (ord(character) - ord("A") + 1)
    return index - 1
