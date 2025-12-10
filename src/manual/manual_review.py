"""
Manual review module for hybrid evaluation pipeline.

This module provides functions for:
- Converting documents to PDF for manual review
- Opening PDF viewer for manual inspection
- Prompting tutor for manual scores on format-based criteria
"""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path
from typing import Any

from src.utils.logging import get_logger

logger = get_logger(__name__)


def _polish_comment(comment: str) -> str:
    """
    Polish a tutor comment using AI to fix typos and grammar.

    Args:
        comment: Raw comment from tutor input

    Returns:
        Polished comment with corrected spelling and grammar
    """
    if not comment or not comment.strip():
        return comment

    # Check for API key
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        logger.warning("ANTHROPIC_API_KEY not set, skipping comment polish")
        return comment

    try:
        from anthropic import Anthropic

        client = Anthropic(api_key=api_key)

        response = client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=256,
            temperature=0,
            messages=[
                {
                    "role": "user",
                    "content": f"""Corrige únicamente errores de ortografía y gramática en español del siguiente texto.
NO cambies el significado, NO agregues información, NO expandas el texto.
Solo corrige typos y errores gramaticales.
Si el texto está bien, devuélvelo sin cambios.
Devuelve SOLO el texto corregido, sin explicaciones.

Texto: {comment}""",
                }
            ],
        )

        polished = response.content[0].text.strip()
        if polished:
            return polished
        return comment

    except Exception as e:
        logger.warning(f"Error polishing comment: {e}")
        return comment

# Format-based criteria that require manual evaluation
# These criteria cannot be properly evaluated through text extraction alone
# Note: "Portada" is auto-scored with full points (see AUTO_FULL_SCORE_CRITERIA)
FORMAT_CRITERIA = [
    "Formato, ortografía y gramática",
    "Referencias",
]

# Criteria that automatically receive full score (no manual prompt needed)
AUTO_FULL_SCORE_CRITERIA = [
    "Portada",
]


def get_format_criteria() -> list[str]:
    """
    Returns the list of format-based criteria that require manual evaluation.

    Returns:
        List of criterion names that should be manually scored
    """
    return FORMAT_CRITERIA.copy()


def get_auto_full_score_criteria() -> list[str]:
    """
    Returns the list of criteria that automatically receive full score.

    Returns:
        List of criterion names that get auto-scored with max points
    """
    return AUTO_FULL_SCORE_CRITERIA.copy()


def generate_auto_scores(
    rubric: dict[str, Any],
    auto_criteria: list[str] | None = None,
) -> dict[str, Any]:
    """
    Generate automatic full scores for specified criteria.

    Args:
        rubric: The rubric dictionary containing criteria definitions
        auto_criteria: List of criterion names to auto-score.
                      If None, uses AUTO_FULL_SCORE_CRITERIA.

    Returns:
        Dictionary with:
        - scores: {criterio: max_score}
        - comments: {criterio: "Cumple"}
    """
    if auto_criteria is None:
        auto_criteria = AUTO_FULL_SCORE_CRITERIA

    # Get criteria details from rubric
    criteria_map = {}
    for criterio in rubric.get("criterios", []):
        criteria_map[criterio.get("nombre", "")] = criterio

    scores = {}
    comments = {}

    for criterio_name in auto_criteria:
        criterio = criteria_map.get(criterio_name)
        if criterio:
            max_score = criterio.get("maximo", 5)
            scores[criterio_name] = max_score
            comments[criterio_name] = "Cumple"

    return {
        "scores": scores,
        "comments": comments,
    }


def convert_to_pdf(input_file: Path) -> Path:
    """
    Convert a document to PDF format for manual review.

    Uses LibreOffice in headless mode to convert DOCX/DOC files to PDF.
    If the file is already a PDF, returns the original path.

    Args:
        input_file: Path to the document to convert (DOCX, DOC, or PDF)

    Returns:
        Path to the PDF file (either converted or original)

    Raises:
        FileNotFoundError: If input file doesn't exist
        RuntimeError: If conversion fails
    """
    input_file = Path(input_file).resolve()

    if not input_file.exists():
        raise FileNotFoundError(f"Input file not found: {input_file}")

    # If already PDF, return original
    if input_file.suffix.lower() == ".pdf":
        logger.debug(f"File is already PDF: {input_file}")
        return input_file

    # Output directory is same as input file
    output_dir = input_file.parent

    logger.info(f"Converting to PDF: {input_file.name}")

    # Try LibreOffice first
    try:
        result = subprocess.run(
            [
                "libreoffice",
                "--headless",
                "--convert-to", "pdf",
                "--outdir", str(output_dir),
                str(input_file),
            ],
            capture_output=True,
            text=True,
            timeout=120,  # 2 minute timeout
        )

        if result.returncode == 0:
            pdf_path = output_dir / f"{input_file.stem}.pdf"
            if pdf_path.exists():
                logger.info(f"Converted successfully: {pdf_path.name}")
                return pdf_path
            else:
                logger.warning("LibreOffice reported success but PDF not found")
        else:
            logger.warning(f"LibreOffice conversion failed: {result.stderr}")

    except FileNotFoundError:
        logger.warning("LibreOffice not found, trying unoconv...")
    except subprocess.TimeoutExpired:
        logger.warning("LibreOffice conversion timed out")
    except Exception as e:
        logger.warning(f"LibreOffice conversion error: {e}")

    # Try unoconv as fallback
    try:
        result = subprocess.run(
            [
                "unoconv",
                "-f", "pdf",
                "-o", str(output_dir),
                str(input_file),
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )

        if result.returncode == 0:
            pdf_path = output_dir / f"{input_file.stem}.pdf"
            if pdf_path.exists():
                logger.info(f"Converted with unoconv: {pdf_path.name}")
                return pdf_path

    except FileNotFoundError:
        logger.warning("unoconv not found")
    except subprocess.TimeoutExpired:
        logger.warning("unoconv conversion timed out")
    except Exception as e:
        logger.warning(f"unoconv conversion error: {e}")

    raise RuntimeError(
        f"Could not convert {input_file.name} to PDF. "
        "Ensure LibreOffice or unoconv is installed."
    )


def open_pdf_viewer(pdf_path: Path, wait: bool = True) -> subprocess.Popen | None:
    """
    Open a PDF file in evince viewer for manual inspection.

    Args:
        pdf_path: Path to the PDF file to open
        wait: If True, waits for the viewer to close before returning

    Returns:
        The Popen process if wait=False, None if wait=True

    Raises:
        FileNotFoundError: If PDF file doesn't exist
        RuntimeError: If evince cannot be launched
    """
    pdf_path = Path(pdf_path).resolve()

    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    logger.info(f"Opening PDF viewer: {pdf_path.name}")

    # List of PDF viewers to try (in order of preference)
    viewers = ["evince", "okular", "xdg-open", "gnome-open"]

    for viewer in viewers:
        try:
            process = subprocess.Popen(
                [viewer, str(pdf_path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            logger.debug(f"Launched {viewer} (PID: {process.pid})")

            if wait:
                # Wait for viewer to close with periodic polling
                logger.info("Waiting for PDF viewer to close...")
                while process.poll() is None:
                    time.sleep(0.5)
                logger.info("PDF viewer closed")
                return None
            else:
                return process

        except FileNotFoundError:
            logger.debug(f"{viewer} not found, trying next...")
            continue
        except Exception as e:
            logger.warning(f"Error launching {viewer}: {e}")
            continue

    raise RuntimeError(
        "Could not open PDF viewer. "
        "Ensure evince, okular, or another PDF viewer is installed."
    )


def prompt_manual_scores(
    rubric: dict[str, Any],
    format_criteria: list[str] | None = None,
) -> dict[str, Any]:
    """
    Prompt the tutor for manual scores on format-based criteria.

    Displays each format-based criterion with its scoring levels and
    asks the tutor to enter a score and optional comment.

    Args:
        rubric: The rubric dictionary containing criteria definitions
        format_criteria: List of criterion names to prompt for.
                        If None, uses the default FORMAT_CRITERIA.

    Returns:
        Dictionary with:
        - scores: {criterio: score}
        - comments: {criterio: comment}
    """
    if format_criteria is None:
        format_criteria = FORMAT_CRITERIA

    # Get criteria details from rubric
    criteria_map = {}
    for criterio in rubric.get("criterios", []):
        criteria_map[criterio.get("nombre", "")] = criterio

    scores = {}
    comments = {}

    print("\n" + "=" * 60)
    print("EVALUACIÓN MANUAL DE CRITERIOS DE FORMATO")
    print("=" * 60)

    for criterio_name in format_criteria:
        criterio = criteria_map.get(criterio_name)

        if not criterio:
            logger.warning(f"Criterion '{criterio_name}' not found in rubric")
            continue

        maximo = criterio.get("maximo", 0)
        niveles = criterio.get("niveles", [])

        print(f"\n{'-' * 60}")
        print(f"CRITERIO: {criterio_name}")
        print(f"Puntaje máximo: {maximo}")
        print(f"{'-' * 60}")

        # Show scoring levels
        print("Niveles de desempeño:")
        for nivel in niveles:
            score = nivel.get("score", 0)
            descripcion = nivel.get("descripcion", "")
            print(f"  [{score}] {descripcion}")

        # Get score from tutor
        while True:
            try:
                score_input = input(f"\nIngrese puntaje para '{criterio_name}' (0-{maximo}): ").strip()
                score = int(score_input) if score_input else 0

                if 0 <= score <= maximo:
                    scores[criterio_name] = score
                    break
                else:
                    print(f"  ⚠ El puntaje debe estar entre 0 y {maximo}")
            except ValueError:
                print("  ⚠ Ingrese un número válido")
            except EOFError:
                # Handle Ctrl+D gracefully
                print("\n  ⚠ Entrada cancelada, usando puntaje 0")
                scores[criterio_name] = 0
                break

        # Get optional comment
        try:
            comment = input(f"Comentario del tutor (opcional, Enter para omitir): ").strip()
            if comment:
                # Polish the comment to fix typos/grammar
                polished = _polish_comment(comment)
                if polished != comment:
                    print(f"   → {polished}")
                comments[criterio_name] = polished
        except EOFError:
            pass

    print("\n" + "=" * 60)
    print("Resumen de evaluación manual:")
    for criterio_name, score in scores.items():
        comment = comments.get(criterio_name, "")
        comment_str = f" - {comment}" if comment else ""
        print(f"  • {criterio_name}: {score}{comment_str}")
    print("=" * 60)

    return {
        "scores": scores,
        "comments": comments,
    }


def merge_manual_scores(
    ai_puntajes: list[dict[str, Any]],
    manual_result: dict[str, Any],
    rubric: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """
    Merge manual scores into the AI-generated puntajes list.

    Manual scores replace AI scores for the same criteria.
    Manual scores for criteria not in AI puntajes are added.
    This ensures format-based criteria are evaluated by human judgment.

    Args:
        ai_puntajes: List of AI-generated score dictionaries
        manual_result: Result from prompt_manual_scores()
        rubric: Optional rubric dict to get max scores for added criteria

    Returns:
        Updated puntajes list with manual scores merged in
    """
    manual_scores = manual_result.get("scores", {})
    manual_comments = manual_result.get("comments", {})

    # Build rubric lookup for max scores
    rubric_criteria = {}
    if rubric:
        for criterio in rubric.get("criterios", []):
            rubric_criteria[criterio.get("nombre", "")] = criterio

    # Track which manual scores have been merged
    merged_manual = set()

    # Create a copy to avoid modifying original
    merged = []

    for puntaje in ai_puntajes:
        criterio = puntaje.get("criterio", "")

        if criterio in manual_scores:
            # Replace AI score with manual score
            merged.append({
                "criterio": criterio,
                "puntaje": manual_scores[criterio],
                "maximo": puntaje.get("maximo", 0),
                "justificacion": manual_comments.get(criterio, "Cumple"),
                "manual": True,  # Flag to indicate manual evaluation
            })
            merged_manual.add(criterio)
        else:
            # Keep AI score
            merged.append(puntaje.copy())

    # Add manual scores that weren't in AI puntajes
    for criterio, score in manual_scores.items():
        if criterio not in merged_manual:
            # Get max score from rubric if available
            maximo = 5  # default
            if criterio in rubric_criteria:
                maximo = rubric_criteria[criterio].get("maximo", 5)

            merged.append({
                "criterio": criterio,
                "puntaje": score,
                "maximo": maximo,
                "justificacion": manual_comments.get(criterio, "Cumple"),
                "manual": True,
            })

    return merged


def calculate_final_total(puntajes: list[dict[str, Any]]) -> dict[str, int | float]:
    """
    Calculate final totals from puntajes list.

    Args:
        puntajes: List of score dictionaries

    Returns:
        Dictionary with total_obtenido and total_maximo
    """
    total_obtenido = sum(p.get("puntaje", 0) for p in puntajes)
    total_maximo = sum(p.get("maximo", 0) for p in puntajes)

    return {
        "total_obtenido": total_obtenido,
        "total_maximo": total_maximo,
    }
