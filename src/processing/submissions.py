"""
Submission file discovery utilities.

Provides functions for finding and filtering student submission files
in a directory, with deduplication when multiple formats exist.
"""

from __future__ import annotations

import re
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


# --- Table Type Classification ---

# Pattern to detect internal title rows that split a merged Word table
_INTERNAL_TITLE_RE = re.compile(
    r"^tabla\s+(n[uú]mero|no\.?)\s*\d+",
    re.IGNORECASE,
)


def _classify_table_type(title_text: str, num_columns: int) -> str:
    """
    Classify a table as CONCEPTUAL or REFERENCIAL based on its title or structure.

    Args:
        title_text: Text from the first row/cell of the table (the title)
        num_columns: Number of unique columns in the table

    Returns:
        "CONCEPTUAL", "REFERENCIAL", or "OTRO"
    """
    title_lower = title_text.lower()

    if "conceptual" in title_lower:
        return "CONCEPTUAL"
    if "referencial" in title_lower:
        return "REFERENCIAL"

    # Structural fallback: single-column → conceptual, multi-column → referencial
    if num_columns == 1:
        return "CONCEPTUAL"
    if num_columns >= 4:
        return "REFERENCIAL"

    return "OTRO"


def _is_internal_title_row(row_cells: list[str]) -> bool:
    """
    Detect if a row is an internal title that splits a merged Word table.

    Students sometimes place multiple conceptual tables inside a single Word
    <w:tbl> element, separated by internal title rows like
    "Tabla número 2: Análisis conceptual sobre..."

    Args:
        row_cells: List of cell text values for the row

    Returns:
        True if this row is an internal title separator
    """
    # All cells must have the same text (merged row)
    unique_texts = set(cell.strip() for cell in row_cells if cell.strip())
    if len(unique_texts) != 1:
        return False

    text = unique_texts.pop()
    return bool(_INTERNAL_TITLE_RE.match(text))


def _count_unique_columns(table) -> int:
    """Count unique columns by checking cell spans in the first data row."""
    if not table.rows:
        return 0
    # python-docx may report duplicate cells for merged columns;
    # count unique cell objects in a row
    first_row = table.rows[0]
    seen = set()
    count = 0
    for cell in first_row.cells:
        cell_id = id(cell)
        if cell_id not in seen:
            seen.add(cell_id)
            count += 1
    return count


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


def _split_merged_table(table_data: list[list[str]]) -> list[tuple[str, list[list[str]]]]:
    """
    Split a single Word table that contains multiple logical tables
    separated by internal title rows.

    Args:
        table_data: 2D list of cell text values

    Returns:
        List of (title_text, rows) tuples for each logical sub-table
    """
    sub_tables: list[tuple[str, list[list[str]]]] = []
    current_title = ""
    current_rows: list[list[str]] = []

    for row in table_data:
        if _is_internal_title_row(row):
            # Save previous sub-table if it has data
            if current_rows:
                sub_tables.append((current_title, current_rows))
            # Start new sub-table with this title
            unique_texts = set(cell.strip() for cell in row if cell.strip())
            current_title = unique_texts.pop() if unique_texts else ""
            current_rows = []
        else:
            # First row of the whole table might be the title
            if not current_rows and not current_title:
                unique_texts = set(cell.strip() for cell in row if cell.strip())
                if len(unique_texts) == 1:
                    text = unique_texts.pop()
                    text_lower = text.lower()
                    if "conceptual" in text_lower or "referencial" in text_lower or _INTERNAL_TITLE_RE.match(text):
                        current_title = text
                        continue
            current_rows.append(row)

    # Don't forget the last sub-table
    if current_rows:
        sub_tables.append((current_title, current_rows))

    return sub_tables


def _extract_from_docx(file_path: Path) -> list[dict]:
    """
    Extract tables from a DOCX file using python-docx, with type classification.

    Each extracted table includes metadata about its detected type
    (CONCEPTUAL, REFERENCIAL, or OTRO).

    Args:
        file_path: Path to the DOCX file

    Returns:
        List of dicts with keys: "df" (DataFrame), "type" (str), "title" (str)
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
    results = []

    for table in doc.tables:
        table_data = _get_table_data_docx(table)
        if not table_data:
            continue

        num_columns = _count_unique_columns(table)

        # Check if this Word table contains multiple logical tables
        first_row_text = " ".join(cell.strip() for cell in table_data[0] if cell.strip())
        sub_tables = _split_merged_table(table_data)

        if len(sub_tables) > 1:
            # Merged table: process each sub-table independently
            for title, rows in sub_tables:
                if len(rows) > 1:
                    df = pd.DataFrame(rows[1:], columns=rows[0])
                elif rows:
                    df = pd.DataFrame(rows)
                else:
                    continue
                table_type = _classify_table_type(title, num_columns)
                results.append({"df": df, "type": table_type, "title": title})
        else:
            # Single logical table
            title = sub_tables[0][0] if sub_tables else ""
            rows = sub_tables[0][1] if sub_tables else table_data

            if len(rows) > 1:
                df = pd.DataFrame(rows[1:], columns=rows[0])
            elif rows:
                df = pd.DataFrame(rows)
            else:
                continue

            # If no title was extracted from splitting, use the first row text
            if not title:
                title = first_row_text
            table_type = _classify_table_type(title, num_columns)
            results.append({"df": df, "type": table_type, "title": title})

    return results


def _extract_from_pdf(file_path: Path) -> list[dict]:
    """
    Extract tables from a PDF file using tabula-py with pdfplumber fallback.

    Tries tabula-py first (better for bordered tables), then falls back to
    pdfplumber (better for some borderless/APA-style tables).

    Args:
        file_path: Path to the PDF file

    Returns:
        List of dicts with keys: "df" (DataFrame), "type" (str), "title" (str)
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

    # For PDFs we can't easily classify — try heuristic from content
    results = []
    for df in dataframes:
        # Try to classify from first cell/column header text
        first_text = ""
        if not df.empty:
            cols_text = " ".join(str(c) for c in df.columns)
            first_cell = str(df.iloc[0, 0]) if len(df.columns) > 0 else ""
            first_text = f"{cols_text} {first_cell}"

        table_type = _classify_table_type(first_text, len(df.columns))
        results.append({"df": df, "type": table_type, "title": first_text[:100]})

    return results


def extract_tables_from_submission(file_path: Path) -> list[dict]:
    """
    Extract tables from a student submission file (DOCX or PDF).

    This is the main router function that dispatches to the appropriate
    extractor based on file extension.

    Args:
        file_path: Path to the submission file (.docx or .pdf)

    Returns:
        List of dicts with keys: "df" (DataFrame), "type" (str), "title" (str).
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

_TYPE_LABELS = {
    "CONCEPTUAL": "Listado Conceptual — 7 indicadores esperados",
    "REFERENCIAL": "Listado Referencial — 11 indicadores esperados",
    "OTRO": "Tipo no identificado",
}


def dataframes_to_markdown_context(tables: list, activity_id: str) -> str:
    """
    Convert a list of extracted tables into a structured Markdown string
    for injection into the LLM prompt.

    Accepts either:
    - list[dict] with keys "df", "type", "title" (new classified format)
    - list[DataFrame] (legacy format, no classification)

    Args:
        tables: List of table dicts or DataFrames extracted from submission
        activity_id: The activity identifier (e.g., "2.1", "3.1")

    Returns:
        Formatted Markdown string with table data, or a note if no tables found
    """
    if not tables:
        return f"// No se detectaron tablas para la actividad {activity_id}."

    markdown_parts = [
        f"\n// [INICIO DE DATOS ESTRUCTURADOS DE LA TAREA {activity_id}]"
    ]

    for i, item in enumerate(tables):
        # Support both new dict format and legacy DataFrame format
        if isinstance(item, dict):
            df = item["df"]
            table_type = item.get("type", "OTRO")
            title = item.get("title", "")
        else:
            # Legacy: bare DataFrame
            df = item
            table_type = "OTRO"
            title = ""

        type_label = _TYPE_LABELS.get(table_type, table_type)

        # Use pandas .to_markdown() for clean conversion
        table_markdown = df.to_markdown(index=False)

        header = f"### Tabla {i+1}: {type_label}"
        if title:
            header += f"\nTítulo detectado: \"{title[:120]}\""

        markdown_parts.append(
            f"\n{header}\n"
            f"```markdown_table\n"
            f"{table_markdown}\n"
            f"```"
        )

    markdown_parts.append(f"\n// [FIN DE DATOS ESTRUCTURADOS DE LA TAREA {activity_id}]")

    return "\n".join(markdown_parts)
