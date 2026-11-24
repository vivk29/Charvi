"""File type validation helpers for Charvi's private knowledge vault."""

import dataclasses
import io
import zipfile


MAX_FILE_BYTES = 15 * 1024 * 1024


@dataclasses.dataclass(frozen=True)
class ValidatedFile:
    extension: str
    mime_type: str


MIME_BY_EXTENSION = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "doc": "application/msword",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "xls": "application/vnd.ms-excel",
    "csv": "text/csv",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "ppt": "application/vnd.ms-powerpoint",
    "txt": "text/plain",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
}

OLE_SIGNATURE = bytes.fromhex("D0CF11E0A1B11AE1")


def validate_file(filename: str, content: bytes) -> ValidatedFile:
    """Validate extension against file signatures; never trust browser MIME headers."""
    if not content:
        raise ValueError("The file is empty.")
    if len(content) > MAX_FILE_BYTES:
        raise ValueError("Files must be 15 MB or smaller.")
    if not filename or len(filename) > 255 or "/" in filename or "\\" in filename:
        raise ValueError("Invalid filename.")

    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if extension not in MIME_BY_EXTENSION:
        raise ValueError("This file format is not supported.")

    valid = False
    if extension == "pdf":
        valid = content.startswith(b"%PDF-")
    elif extension in {"jpg", "jpeg"}:
        valid = content.startswith(b"\xff\xd8\xff")
    elif extension == "png":
        valid = content.startswith(b"\x89PNG\r\n\x1a\n")
    elif extension == "webp":
        valid = len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP"
    elif extension in {"doc", "xls", "ppt"}:
        valid = content.startswith(OLE_SIGNATURE)
    elif extension in {"docx", "xlsx", "pptx"}:
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                names = set(archive.namelist())
            if "[Content_Types].xml" in names:
                required = {"docx": "word/", "xlsx": "xl/", "pptx": "ppt/"}[extension]
                valid = any(name.startswith(required) for name in names)
        except (zipfile.BadZipFile, OSError):
            valid = False
    elif extension in {"csv", "txt"}:
        try:
            decoded = content.decode("utf-8-sig")
            valid = "\x00" not in decoded
        except UnicodeDecodeError:
            valid = False

    if not valid:
        raise ValueError("The file contents do not match the selected file format.")
    return ValidatedFile(extension=extension, mime_type=MIME_BY_EXTENSION[extension])
