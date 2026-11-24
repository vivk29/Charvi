from __future__ import annotations

import io
import pytest
from docx import Document
from openpyxl import Workbook
from pptx import Presentation

from charvi_api.document_parser import chunk_units, extract_document


def test_csv_rows_keep_exact_row_provenance():
    units = extract_document("csv", b"Name,Amount\nHotel,1200\n")
    assert len(units) == 2
    assert units[0].locator == {"row": 1}
    assert "Hotel" in units[1].text
    assert units[1].locator == {"row": 2}


def test_docx_paragraph_and_table_rows_are_preserved():
    doc = Document()
    doc.add_paragraph("GST reconciliation")
    table = doc.add_table(rows=1, cols=2)
    table.cell(0, 0).text = "Invoice"
    table.cell(0, 1).text = "Taxable value"
    stream = io.BytesIO()
    doc.save(stream)
    units = extract_document("docx", stream.getvalue())
    assert any("GST reconciliation" in item.text for item in units)
    assert any(item.locator_type == "table_row" and "Invoice" in item.text for item in units)


def test_xlsx_preserves_sheet_row_and_cell_addresses():
    book = Workbook()
    sheet = book.active
    sheet.title = "GSTR2B"
    sheet.append(["Invoice", "Taxable value"])
    sheet.append(["INV-1", 1000])
    stream = io.BytesIO()
    book.save(stream)
    units = extract_document("xlsx", stream.getvalue())
    assert units[1].locator["sheet"] == "GSTR2B"
    assert units[1].locator["row"] == 2
    assert "A2=INV-1" in units[1].text
    assert "B2=1000" in units[1].text


def test_pptx_preserves_slide_number():
    deck = Presentation()
    slide = deck.slides.add_slide(deck.slide_layouts[5])
    slide.shapes.title.text = "Quarterly results"
    stream = io.BytesIO()
    deck.save(stream)
    units = extract_document("pptx", stream.getvalue())
    assert units[0].locator == {"slide": 1}
    assert "Quarterly results" in units[0].text


def test_chunks_are_stable_and_keep_locator():
    from charvi_api.document_parser import ExtractedUnit
    units = [ExtractedUnit("a" * 2500, "page", {"page": 3})]
    first = chunk_units(units)
    second = chunk_units(units)
    assert len(first) == 2
    assert first[0]["content_sha256"] == second[0]["content_sha256"]
    assert first[0]["locator"]["page"] == 3


def test_unknown_extension_is_not_silently_accepted():
    with pytest.raises(ValueError, match="not supported"):
        extract_document("xls", b"anything")
