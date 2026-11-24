from __future__ import annotations

import io
import zipfile

import pytest

from charvi_api.knowledge import MAX_FILE_BYTES, validate_file


def test_pdf_signature_is_required():
    result = validate_file("report.pdf", b"%PDF-1.7 sample")
    assert result.mime_type == "application/pdf"


def test_extension_cannot_disguise_another_file_type():
    with pytest.raises(ValueError, match="do not match"):
        validate_file("report.pdf", b"not a pdf")


def test_csv_must_be_utf8_text_without_nul_bytes():
    assert validate_file("data.csv", b"a,b\n1,2").mime_type == "text/csv"
    with pytest.raises(ValueError, match="do not match"):
        validate_file("data.csv", b"a\x00b")


def test_png_signature_is_required():
    result = validate_file("scan.png", b"\x89PNG\\r\n\x1a\n" + b"data")
    assert result.mime_type == "image/png"


def test_docx_is_checked_as_an_office_zip_package():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", "<document/>")
    assert validate_file("agreement.docx", buffer.getvalue()).extension == "docx"
    with pytest.raises(ValueError, match="do not match"):
        validate_file("agreement.docx", b"PK\x03\x04not-a-package")


def test_oversized_file_is_rejected():
    with pytest.raises(ValueError, match="15 MB"):
        validate_file("large.pdf", b"x" * (MAX_FILE_BYTES + 1))


def test_unsafe_filename_is_rejected():
    with pytest.raises(ValueError, match="Invalid filename"):
        validate_file("../report.pdf", b"%PDF-1.7")
