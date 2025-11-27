"""
File type detection and validation.

Provides robust file type detection using both file extensions
and magic bytes (file signatures) for reliable identification.
"""

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import BinaryIO

from ..utils.logging import get_logger

logger = get_logger(__name__)


class FileCategory(Enum):
    """Categories of supported file types."""

    DOCUMENT = "document"
    CODE = "code"
    ARCHIVE = "archive"
    IMAGE = "image"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class FileType:
    """Represents a detected file type."""

    extension: str
    mime_type: str
    category: FileCategory
    description: str

    @property
    def is_text_based(self) -> bool:
        """Check if this file type contains text content."""
        return self.category in (FileCategory.DOCUMENT, FileCategory.CODE) or self.extension in (
            "txt",
            "md",
            "csv",
            "json",
            "xml",
            "html",
        )


# -----------------------------------------------------------------------------
# Known File Types
# -----------------------------------------------------------------------------

# Document types
PDF = FileType("pdf", "application/pdf", FileCategory.DOCUMENT, "PDF Document")
DOCX = FileType("docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", FileCategory.DOCUMENT, "Microsoft Word Document")
DOC = FileType("doc", "application/msword", FileCategory.DOCUMENT, "Microsoft Word Document (Legacy)")
ODT = FileType("odt", "application/vnd.oasis.opendocument.text", FileCategory.DOCUMENT, "OpenDocument Text")
RTF = FileType("rtf", "application/rtf", FileCategory.DOCUMENT, "Rich Text Format")
TXT = FileType("txt", "text/plain", FileCategory.DOCUMENT, "Plain Text")
MD = FileType("md", "text/markdown", FileCategory.DOCUMENT, "Markdown")

# Code types
PYTHON = FileType("py", "text/x-python", FileCategory.CODE, "Python Source")
JAVA = FileType("java", "text/x-java-source", FileCategory.CODE, "Java Source")
JAVASCRIPT = FileType("js", "text/javascript", FileCategory.CODE, "JavaScript Source")
TYPESCRIPT = FileType("ts", "text/typescript", FileCategory.CODE, "TypeScript Source")
CPP = FileType("cpp", "text/x-c++src", FileCategory.CODE, "C++ Source")
C = FileType("c", "text/x-csrc", FileCategory.CODE, "C Source")
HEADER = FileType("h", "text/x-chdr", FileCategory.CODE, "C/C++ Header")
CSHARP = FileType("cs", "text/x-csharp", FileCategory.CODE, "C# Source")
HTML = FileType("html", "text/html", FileCategory.CODE, "HTML Document")
CSS = FileType("css", "text/css", FileCategory.CODE, "CSS Stylesheet")
JSON = FileType("json", "application/json", FileCategory.CODE, "JSON Data")
XML = FileType("xml", "application/xml", FileCategory.CODE, "XML Document")

# Archive types
ZIP = FileType("zip", "application/zip", FileCategory.ARCHIVE, "ZIP Archive")
RAR = FileType("rar", "application/vnd.rar", FileCategory.ARCHIVE, "RAR Archive")
SEVENZ = FileType("7z", "application/x-7z-compressed", FileCategory.ARCHIVE, "7-Zip Archive")
GZIP = FileType("gz", "application/gzip", FileCategory.ARCHIVE, "Gzip Archive")
TAR = FileType("tar", "application/x-tar", FileCategory.ARCHIVE, "TAR Archive")

# Image types (for embedded content)
PNG = FileType("png", "image/png", FileCategory.IMAGE, "PNG Image")
JPEG = FileType("jpg", "image/jpeg", FileCategory.IMAGE, "JPEG Image")
GIF = FileType("gif", "image/gif", FileCategory.IMAGE, "GIF Image")

# Unknown
UNKNOWN = FileType("", "application/octet-stream", FileCategory.UNKNOWN, "Unknown File Type")


# -----------------------------------------------------------------------------
# Magic Bytes Signatures
# -----------------------------------------------------------------------------

# File signatures (magic bytes) for reliable detection
# Format: (signature_bytes, offset, file_type)
MAGIC_SIGNATURES: list[tuple[bytes, int, FileType]] = [
    # PDF
    (b"%PDF", 0, PDF),

    # Microsoft Office (OOXML - docx, xlsx, pptx are ZIP-based)
    # DOCX is detected by ZIP signature + content check
    (b"PK\x03\x04", 0, ZIP),  # ZIP signature (also DOCX, XLSX, etc.)

    # Legacy Microsoft Office
    (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1", 0, DOC),  # OLE2 compound document

    # RTF
    (b"{\\rtf", 0, RTF),

    # Archives
    (b"Rar!\x1a\x07", 0, RAR),
    (b"7z\xbc\xaf\x27\x1c", 0, SEVENZ),
    (b"\x1f\x8b", 0, GZIP),

    # Images
    (b"\x89PNG\r\n\x1a\n", 0, PNG),
    (b"\xff\xd8\xff", 0, JPEG),
    (b"GIF87a", 0, GIF),
    (b"GIF89a", 0, GIF),
]

# Extension to FileType mapping
EXTENSION_MAP: dict[str, FileType] = {
    # Documents
    "pdf": PDF,
    "docx": DOCX,
    "doc": DOC,
    "odt": ODT,
    "rtf": RTF,
    "txt": TXT,
    "md": MD,
    "markdown": MD,

    # Code
    "py": PYTHON,
    "pyw": PYTHON,
    "java": JAVA,
    "js": JAVASCRIPT,
    "mjs": JAVASCRIPT,
    "ts": TYPESCRIPT,
    "tsx": TYPESCRIPT,
    "cpp": CPP,
    "cc": CPP,
    "cxx": CPP,
    "c": C,
    "h": HEADER,
    "hpp": HEADER,
    "hxx": HEADER,
    "cs": CSHARP,
    "html": HTML,
    "htm": HTML,
    "css": CSS,
    "json": JSON,
    "xml": XML,

    # Archives
    "zip": ZIP,
    "rar": RAR,
    "7z": SEVENZ,
    "gz": GZIP,
    "tar": TAR,
    "tgz": TAR,

    # Images
    "png": PNG,
    "jpg": JPEG,
    "jpeg": JPEG,
    "gif": GIF,
}


# -----------------------------------------------------------------------------
# Detection Functions
# -----------------------------------------------------------------------------


def detect_by_extension(path: Path) -> FileType:
    """
    Detect file type by extension.

    Args:
        path: Path to the file

    Returns:
        Detected FileType or UNKNOWN
    """
    ext = path.suffix.lower().lstrip(".")
    return EXTENSION_MAP.get(ext, UNKNOWN)


def detect_by_magic(path: Path) -> FileType:
    """
    Detect file type by magic bytes (file signature).

    Args:
        path: Path to the file

    Returns:
        Detected FileType or UNKNOWN
    """
    if not path.exists() or not path.is_file():
        return UNKNOWN

    try:
        with open(path, "rb") as f:
            return _detect_magic_from_stream(f)
    except (OSError, IOError) as e:
        logger.warning(f"Could not read file for magic detection: {e}")
        return UNKNOWN


def _detect_magic_from_stream(stream: BinaryIO) -> FileType:
    """Detect file type from a binary stream."""
    # Read enough bytes to check all signatures
    max_offset = max(offset + len(sig) for sig, offset, _ in MAGIC_SIGNATURES)
    header = stream.read(max_offset)

    for signature, offset, file_type in MAGIC_SIGNATURES:
        if len(header) >= offset + len(signature):
            if header[offset : offset + len(signature)] == signature:
                return file_type

    return UNKNOWN


def detect_filetype(path: Path, trust_extension: bool = True) -> FileType:
    """
    Detect file type using both extension and magic bytes.

    Uses a combination of extension and magic byte detection for
    reliable file type identification.

    Args:
        path: Path to the file
        trust_extension: If True, prefer extension for text files

    Returns:
        Detected FileType
    """
    ext_type = detect_by_extension(path)
    magic_type = detect_by_magic(path)

    # If magic detection found something specific, prefer it
    if magic_type != UNKNOWN:
        # Special case: ZIP-based formats (docx, xlsx, etc.)
        if magic_type == ZIP and ext_type in (DOCX,):
            # Check if it's actually a DOCX by looking for specific content
            if _is_docx(path):
                return DOCX
            return ext_type if ext_type != UNKNOWN else magic_type

        return magic_type

    # For text-based files, trust the extension
    if trust_extension and ext_type.is_text_based:
        return ext_type

    return ext_type if ext_type != UNKNOWN else UNKNOWN


def _is_docx(path: Path) -> bool:
    """Check if a ZIP file is actually a DOCX document."""
    import zipfile

    try:
        with zipfile.ZipFile(path, "r") as zf:
            # DOCX files contain a specific content types file
            return "[Content_Types].xml" in zf.namelist() and any(
                name.startswith("word/") for name in zf.namelist()
            )
    except (zipfile.BadZipFile, OSError):
        return False


def is_supported_document(path: Path) -> bool:
    """
    Check if a file is a supported document type.

    Args:
        path: Path to check

    Returns:
        True if the file is a supported document (PDF, DOCX, TXT, etc.)
    """
    file_type = detect_filetype(path)
    return file_type.category == FileCategory.DOCUMENT


def is_archive(path: Path) -> bool:
    """
    Check if a file is an archive.

    Args:
        path: Path to check

    Returns:
        True if the file is an archive (ZIP, RAR, etc.)
    """
    file_type = detect_filetype(path)
    return file_type.category == FileCategory.ARCHIVE


def is_code_file(path: Path) -> bool:
    """
    Check if a file is a source code file.

    Args:
        path: Path to check

    Returns:
        True if the file is source code
    """
    file_type = detect_filetype(path)
    return file_type.category == FileCategory.CODE


def get_supported_extensions(category: FileCategory | None = None) -> set[str]:
    """
    Get set of supported file extensions.

    Args:
        category: Optional category to filter by

    Returns:
        Set of extension strings (without dots)
    """
    if category is None:
        return set(EXTENSION_MAP.keys())

    return {ext for ext, ft in EXTENSION_MAP.items() if ft.category == category}


def validate_file(path: Path, allowed_types: set[FileType] | None = None) -> tuple[bool, FileType, str]:
    """
    Validate a file against allowed types.

    Args:
        path: Path to the file
        allowed_types: Set of allowed FileTypes (None = all)

    Returns:
        Tuple of (is_valid, detected_type, error_message)
    """
    if not path.exists():
        return False, UNKNOWN, f"File does not exist: {path}"

    if not path.is_file():
        return False, UNKNOWN, f"Path is not a file: {path}"

    detected = detect_filetype(path)

    if detected == UNKNOWN:
        return False, UNKNOWN, f"Could not determine file type: {path}"

    if allowed_types is not None and detected not in allowed_types:
        allowed_str = ", ".join(t.extension for t in allowed_types)
        return False, detected, f"File type '{detected.extension}' not allowed. Allowed: {allowed_str}"

    return True, detected, ""
