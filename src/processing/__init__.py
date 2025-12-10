"""
Submission processing module.

Handles extraction, parsing, and preparation of student submissions
for grading and plagiarism checking.
"""

# File type detection
from .filetypes import (
    FileType,
    FileCategory,
    detect_filetype,
    detect_by_extension,
    detect_by_magic,
    is_supported_document,
    is_archive,
    is_code_file,
    get_supported_extensions,
    validate_file,
    # Common file types
    PDF,
    DOCX,
    DOC,
    TXT,
    ZIP,
    UNKNOWN,
)

# Extraction and renaming
from .extractor import (
    SubmissionExtractor,
    ExtractedFile,
    ExtractionResult,
    ExtractionError,
    UnsupportedArchiveError,
    # Functions
    unzip,
    untar,
    extract_archive,
    rename_file,
    rename_for_submission,
    batch_rename,
)

# Text extraction and parsing
from .parser import (
    DocumentParser,
    TextExtractionResult,
    PDFMetadata,
    DOCXMetadata,
    ParseError,
    UnsupportedFormatError,
    EncodingError,
    # Functions
    extract_text,
    extract_text_from_pdf,
    extract_text_from_docx,
    extract_text_from_text_file,
    normalize_text,
    count_words,
    extract_sentences,
)

# Filename cleaning and normalization
from .filenames import (
    clean_and_rename_files,
    preview_renames,
    clean_filename,
    extract_student_name,
    fix_mojibake,
    to_ascii,
    to_title_case,
    SUPPORTED_EXTENSIONS,
)

# Submission file discovery
from .submissions import (
    get_submission_files,
    get_student_name,
    extract_tables_from_submission,
    dataframes_to_markdown_context,
    EXTENSION_PRIORITY,
)

__all__ = [
    # File types
    "FileType",
    "FileCategory",
    "detect_filetype",
    "detect_by_extension",
    "detect_by_magic",
    "is_supported_document",
    "is_archive",
    "is_code_file",
    "get_supported_extensions",
    "validate_file",
    "PDF",
    "DOCX",
    "DOC",
    "TXT",
    "ZIP",
    "UNKNOWN",
    # Extraction
    "SubmissionExtractor",
    "ExtractedFile",
    "ExtractionResult",
    "ExtractionError",
    "UnsupportedArchiveError",
    "unzip",
    "untar",
    "extract_archive",
    "rename_file",
    "rename_for_submission",
    "batch_rename",
    # Parsing
    "DocumentParser",
    "TextExtractionResult",
    "PDFMetadata",
    "DOCXMetadata",
    "ParseError",
    "UnsupportedFormatError",
    "EncodingError",
    "extract_text",
    "extract_text_from_pdf",
    "extract_text_from_docx",
    "extract_text_from_text_file",
    "normalize_text",
    "count_words",
    "extract_sentences",
    # Filename cleaning
    "clean_and_rename_files",
    "preview_renames",
    "clean_filename",
    "extract_student_name",
    "fix_mojibake",
    "to_ascii",
    "to_title_case",
    "SUPPORTED_EXTENSIONS",
    # Submission discovery
    "get_submission_files",
    "get_student_name",
    "extract_tables_from_submission",
    "dataframes_to_markdown_context",
    "EXTENSION_PRIORITY",
]
