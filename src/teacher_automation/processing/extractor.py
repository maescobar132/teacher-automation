"""
Submission file extraction and handling.

Provides utilities for extracting, organizing, and renaming
student submission files from various archive formats.
"""

import re
import shutil
import tarfile
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

from ..utils.files import ensure_dir, safe_filename
from ..utils.logging import get_logger
from .filetypes import FileType, detect_filetype, is_archive, GZIP, ZIP, TAR

logger = get_logger(__name__)


# -----------------------------------------------------------------------------
# Exceptions
# -----------------------------------------------------------------------------


class ExtractionError(Exception):
    """Error during archive extraction."""

    pass


class UnsupportedArchiveError(ExtractionError):
    """Archive format not supported."""

    pass


# -----------------------------------------------------------------------------
# Data Classes
# -----------------------------------------------------------------------------


@dataclass
class ExtractedFile:
    """Represents an extracted file with metadata."""

    original_path: Path
    extracted_path: Path
    file_type: FileType
    size_bytes: int
    is_main_file: bool = False

    @property
    def extension(self) -> str:
        """Get file extension without dot."""
        return self.extracted_path.suffix.lower().lstrip(".")


@dataclass
class ExtractionResult:
    """Result of an extraction operation."""

    source_path: Path
    output_dir: Path
    files: list[ExtractedFile]
    success: bool
    error_message: str = ""

    @property
    def file_count(self) -> int:
        """Get total number of extracted files."""
        return len(self.files)

    @property
    def total_size(self) -> int:
        """Get total size of extracted files in bytes."""
        return sum(f.size_bytes for f in self.files)

    def get_files_by_type(self, extension: str) -> list[ExtractedFile]:
        """Get files by extension."""
        return [f for f in self.files if f.extension == extension]

    def get_main_file(self) -> ExtractedFile | None:
        """Get the main file if one was identified."""
        for f in self.files:
            if f.is_main_file:
                return f
        return None


# -----------------------------------------------------------------------------
# Renaming Functions
# -----------------------------------------------------------------------------


def rename_file(
    source: Path,
    new_name: str | None = None,
    new_stem: str | None = None,
    prefix: str = "",
    suffix: str = "",
    sanitize: bool = True,
) -> Path:
    """
    Rename a file with various options.

    Args:
        source: Path to the file to rename
        new_name: Complete new filename (with extension)
        new_stem: New filename stem (without extension)
        prefix: Prefix to add to filename
        suffix: Suffix to add before extension
        sanitize: Whether to sanitize the filename

    Returns:
        Path to the renamed file

    Raises:
        FileNotFoundError: If source doesn't exist
        ValueError: If neither new_name nor new_stem is provided
    """
    if not source.exists():
        raise FileNotFoundError(f"Source file not found: {source}")

    if new_name:
        # Use complete new name
        target_name = new_name
    elif new_stem:
        # Use new stem with original extension
        target_name = f"{new_stem}{source.suffix}"
    else:
        # Use prefix/suffix with original name
        stem = source.stem
        ext = source.suffix
        target_name = f"{prefix}{stem}{suffix}{ext}"

    if sanitize:
        # Sanitize but preserve extension
        name_part = Path(target_name).stem
        ext_part = Path(target_name).suffix
        target_name = f"{safe_filename(name_part)}{ext_part}"

    target = source.parent / target_name

    if target == source:
        return source

    # Handle existing target
    if target.exists():
        # Add timestamp to make unique
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        stem = Path(target_name).stem
        ext = Path(target_name).suffix
        target_name = f"{stem}_{timestamp}{ext}"
        target = source.parent / target_name

    source.rename(target)
    logger.debug(f"Renamed {source.name} -> {target.name}")
    return target


def rename_for_submission(
    file_path: Path,
    student_id: str,
    assignment_code: str,
    attempt: int = 1,
) -> Path:
    """
    Rename a file using a standardized submission naming convention.

    Format: {student_id}_{assignment_code}_attempt{N}.{ext}

    Args:
        file_path: Path to the file
        student_id: Student identifier
        assignment_code: Assignment code
        attempt: Attempt number

    Returns:
        Path to the renamed file
    """
    ext = file_path.suffix
    new_stem = f"{safe_filename(student_id)}_{safe_filename(assignment_code)}_attempt{attempt}"
    return rename_file(file_path, new_stem=new_stem)


def batch_rename(
    directory: Path,
    pattern: str,
    replacement: str | Callable[[re.Match], str],
    recursive: bool = False,
    dry_run: bool = False,
) -> list[tuple[Path, Path]]:
    """
    Batch rename files matching a pattern.

    Args:
        directory: Directory containing files
        pattern: Regex pattern to match in filenames
        replacement: Replacement string or function
        recursive: Whether to process subdirectories
        dry_run: If True, return changes without applying

    Returns:
        List of (original_path, new_path) tuples
    """
    changes = []
    regex = re.compile(pattern)

    iterator = directory.rglob("*") if recursive else directory.iterdir()

    for path in iterator:
        if not path.is_file():
            continue

        new_name = regex.sub(replacement, path.name)
        if new_name != path.name:
            new_path = path.parent / new_name
            changes.append((path, new_path))

            if not dry_run:
                path.rename(new_path)
                logger.debug(f"Renamed {path.name} -> {new_name}")

    logger.info(f"Batch rename: {len(changes)} files {'would be' if dry_run else ''} renamed")
    return changes


# -----------------------------------------------------------------------------
# Extraction Functions
# -----------------------------------------------------------------------------


def unzip(
    zip_path: Path,
    output_dir: Path | None = None,
    password: str | None = None,
    flatten: bool = False,
) -> ExtractionResult:
    """
    Extract a ZIP archive.

    Args:
        zip_path: Path to the ZIP file
        output_dir: Directory to extract to (defaults to zip location)
        password: Password for encrypted archives
        flatten: If True, extract all files to root (ignore directory structure)

    Returns:
        ExtractionResult with extracted file information

    Raises:
        ExtractionError: If extraction fails
    """
    if not zip_path.exists():
        raise ExtractionError(f"ZIP file not found: {zip_path}")

    if output_dir is None:
        output_dir = zip_path.parent / zip_path.stem

    ensure_dir(output_dir)
    logger.info(f"Extracting ZIP: {zip_path} -> {output_dir}")

    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            # Check for password protection
            pwd = password.encode() if password else None

            extracted_files = []

            for member in zf.infolist():
                # Skip directories
                if member.is_dir():
                    continue

                # Skip hidden/system files
                if _should_skip_file(member.filename):
                    continue

                if flatten:
                    # Extract to root, using only filename
                    target_name = Path(member.filename).name
                    target_path = output_dir / safe_filename(target_name)

                    # Handle duplicates
                    counter = 1
                    while target_path.exists():
                        stem = Path(target_name).stem
                        ext = Path(target_name).suffix
                        target_path = output_dir / f"{stem}_{counter}{ext}"
                        counter += 1

                    with zf.open(member, pwd=pwd) as src:
                        target_path.write_bytes(src.read())
                else:
                    # Normal extraction with directory structure
                    zf.extract(member, output_dir, pwd=pwd)
                    target_path = output_dir / member.filename

                extracted_files.append(
                    ExtractedFile(
                        original_path=Path(member.filename),
                        extracted_path=target_path,
                        file_type=detect_filetype(target_path),
                        size_bytes=member.file_size,
                    )
                )

            logger.info(f"Extracted {len(extracted_files)} files from ZIP")

            return ExtractionResult(
                source_path=zip_path,
                output_dir=output_dir,
                files=extracted_files,
                success=True,
            )

    except zipfile.BadZipFile as e:
        logger.error(f"Invalid ZIP file: {e}")
        raise ExtractionError(f"Invalid ZIP file: {zip_path}") from e
    except RuntimeError as e:
        # Password required or incorrect
        if "password" in str(e).lower():
            raise ExtractionError(f"Password required or incorrect for: {zip_path}") from e
        raise ExtractionError(f"Extraction failed: {e}") from e


def untar(
    tar_path: Path,
    output_dir: Path | None = None,
    flatten: bool = False,
) -> ExtractionResult:
    """
    Extract a TAR archive (including .tar.gz, .tgz).

    Args:
        tar_path: Path to the TAR file
        output_dir: Directory to extract to
        flatten: If True, extract all files to root

    Returns:
        ExtractionResult with extracted file information
    """
    if not tar_path.exists():
        raise ExtractionError(f"TAR file not found: {tar_path}")

    if output_dir is None:
        # Handle .tar.gz, .tgz extensions
        stem = tar_path.stem
        if stem.endswith(".tar"):
            stem = stem[:-4]
        output_dir = tar_path.parent / stem

    ensure_dir(output_dir)
    logger.info(f"Extracting TAR: {tar_path} -> {output_dir}")

    # Determine compression mode
    mode = "r"
    suffix = tar_path.suffix.lower()
    if suffix in (".gz", ".tgz"):
        mode = "r:gz"
    elif suffix == ".bz2":
        mode = "r:bz2"
    elif suffix == ".xz":
        mode = "r:xz"

    try:
        with tarfile.open(tar_path, mode) as tf:
            extracted_files = []

            for member in tf.getmembers():
                if not member.isfile():
                    continue

                if _should_skip_file(member.name):
                    continue

                if flatten:
                    target_name = Path(member.name).name
                    target_path = output_dir / safe_filename(target_name)

                    # Handle duplicates
                    counter = 1
                    while target_path.exists():
                        stem = Path(target_name).stem
                        ext = Path(target_name).suffix
                        target_path = output_dir / f"{stem}_{counter}{ext}"
                        counter += 1

                    with tf.extractfile(member) as src:
                        if src:
                            target_path.write_bytes(src.read())
                else:
                    tf.extract(member, output_dir)
                    target_path = output_dir / member.name

                extracted_files.append(
                    ExtractedFile(
                        original_path=Path(member.name),
                        extracted_path=target_path,
                        file_type=detect_filetype(target_path),
                        size_bytes=member.size,
                    )
                )

            logger.info(f"Extracted {len(extracted_files)} files from TAR")

            return ExtractionResult(
                source_path=tar_path,
                output_dir=output_dir,
                files=extracted_files,
                success=True,
            )

    except tarfile.TarError as e:
        logger.error(f"TAR extraction failed: {e}")
        raise ExtractionError(f"TAR extraction failed: {e}") from e


def extract_archive(
    archive_path: Path,
    output_dir: Path | None = None,
    password: str | None = None,
    flatten: bool = False,
) -> ExtractionResult:
    """
    Extract any supported archive format.

    Automatically detects the archive type and uses the appropriate
    extraction method.

    Args:
        archive_path: Path to the archive
        output_dir: Directory to extract to
        password: Password for encrypted archives (ZIP only)
        flatten: If True, ignore directory structure

    Returns:
        ExtractionResult with extracted file information

    Raises:
        UnsupportedArchiveError: If archive format not supported
        ExtractionError: If extraction fails
    """
    file_type = detect_filetype(archive_path)

    if file_type == ZIP:
        return unzip(archive_path, output_dir, password, flatten)
    elif file_type in (TAR, GZIP):
        return untar(archive_path, output_dir, flatten)
    elif archive_path.suffix.lower() in (".tar", ".tgz", ".tar.gz", ".tar.bz2", ".tar.xz"):
        return untar(archive_path, output_dir, flatten)
    else:
        raise UnsupportedArchiveError(f"Unsupported archive format: {archive_path.suffix}")


def _should_skip_file(filename: str) -> bool:
    """Check if a file should be skipped during extraction."""
    name = Path(filename).name

    # Skip hidden files and directories
    if name.startswith("."):
        return True

    # Skip macOS resource forks
    if name.startswith("__MACOSX") or name.startswith("._"):
        return True

    # Skip Windows thumbnails
    if name.lower() == "thumbs.db":
        return True

    # Skip desktop.ini
    if name.lower() == "desktop.ini":
        return True

    return False


# -----------------------------------------------------------------------------
# Submission Extractor Class
# -----------------------------------------------------------------------------


class SubmissionExtractor:
    """Extracts and organizes submission files."""

    def __init__(self, output_dir: Path):
        """Initialize the extractor.

        Args:
            output_dir: Base directory for extracted files
        """
        self.output_dir = ensure_dir(output_dir)

    def extract_zip(self, zip_path: Path, submission_id: str) -> Path:
        """Extract a ZIP file submission.

        Args:
            zip_path: Path to the ZIP file
            submission_id: Unique identifier for the submission

        Returns:
            Path to the extraction directory
        """
        extract_dir = self.output_dir / safe_filename(submission_id)
        result = unzip(zip_path, extract_dir)
        return result.output_dir

    def extract_submission(
        self,
        file_path: Path,
        submission_id: str,
        flatten: bool = False,
    ) -> ExtractionResult:
        """
        Extract a submission file (archive or single file).

        Args:
            file_path: Path to the submission file
            submission_id: Unique identifier for the submission
            flatten: If True, flatten directory structure

        Returns:
            ExtractionResult with file information
        """
        extract_dir = self.output_dir / safe_filename(submission_id)
        ensure_dir(extract_dir)

        if is_archive(file_path):
            return extract_archive(file_path, extract_dir, flatten=flatten)
        else:
            # Single file - just copy it
            target = extract_dir / file_path.name
            shutil.copy2(file_path, target)

            file_type = detect_filetype(target)

            return ExtractionResult(
                source_path=file_path,
                output_dir=extract_dir,
                files=[
                    ExtractedFile(
                        original_path=file_path,
                        extracted_path=target,
                        file_type=file_type,
                        size_bytes=target.stat().st_size,
                        is_main_file=True,
                    )
                ],
                success=True,
            )

    def organize_files(self, source_dir: Path, file_types: set[str] | None = None) -> dict[str, list[Path]]:
        """Organize extracted files by type.

        Args:
            source_dir: Directory containing files
            file_types: Set of file extensions to include

        Returns:
            Dict mapping file types to lists of file paths
        """
        if file_types is None:
            file_types = {"py", "java", "js", "ts", "cpp", "c", "txt", "pdf", "docx"}

        organized: dict[str, list[Path]] = {}

        for path in source_dir.rglob("*"):
            if path.is_file():
                ext = path.suffix.lower().lstrip(".")
                if ext in file_types:
                    if ext not in organized:
                        organized[ext] = []
                    organized[ext].append(path)

        logger.info(f"Organized {sum(len(v) for v in organized.values())} files into {len(organized)} categories")
        return organized

    def get_main_file(self, files: dict[str, list[Path]], priority: list[str] | None = None) -> Path | None:
        """Get the main submission file based on priority.

        Args:
            files: Organized files dict
            priority: List of extensions in priority order

        Returns:
            Path to the main file, or None if no suitable file found
        """
        if priority is None:
            priority = ["py", "java", "js", "cpp", "c", "txt", "pdf", "docx"]

        for ext in priority:
            if ext in files and files[ext]:
                # Return the first (or largest) file of this type
                return max(files[ext], key=lambda p: p.stat().st_size)

        return None
