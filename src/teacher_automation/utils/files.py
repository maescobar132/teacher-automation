"""File handling utilities."""

import re
import unicodedata
from pathlib import Path


def ensure_dir(path: Path) -> Path:
    """Ensure a directory exists, creating it if necessary.

    Args:
        path: Directory path to ensure exists

    Returns:
        The path (for chaining)
    """
    path.mkdir(parents=True, exist_ok=True)
    return path


def safe_filename(name: str, max_length: int = 255) -> str:
    """Convert a string to a safe filename.

    Removes or replaces characters that are problematic in filenames
    across different operating systems.

    Args:
        name: Original filename or string
        max_length: Maximum length of the resulting filename

    Returns:
        Safe filename string
    """
    # Normalize unicode characters
    name = unicodedata.normalize("NFKD", name)
    name = name.encode("ascii", "ignore").decode("ascii")

    # Replace spaces with underscores
    name = name.replace(" ", "_")

    # Remove characters that are problematic in filenames
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", name)

    # Remove leading/trailing dots and spaces
    name = name.strip(". ")

    # Truncate if necessary
    if len(name) > max_length:
        name = name[:max_length]

    # Ensure we have something
    if not name:
        name = "unnamed"

    return name


def get_file_extension(path: Path) -> str:
    """Get the file extension in lowercase without the dot.

    Args:
        path: File path

    Returns:
        Lowercase extension without dot, or empty string
    """
    return path.suffix.lower().lstrip(".")


def is_supported_document(path: Path, extensions: set[str] | None = None) -> bool:
    """Check if a file is a supported document type.

    Args:
        path: File path to check
        extensions: Set of supported extensions (without dots)

    Returns:
        True if the file extension is supported
    """
    if extensions is None:
        extensions = {"pdf", "docx", "doc", "txt", "md", "py", "java", "js", "ts", "cpp", "c", "h"}

    return get_file_extension(path) in extensions
