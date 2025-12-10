#!/usr/bin/env python3
"""
PDF generation module for teacher-automation.

Generates PDF feedback documents from JSON feedback files.
Uses reportlab for PDF generation.

Usage as module:
    python -m src.output.pdf_generator --input-dir <dir> --output-dir <dir>

Usage from code:
    from src.output.pdf_generator import generate_pdf_from_feedback
    generate_pdf_from_feedback(json_path, output_path)
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import (
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )
except ImportError:
    print("Error: reportlab is required. Install with: pip install reportlab")
    sys.exit(1)

from src.utils.logging import get_logger

logger = get_logger(__name__)


def _get_styles() -> dict[str, ParagraphStyle]:
    """Get custom paragraph styles for the PDF."""
    styles = getSampleStyleSheet()

    custom_styles = {
        "Title": ParagraphStyle(
            "CustomTitle",
            parent=styles["Heading1"],
            fontSize=16,
            spaceAfter=12,
            textColor=colors.HexColor("#1a365d"),
        ),
        "Heading2": ParagraphStyle(
            "CustomHeading2",
            parent=styles["Heading2"],
            fontSize=13,
            spaceBefore=12,
            spaceAfter=6,
            textColor=colors.HexColor("#2c5282"),
        ),
        "Heading3": ParagraphStyle(
            "CustomHeading3",
            parent=styles["Heading3"],
            fontSize=11,
            spaceBefore=8,
            spaceAfter=4,
            textColor=colors.HexColor("#2b6cb0"),
        ),
        "Normal": ParagraphStyle(
            "CustomNormal",
            parent=styles["Normal"],
            fontSize=10,
            leading=14,
            spaceAfter=6,
        ),
        "Small": ParagraphStyle(
            "CustomSmall",
            parent=styles["Normal"],
            fontSize=8,
            leading=10,
            textColor=colors.HexColor("#4a5568"),
        ),
        "Narrative": ParagraphStyle(
            "Narrative",
            parent=styles["Normal"],
            fontSize=10,
            leading=14,
            spaceAfter=6,
            leftIndent=10,
            rightIndent=10,
            textColor=colors.HexColor("#2d3748"),
        ),
    }

    return custom_styles


def _extract_feedback_data(json_data: dict[str, Any]) -> dict[str, Any]:
    """
    Extract feedback data from JSON, handling nested structures.

    Args:
        json_data: Raw JSON data from feedback file

    Returns:
        Dictionary with normalized feedback data
    """
    metadata = json_data.get("metadata", {})
    retro = json_data.get("retroalimentacion", {})

    # Handle nested structure where retroalimentacion contains another retroalimentacion
    if "retroalimentacion" in retro:
        actual_feedback = retro["retroalimentacion"]
        # Use nested metadata if available
        if "metadata" in retro:
            metadata = retro["metadata"]
    else:
        actual_feedback = retro

    return {
        "metadata": metadata,
        "puntajes": actual_feedback.get("puntajes", []),
        "comentario_narrativo": actual_feedback.get("comentario_narrativo", ""),
    }


def _format_student_name(estudiante: str) -> str:
    """
    Format student name for display, extracting first name and last name.

    Handles formats like:
    - "ROSLADY KATHERIN QUESADA DIAZ" -> "Roslady Quesada"
    - "Navarrete_adriana_u1a3_muestra" -> "Adriana Navarrete"
    - "VLADIMIR ARIAS RAMIREZ" -> "Vladimir Arias"

    Args:
        estudiante: Student identifier (from metadata or filename)

    Returns:
        Properly capitalized "FirstName LastName"
    """
    # Handle underscore-separated names (from filenames)
    if "_" in estudiante:
        parts = estudiante.split("_")
        if len(parts) >= 2:
            # Typically: apellido_nombre_...
            last_name = parts[0].strip().title()
            first_name = parts[1].strip().title()
            return f"{first_name} {last_name}"
        return estudiante.title()

    # Handle space-separated names (full names like "ROSLADY KATHERIN QUESADA DIAZ")
    parts = estudiante.strip().split()
    if len(parts) >= 3:
        # Assume: FIRST [MIDDLE] LAST [LAST2] - take first name and first last name
        # For "ROSLADY KATHERIN QUESADA DIAZ" -> "Roslady Quesada"
        first_name = parts[0].title()
        # Find the last name (typically after middle names, around position 2+)
        if len(parts) == 4:
            last_name = parts[2].title()  # FIRST MIDDLE LAST LAST2
        elif len(parts) == 3:
            last_name = parts[2].title()  # FIRST MIDDLE LAST or FIRST LAST LAST2
        else:
            last_name = parts[-2].title()  # Take second to last
        return f"{first_name} {last_name}"
    elif len(parts) == 2:
        return f"{parts[0].title()} {parts[1].title()}"

    return estudiante.title()


def _build_metadata_section(
    metadata: dict[str, Any], styles: dict[str, ParagraphStyle]
) -> list:
    """Build the metadata section of the PDF."""
    elements = []

    # Title - use formatted name (FirstName LastName)
    estudiante = metadata.get("estudiante", "Estudiante")
    formatted_name = _format_student_name(estudiante)
    elements.append(Paragraph(f"Retroalimentación: {formatted_name}", styles["Title"]))
    elements.append(Spacer(1, 0.2 * inch))

    return elements


def _build_scores_section(
    puntajes: list[dict[str, Any]], styles: dict[str, ParagraphStyle]
) -> list:
    """Build the scores section of the PDF."""
    elements = []

    elements.append(Paragraph("Evaluación por Criterios", styles["Heading2"]))

    if not puntajes:
        elements.append(Paragraph("No hay puntajes disponibles.", styles["Normal"]))
        return elements

    # Calculate total score
    total_obtenido = sum(p.get("puntaje", 0) for p in puntajes)
    total_maximo = sum(p.get("maximo", 0) for p in puntajes)

    # Build scores table
    table_data = [
        [
            Paragraph("<b>Criterio</b>", styles["Small"]),
            Paragraph("<b>Puntaje</b>", styles["Small"]),
            Paragraph("<b>Justificación</b>", styles["Small"]),
        ]
    ]

    for puntaje in puntajes:
        criterio = puntaje.get("criterio", "N/A")
        score = puntaje.get("puntaje", 0)
        maximo = puntaje.get("maximo", 0)
        justificacion = puntaje.get("justificacion", "")

        table_data.append([
            Paragraph(criterio, styles["Small"]),
            Paragraph(f"{score}/{maximo}", styles["Small"]),
            Paragraph(justificacion, styles["Small"]),
        ])

    # Add total row
    table_data.append([
        Paragraph("<b>TOTAL</b>", styles["Small"]),
        Paragraph(f"<b>{total_obtenido}/{total_maximo}</b>", styles["Small"]),
        Paragraph("", styles["Small"]),
    ])

    table = Table(table_data, colWidths=[1.8 * inch, 0.8 * inch, 4 * inch])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e2e8f0")),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#edf2f7")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#1a365d")),
        ("ALIGN", (1, 0), (1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e0")),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))

    elements.append(table)
    elements.append(Spacer(1, 0.2 * inch))

    return elements


def _build_narrative_section(
    comentario: str, styles: dict[str, ParagraphStyle]
) -> list:
    """Build the narrative feedback section of the PDF."""
    elements = []

    # No header - flows naturally after the scores table

    if not comentario:
        return elements

    # Split into paragraphs and format
    paragraphs = comentario.strip().split("\n\n")
    for para in paragraphs:
        para = para.strip()
        if para:
            # Replace single newlines with spaces
            para = para.replace("\n", " ")
            elements.append(Paragraph(para, styles["Narrative"]))
            elements.append(Spacer(1, 0.05 * inch))

    elements.append(Spacer(1, 0.1 * inch))

    return elements


def _build_moodle_summary_section(
    resumen: str, styles: dict[str, ParagraphStyle]
) -> list:
    """Build the Moodle summary section of the PDF."""
    elements = []

    elements.append(Paragraph("Resumen para Moodle", styles["Heading2"]))

    if not resumen:
        elements.append(
            Paragraph("No hay resumen disponible.", styles["Normal"])
        )
        return elements

    # Add a box around the summary
    summary_text = resumen.strip().replace("\n", " ")
    elements.append(Paragraph(summary_text, styles["Normal"]))

    return elements


def _remove_score_from_resumen(resumen: str) -> str:
    """
    Remove score/grade information from the resumen text.

    Removes patterns like:
    - "Puntaje total: 71/100"
    - "Puntaje: 85/100"
    - "Calificación: 90/100"
    """
    import re

    # Remove score patterns at the end of the text
    patterns = [
        r"\s*Puntaje\s+total[:\s]+\d+/\d+\.?\s*$",
        r"\s*Puntaje[:\s]+\d+/\d+\.?\s*$",
        r"\s*Calificación[:\s]+\d+/\d+\.?\s*$",
        r"\s*Total[:\s]+\d+/\d+\.?\s*$",
    ]

    result = resumen
    for pattern in patterns:
        result = re.sub(pattern, "", result, flags=re.IGNORECASE)

    return result.strip()


def _build_scores_section_no_total(
    puntajes: list[dict[str, Any]], styles: dict[str, ParagraphStyle]
) -> list:
    """Build the scores section of the PDF WITHOUT total row."""
    elements = []

    if not puntajes:
        return elements

    # Build scores table (no header title, no total)
    table_data = [
        [
            Paragraph("<b>Criterio</b>", styles["Small"]),
            Paragraph("<b>Puntaje</b>", styles["Small"]),
            Paragraph("<b>Justificación</b>", styles["Small"]),
        ]
    ]

    for puntaje in puntajes:
        criterio = puntaje.get("criterio", "N/A")
        score = puntaje.get("puntaje", 0)
        maximo = puntaje.get("maximo", 0)
        justificacion = puntaje.get("justificacion", "")

        table_data.append([
            Paragraph(criterio, styles["Small"]),
            Paragraph(f"{score}/{maximo}", styles["Small"]),
            Paragraph(justificacion, styles["Small"]),
        ])

    table = Table(table_data, colWidths=[1.8 * inch, 0.8 * inch, 4 * inch])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e2e8f0")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#1a365d")),
        ("ALIGN", (1, 0), (1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e0")),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))

    elements.append(table)
    elements.append(Spacer(1, 0.2 * inch))

    return elements


def _build_hybrid_scores_section(
    puntajes: list[dict[str, Any]],
    styles: dict[str, ParagraphStyle],
    final_total: int | float | None = None,
    final_maximo: int | float | None = None,
) -> list:
    """
    Build the scores section for hybrid feedback PDFs.

    Shows the final total with all criteria scores.
    """
    elements = []

    # No header - table is self-explanatory

    if not puntajes:
        elements.append(Paragraph("No hay puntajes disponibles.", styles["Normal"]))
        return elements

    # Calculate totals if not provided
    if final_total is None:
        final_total = sum(p.get("puntaje", 0) for p in puntajes)
    if final_maximo is None:
        final_maximo = sum(p.get("maximo", 0) for p in puntajes)

    # Build scores table (no Tipo column)
    table_data = [
        [
            Paragraph("<b>Criterio</b>", styles["Small"]),
            Paragraph("<b>Puntaje</b>", styles["Small"]),
            Paragraph("<b>Justificación</b>", styles["Small"]),
        ]
    ]

    for puntaje in puntajes:
        criterio = puntaje.get("criterio", "N/A")
        score = puntaje.get("puntaje", 0)
        maximo = puntaje.get("maximo", 0)
        justificacion = puntaje.get("justificacion", "")

        table_data.append([
            Paragraph(criterio, styles["Small"]),
            Paragraph(f"{score}/{maximo}", styles["Small"]),
            Paragraph(justificacion, styles["Small"]),
        ])

    # Add total row
    table_data.append([
        Paragraph("<b>TOTAL</b>", styles["Small"]),
        Paragraph(f"<b>{final_total}/{final_maximo}</b>", styles["Small"]),
        Paragraph("", styles["Small"]),
    ])

    table = Table(table_data, colWidths=[1.8 * inch, 0.8 * inch, 4 * inch])

    # Base styles
    table_style = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e2e8f0")),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#edf2f7")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#1a365d")),
        ("ALIGN", (1, 0), (1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e0")),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]

    table.setStyle(TableStyle(table_style))

    elements.append(table)
    elements.append(Spacer(1, 0.2 * inch))

    return elements


def _build_tutor_comments_section(
    manual_comments: dict[str, str],
    styles: dict[str, ParagraphStyle],
) -> list:
    """Build section for tutor's manual comments."""
    elements = []

    if not manual_comments:
        return elements

    elements.append(Paragraph("Comentarios del Tutor (Formato)", styles["Heading2"]))

    for criterio, comment in manual_comments.items():
        if comment:
            elements.append(
                Paragraph(f"<b>{criterio}:</b> {comment}", styles["Normal"])
            )
            elements.append(Spacer(1, 0.05 * inch))

    elements.append(Spacer(1, 0.1 * inch))

    return elements


def _extract_hybrid_feedback_data(json_data: dict[str, Any]) -> dict[str, Any]:
    """
    Extract feedback data from hybrid JSON, including manual scores.

    Args:
        json_data: Raw JSON data from feedback file

    Returns:
        Dictionary with normalized feedback data including hybrid fields
    """
    metadata = json_data.get("metadata", {})
    retro = json_data.get("retroalimentacion", {})

    # Handle nested structure
    if "retroalimentacion" in retro:
        actual_feedback = retro["retroalimentacion"]
        if "metadata" in retro:
            metadata = retro["metadata"]
    else:
        actual_feedback = retro

    return {
        "metadata": metadata,
        "puntajes": actual_feedback.get("puntajes", []),
        "comentario_narrativo": actual_feedback.get("comentario_narrativo", ""),
        # Hybrid-specific fields
        "manual_scores": json_data.get("manual_scores", {}),
        "manual_comments": json_data.get("manual_comments", {}),
        "final_total": json_data.get("final_total"),
        "final_maximo": json_data.get("final_maximo"),
    }


def generate_hybrid_pdf_from_feedback(
    json_path: Path,
    output_path: Path | None = None,
) -> Path:
    """
    Generate a full PDF feedback document from hybrid JSON feedback.

    The PDF contains:
    - Header with course, unit, activity info
    - Full rubric table (auto + manual scores with visual distinction)
    - Narrative feedback
    - Tutor manual comments

    Args:
        json_path: Path to the JSON feedback file
        output_path: Path for the output PDF. If None, uses same directory as JSON.

    Returns:
        Path to the generated PDF file
    """
    logger.info(f"Generating hybrid PDF from: {json_path}")

    # Load JSON
    with json_path.open("r", encoding="utf-8") as f:
        json_data = json.load(f)

    # Check if this is hybrid feedback
    is_hybrid = "manual_scores" in json_data or "final_total" in json_data

    if is_hybrid:
        feedback = _extract_hybrid_feedback_data(json_data)
    else:
        feedback = _extract_feedback_data(json_data)

    # Determine output path
    if output_path is None:
        output_path = json_path.with_suffix(".pdf")

    # Ensure output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Get styles
    styles = _get_styles()

    # Build document elements
    elements = []

    # 1. Header/Metadata section
    elements.extend(_build_metadata_section(feedback["metadata"], styles))

    # 2. Scores table
    if is_hybrid:
        elements.extend(_build_hybrid_scores_section(
            feedback["puntajes"],
            styles,
            final_total=feedback.get("final_total"),
            final_maximo=feedback.get("final_maximo"),
        ))
    else:
        elements.extend(_build_scores_section(feedback["puntajes"], styles))

    # 3. Narrative feedback
    elements.extend(_build_narrative_section(
        feedback.get("comentario_narrativo", ""),
        styles
    ))

    # Create PDF
    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=letter,
        rightMargin=0.75 * inch,
        leftMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
    )

    doc.build(elements)

    logger.info(f"Hybrid PDF generated: {output_path}")
    return output_path


def generate_pdf_from_feedback(
    json_path: Path,
    output_path: Path | None = None,
) -> Path:
    """
    Generate a PDF feedback document from a JSON feedback file.

    The PDF contains:
    - Rubric scores table (without total)
    - Resumen content (without header, without final grade)

    Args:
        json_path: Path to the JSON feedback file
        output_path: Path for the output PDF. If None, uses same directory as JSON.

    Returns:
        Path to the generated PDF file

    Raises:
        FileNotFoundError: If JSON file doesn't exist
        json.JSONDecodeError: If JSON is invalid
        Exception: If PDF generation fails
    """
    logger.info(f"Generating PDF from: {json_path}")

    # Load JSON
    with json_path.open("r", encoding="utf-8") as f:
        json_data = json.load(f)

    # Extract feedback data
    feedback = _extract_feedback_data(json_data)

    # Determine output path
    if output_path is None:
        output_path = json_path.with_suffix(".pdf")

    # Ensure output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Get styles
    styles = _get_styles()

    # Build document elements
    elements = []

    # 1. Rubric scores table (without total)
    elements.extend(_build_scores_section_no_total(feedback["puntajes"], styles))

    # Create PDF
    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=letter,
        rightMargin=0.75 * inch,
        leftMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
    )

    doc.build(elements)

    logger.info(f"PDF generated: {output_path}")
    return output_path


def generate_pdfs_from_directory(
    input_dir: Path,
    output_dir: Path | None = None,
    recursive: bool = True,
) -> list[dict[str, Any]]:
    """
    Generate PDFs for all JSON feedback files in a directory.

    Args:
        input_dir: Directory containing JSON feedback files
        output_dir: Directory for output PDFs. If None, PDFs go next to JSONs.
        recursive: Whether to search subdirectories

    Returns:
        List of result dictionaries with:
        - input: Path to input JSON
        - output: Path to output PDF (if successful)
        - success: Whether generation succeeded
        - error: Error message (if failed)
    """
    logger.info(f"Processing directory: {input_dir}")

    # Find JSON files
    if recursive:
        json_files = list(input_dir.rglob("*.json"))
    else:
        json_files = list(input_dir.glob("*.json"))

    # Exclude summary/metadata files
    json_files = [f for f in json_files if not f.name.startswith("_")]

    logger.info(f"Found {len(json_files)} JSON files")

    results = []

    for json_path in json_files:
        result = {
            "input": str(json_path),
            "success": False,
        }

        try:
            # Determine output path
            if output_dir:
                # Preserve relative structure
                rel_path = json_path.relative_to(input_dir)
                pdf_path = output_dir / rel_path.with_suffix(".pdf")
            else:
                pdf_path = json_path.with_suffix(".pdf")

            # Generate PDF (use hybrid function which handles both formats)
            output_path = generate_hybrid_pdf_from_feedback(json_path, pdf_path)

            result["output"] = str(output_path)
            result["success"] = True

        except Exception as e:
            logger.error(f"Error processing {json_path}: {e}")
            result["error"] = str(e)

        results.append(result)

    successful = sum(1 for r in results if r["success"])
    logger.info(f"Generated {successful}/{len(results)} PDFs")

    return results


def main():
    """CLI entry point for PDF generation."""
    parser = argparse.ArgumentParser(
        description="Generate PDF feedback documents from JSON files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--input-dir",
        required=True,
        help="Directory containing JSON feedback files",
    )
    parser.add_argument(
        "--output-dir",
        required=False,
        help="Directory for output PDFs (default: same as input)",
    )
    parser.add_argument(
        "--no-recursive",
        action="store_true",
        help="Don't search subdirectories",
    )

    args = parser.parse_args()

    input_dir = Path(args.input_dir).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve() if args.output_dir else None

    if not input_dir.exists():
        print(f"Error: Input directory not found: {input_dir}", file=sys.stderr)
        sys.exit(1)

    print(f"Input directory: {input_dir}")
    if output_dir:
        print(f"Output directory: {output_dir}")

    results = generate_pdfs_from_directory(
        input_dir=input_dir,
        output_dir=output_dir,
        recursive=not args.no_recursive,
    )

    # Print summary
    successful = sum(1 for r in results if r["success"])
    failed = len(results) - successful

    print(f"\nProcessed {len(results)} files:")
    print(f"  Successful: {successful}")
    print(f"  Failed: {failed}")

    if failed > 0:
        print("\nFailed files:")
        for r in results:
            if not r["success"]:
                print(f"  - {r['input']}: {r.get('error', 'Unknown error')}")

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
