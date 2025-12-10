"""
Submission file discovery utilities.

Provides functions for finding and filtering student submission files
in a directory, with deduplication when multiple formats exist.
"""

from pathlib import Path

from .filenames import SUPPORTED_EXTENSIONS

# Priority order: prefer PDF over DOCX over DOC
EXTENSION_PRIORITY = {".pdf": 0, ".docx": 1, ".doc": 2}


def get_submission_files(directory: Path) -> list[Path]:
    """
    Get submission files from directory, deduplicated by stem.

    If multiple files have same stem (e.g., student.pdf and student.docx),
    prefers PDF > DOCX > DOC based on EXTENSION_PRIORITY.

    Args:
        directory: Directory containing student submissions

    Returns:
        Sorted list of file paths (one per unique stem)
    """
    files = []
    for ext in SUPPORTED_EXTENSIONS:
        files.extend(directory.glob(f"*{ext}"))
        files.extend(directory.glob(f"*{ext.upper()}"))

    # Deduplicate by stem, keeping highest priority extension
    seen_stems: dict[str, tuple[Path, int]] = {}
    for f in files:
        stem = f.stem
        ext_lower = f.suffix.lower()
        priority = EXTENSION_PRIORITY.get(ext_lower, 99)
        if stem not in seen_stems or priority < seen_stems[stem][1]:
            seen_stems[stem] = (f, priority)

    return sorted([f for f, _ in seen_stems.values()])


def get_student_name(file_path: Path) -> str:
    """
    Extract student name from filename (uses stem).

    For more sophisticated name extraction from Moodle-style filenames,
    use extract_student_name from the filenames module instead.

    Args:
        file_path: Path to submission file

    Returns:
        File stem as student identifier
    """
    return file_path.stem


# --- Table Extraction Functions ---

def _get_table_data_docx(table) -> list[list[str]]:
    """
    Extract data from a python-docx Table object as a 2D list of strings.

    Args:
        table: A python-docx Table object

    Returns:
        List of rows, where each row is a list of cell text values
    """
    data = []
    for row in table.rows:
        row_data = [cell.text.strip() for cell in row.cells]
        data.append(row_data)
    return data


def _extract_from_docx(file_path: Path) -> list:
    """
    Extract tables from a DOCX file using python-docx.

    Args:
        file_path: Path to the DOCX file

    Returns:
        List of pandas DataFrames, one per table found
    """
    try:
        from docx import Document
        import pandas as pd
    except ImportError as e:
        raise ImportError(
            "Table extraction requires python-docx and pandas. "
            "Install with: pip install python-docx pandas"
        ) from e

    doc = Document(file_path)
    dataframes = []

    for table in doc.tables:
        table_data = _get_table_data_docx(table)
        if table_data and len(table_data) > 1:
            # Use first row as header
            df = pd.DataFrame(table_data[1:], columns=table_data[0])
            dataframes.append(df)
        elif table_data:
            # Single row table (no header)
            df = pd.DataFrame(table_data)
            dataframes.append(df)

    return dataframes


def _extract_from_pdf(file_path: Path) -> list:
    """
    Extract tables from a PDF file using tabula-py with pdfplumber fallback.

    Tries tabula-py first (better for bordered tables), then falls back to
    pdfplumber (better for some borderless/APA-style tables).

    Args:
        file_path: Path to the PDF file

    Returns:
        List of pandas DataFrames, one per table found
    """
    import pandas as pd

    dataframes = []

    # Try tabula-py first (good for bordered tables)
    try:
        import tabula
        dataframes = tabula.read_pdf(
            str(file_path),
            pages="all",
            multiple_tables=True,
            silent=True,
        )
        # Filter out empty DataFrames
        dataframes = [df for df in dataframes if not df.empty]
    except ImportError:
        pass  # tabula not installed, try pdfplumber
    except Exception:
        pass  # tabula failed, try pdfplumber

    # If tabula found nothing, try pdfplumber
    if not dataframes:
        try:
            import pdfplumber
            with pdfplumber.open(str(file_path)) as pdf:
                for page in pdf.pages:
                    # Try default extraction first
                    tables = page.extract_tables()

                    # If no tables found, try with lines+text strategy
                    # (better for APA-style tables with horizontal rules only)
                    if not tables:
                        tables = page.extract_tables(table_settings={
                            "vertical_strategy": "text",
                            "horizontal_strategy": "lines",
                            "snap_tolerance": 5,
                            "join_tolerance": 5,
                        })

                    for table in tables:
                        if table and len(table) > 1:
                            # Clean up empty cells and filter empty rows
                            cleaned = [
                                [cell.strip() if cell else "" for cell in row]
                                for row in table
                            ]
                            cleaned = [row for row in cleaned if any(cell for cell in row)]

                            if len(cleaned) > 1:
                                # Use first row as header
                                df = pd.DataFrame(cleaned[1:], columns=cleaned[0])
                                if not df.empty:
                                    dataframes.append(df)
                            elif cleaned:
                                df = pd.DataFrame(cleaned)
                                if not df.empty:
                                    dataframes.append(df)
        except ImportError:
            pass  # pdfplumber not installed
        except Exception:
            pass  # pdfplumber failed

    return dataframes


def extract_tables_from_submission(file_path: Path) -> list:
    """
    Extract tables from a student submission file (DOCX or PDF).

    This is the main router function that dispatches to the appropriate
    extractor based on file extension.

    Args:
        file_path: Path to the submission file (.docx or .pdf)

    Returns:
        List of pandas DataFrames, one per table found.
        Returns empty list if file type is unsupported or no tables found.
    """
    ext = file_path.suffix.lower()

    if ext == ".docx":
        return _extract_from_docx(file_path)
    elif ext == ".pdf":
        return _extract_from_pdf(file_path)
    else:
        # Unsupported file type for table extraction
        return []


# --- Table to Markdown Conversion ---

def dataframes_to_markdown_context(dataframes: list, activity_id: str) -> str:
    """
    Convert a list of extracted DataFrames into a structured Markdown string
    for injection into the LLM prompt.

    Args:
        dataframes: List of pandas DataFrames extracted from submission
        activity_id: The activity identifier (e.g., "3.1", "3.2")

    Returns:
        Formatted Markdown string with table data, or a note if no tables found
    """
    if not dataframes:
        return f"// No se detectaron tablas para la actividad {activity_id}."

    markdown_parts = [
        f"\n// [INICIO DE DATOS ESTRUCTURADOS DE LA TAREA {activity_id}]"
    ]

    for i, df in enumerate(dataframes):
        # Use pandas .to_markdown() for clean conversion
        table_markdown = df.to_markdown(index=False)

        markdown_parts.append(
            f"\n### Tabla {i+1} (Extraída del Documento de la Entrega)\n"
            f"```markdown_table\n"
            f"{table_markdown}\n"
            f"```"
        )

    markdown_parts.append(f"\n// [FIN DE DATOS ESTRUCTURADOS DE LA TAREA {activity_id}]")

    return "\n".join(markdown_parts)
