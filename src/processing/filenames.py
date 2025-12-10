"""
Clean and normalize student submission filenames.

This module removes mojibake, fixes unicode issues, extracts a clean
student name, and renames files safely for downstream processing.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from pathlib import Path

from src.utils.logging import get_logger

logger = get_logger(__name__)

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".doc"}


def fix_mojibake(text: str) -> str:
    """
    Fix common mojibake/encoding issues in text.
    Uses automatic encoding detection to fix UTF-8 decoded as Latin-1.
    """
    result = text

    # Try to fix UTF-8 that was incorrectly decoded as Latin-1
    try:
        result = result.encode("latin-1").decode("utf-8")
    except (UnicodeDecodeError, UnicodeEncodeError):
        pass

    return result


def to_ascii(text: str) -> str:
    """
    Convert text to ASCII-only using unidecode if available.
    """
    try:
        from unidecode import unidecode
        return unidecode(text)
    except ImportError:
        nfkd = unicodedata.normalize("NFKD", text)
        ascii_text = "".join(c for c in nfkd if not unicodedata.combining(c))
        return ascii_text.encode("ascii", "ignore").decode("ascii")


def to_title_case(text: str) -> str:
    """
    Convert words to Title Case.
    """
    words = re.split(r"[\\s_]+", text)
    titled = [w.capitalize() for w in words if w]
    return " ".join(titled)


def extract_student_name(filename: str) -> str:
    """
    Extract full student name from filename.

    Handles Moodle-style filenames like:
    - "Nombre Apellido_12345_assignsubmission_file_trabajo.pdf"
    - "Nombre_Apellido_12345_assignsubmission_file_trabajo.pdf"

    Returns the full name portion before any Moodle metadata.
    """
    stem = Path(filename).stem

    # Pattern to detect Moodle submission metadata
    # Looks for _NUMBER_assignsubmission or similar patterns
    moodle_pattern = r"_\d+_assignsubmission"
    match = re.search(moodle_pattern, stem, re.IGNORECASE)

    if match:
        # Return everything before the Moodle metadata
        return stem[:match.start()]

    # Also handle pattern with just numeric ID followed by underscore
    # e.g., "Nombre_Apellido_12345_file.pdf"
    numeric_pattern = r"_\d{4,}_"
    match = re.search(numeric_pattern, stem)

    if match:
        return stem[:match.start()]

    # No Moodle pattern found - return full stem
    return stem


def clean_name(raw_name: str) -> str:
    """
    Normalize student name safely.
    """
    name = fix_mojibake(raw_name)
    name = unicodedata.normalize("NFC", name)
    name = to_ascii(name)
    name = to_title_case(name)
    name = name.replace(" ", "_")
    name = re.sub(r"[^A-Za-z0-9_]", "", name)
    name = re.sub(r"_+", "_", name)
    return name.strip("_") or "Unknown"


def clean_filename(filename: str) -> str:
    """
    Clean a filename by extracting student name and normalizing it.
    """
    raw_name = extract_student_name(filename)
    clean = clean_name(raw_name)
    extension = Path(filename).suffix.lower()
    return f"{clean}{extension}"


def preview_renames(directory: Path) -> list[tuple[Path, Path]]:
    """
    Preview what files would be renamed without actually renaming them.
    Returns list of (old_path, new_path) tuples.
    """
    if not directory.exists():
        raise FileNotFoundError(f"Directory not found: {directory}")

    if not directory.is_dir():
        raise ValueError(f"Not a directory: {directory}")

    # Collect files
    files_to_process = []
    for ext in SUPPORTED_EXTENSIONS:
        files_to_process.extend(directory.glob(f"*{ext}"))
        files_to_process.extend(directory.glob(f"*{ext.upper()}"))

    files_to_process = sorted(set(files_to_process))

    preview_results = []
    seen_targets: dict[Path, int] = {}

    for old_path in files_to_process:
        raw_name = extract_student_name(old_path.name)
        clean = clean_name(raw_name)
        extension = old_path.suffix.lower()

        target_path = directory / f"{clean}{extension}"

        # Handle duplicates in preview
        if target_path in seen_targets:
            seen_targets[target_path] += 1
            stem = target_path.stem
            suffix = target_path.suffix
            target_path = directory / f"{stem}_{seen_targets[target_path]}{suffix}"
        else:
            seen_targets[target_path] = 1

        if old_path != target_path:
            preview_results.append((old_path, target_path))

    return preview_results


def get_unique_path(target_path: Path) -> Path:
    """
    Ensure unique filename by appending _2, _3, etc.
    """
    if not target_path.exists():
        return target_path

    stem = target_path.stem
    suffix = target_path.suffix
    parent = target_path.parent

    counter = 2
    while counter < 1000:
        new_path = parent / f"{stem}_{counter}{suffix}"
        if not new_path.exists():
            return new_path
        counter += 1

    raise RuntimeError(f"Too many files with base name {stem}")


def clean_and_rename_files(directory: Path) -> list[tuple[Path, Path]]:
    """
    Clean and rename all files inside directory.
    """
    if not directory.exists():
        raise FileNotFoundError(f"Directory not found: {directory}")

    if not directory.is_dir():
        raise ValueError(f"Not a directory: {directory}")

    logger.info(f"Cleaning filenames in: {directory}")

    # Collect files
    files_to_process = []
    for ext in SUPPORTED_EXTENSIONS:
        files_to_process.extend(directory.glob(f"*{ext}"))
        files_to_process.extend(directory.glob(f"*{ext.upper()}"))

    files_to_process = sorted(set(files_to_process))

    if not files_to_process:
        logger.warning(f"No supported files found in {directory}")
        return []

    rename_results = []
    log_entries = [
        f"Rename Log - {datetime.now().isoformat()}",
        f"Directory: {directory}",
        "=" * 60,
        ""
    ]

    for old_path in files_to_process:
        try:
            raw_name = extract_student_name(old_path.name)
            clean = clean_name(raw_name)
            extension = old_path.suffix.lower()

            target_path = directory / f"{clean}{extension}"
            new_path = get_unique_path(target_path)

            if old_path == new_path:
                log_entries.append(f"SKIP: {old_path.name}")
                continue

            old_path.rename(new_path)
            rename_results.append((old_path, new_path))

            log_entries.append(f"{old_path.name} -> {new_path.name}")

        except Exception as e:
            logger.error(f"Error processing {old_path.name}: {e}")
            log_entries.append(f"ERROR: {old_path.name} - {e}")

    log_entries.append("")
    log_entries.append("=" * 60)
    log_entries.append(f"Total files: {len(files_to_process)}")
    log_entries.append(f"Renamed: {len(rename_results)}")
    log_entries.append(f"Skipped: {len(files_to_process) - len(rename_results)}")

    # Write log
    log_path = directory / "rename_log.txt"
    try:
        log_path.write_text("\n".join(log_entries), encoding="utf-8")
    except Exception as e:
        logger.error(f"Could not write rename log: {e}")

    return rename_results
