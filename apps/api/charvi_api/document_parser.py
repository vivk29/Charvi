"""Native, provenance-preserving document extraction for the Knowledge Hub."""
from __future__ import annotations

import csv
import io
import json
import re
from dataclasses import asdict, dataclass
from hashlib import sha256
from typing import Any


@dataclass(frozen=True)
class ExtractedUnit:
    text: str
    locator_type: str
    locator: dict[str, Any]


def _clean(text: str) -> str:
    return re.sub(r"[ \t]+\n", "\n", re.sub(r"\n{3,}", "\n\n", text)).strip()


def _unit(text: str, kind: str, **locator: Any) -> ExtractedUnit | None:
    cleaned = _clean(text)
    if not cleaned:
        return None
    return ExtractedUnit(cleaned, kind, locator)


def extract_document(extension: str, content: bytes) -> list[ExtractedUnit]:
    """Extract bounded text units with page/sheet/row/slide provenance.

    This function never executes macros, formulas, embedded objects, or document instructions.
    """
    units: list[ExtractedUnit] = []
    if extension == "pdf":
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(content), strict=True)
        if reader.is_encrypted:
            raise ValueError("Password-protected PDFs are not supported yet.")
        for page_number, page in enumerate(reader.pages, start=1):
            item = _unit(page.extract_text() or "", "page", page=page_number)
            if item:
                units.append(item)
    elif extension == "docx":
        from docx import Document

        document = Document(io.BytesIO(content))
        for index, paragraph in enumerate(document.paragraphs, start=1):
            item = _unit(paragraph.text, "paragraph", paragraph=index, style=paragraph.style.name)
            if item:
                units.append(item)
        for table_index, table in enumerate(document.tables, start=1):
            for row_index, row in enumerate(table.rows, start=1):
                values = [cell.text.strip() for cell in row.cells]
                item = _unit(" | ".join(values), "table_row", table=table_index, row=row_index)
                if item:
                    units.append(item)
    elif extension == "xlsx":
        from openpyxl import load_workbook

        workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=False)
        try:
            for sheet in workbook.worksheets:
                for row_index, row in enumerate(sheet.iter_rows(), start=1):
                    values = []
                    first_col = None
                    last_col = None
                    for cell in row:
                        if cell.value is not None:
                            first_col = first_col or cell.column_letter
                            last_col = cell.column_letter
                            value = cell.value
                            values.append(f"{cell.coordinate}={value}")
                    item = _unit(
                        " | ".join(values),
                        "spreadsheet_row",
                        sheet=sheet.title,
                        row=row_index,
                        cell_range=f"{first_col}:{last_col}" if first_col else "",
                    )
                    if item:
                        units.append(item)
        finally:
            workbook.close()
    elif extension == "csv":
        reader = csv.reader(io.StringIO(content.decode("utf-8-sig"), newline=""))
        for row_index, row in enumerate(reader, start=1):
            item = _unit(" | ".join(row), "csv_row", row=row_index)
            if item:
                units.append(item)
    elif extension == "pptx":
        from pptx import Presentation

        presentation = Presentation(io.BytesIO(content))
        for slide_number, slide in enumerate(presentation.slides, start=1):
            parts: list[str] = []
            for shape in slide.shapes:
                if getattr(shape, "has_text_frame", False):
                    if shape.text.strip():
                        parts.append(shape.text)
                if getattr(shape, "has_table", False):
                    for row in shape.table.rows:
                        parts.append(" | ".join(cell.text for cell in row.cells))
            if slide.has_notes_slide:
                notes = slide.notes_slide.notes_text_frame.text
                if notes.strip():
                    parts.append(f"Speaker notes: {notes}")
            item = _unit("\n".join(parts), "slide", slide=slide_number)
            if item:
                units.append(item)
    elif extension == "txt":
        text = content.decode("utf-8-sig")
        for index, block in enumerate(re.split(r"\n\s*\n", text), start=1):
            item = _unit(block, "text_block", block=index)
            if item:
                units.append(item)
    else:
        raise ValueError(f"Extraction is not supported for .{extension} files yet.")

    return units


def chunk_units(units: list[ExtractedUnit], *, max_chars: int = 2400) -> list[dict[str, Any]]:
    """Create deterministic retrieval chunks without crossing source-unit boundaries."""
    chunks: list[dict[str, Any]] = []
    for unit_index, unit in enumerate(units):
        text = unit.text
        parts = [text[i:i + max_chars] for i in range(0, len(text), max_chars)]
        for part_index, part in enumerate(parts):
            locator = {**unit.locator, "unit_index": unit_index, "part": part_index + 1}
            digest = sha256(
                (unit.locator_type + "\0" + json.dumps(locator, sort_keys=True) + "\0" + part).encode()
            ).hexdigest()
            chunks.append({
                "content": part,
                "locator_type": unit.locator_type,
                "locator": locator,
                "content_sha256": digest,
            })
    return chunks
