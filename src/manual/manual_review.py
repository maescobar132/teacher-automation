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
            model="claude-haiku-4-5-20251001",
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

    # Try PowerShell + Word COM on WSL2 (no extra install required)
    if _is_wsl():
        try:
            win_input = subprocess.run(
                ["wslpath", "-w", str(input_file)],
                capture_output=True, text=True, timeout=5,
            ).stdout.strip()
            win_output = subprocess.run(
                ["wslpath", "-w", str(output_dir)],
                capture_output=True, text=True, timeout=5,
            ).stdout.strip()
            pdf_win_path = win_output + "\\" + input_file.stem + ".pdf"

            ps_script = (
                "$w = New-Object -ComObject Word.Application;"
                "$w.Visible = $false;"
                f"$d = $w.Documents.Open('{win_input}');"
                f"$d.SaveAs('{pdf_win_path}', 17);"
                "$d.Close(); $w.Quit()"
            )
            result = subprocess.run(
                ["powershell.exe", "-NoProfile", "-Command", ps_script],
                capture_output=True, text=True, timeout=120,
            )
            pdf_path = output_dir / f"{input_file.stem}.pdf"
            if result.returncode == 0 and pdf_path.exists():
                logger.info(f"Converted via Word COM: {pdf_path.name}")
                return pdf_path
            else:
                logger.warning(f"Word COM conversion failed: {result.stderr.strip()}")
        except Exception as e:
            logger.warning(f"Word COM conversion error: {e}")

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


def _is_wsl() -> bool:
    """Detect if running inside Windows Subsystem for Linux."""
    try:
        with open("/proc/version") as f:
            return "microsoft" in f.read().lower()
    except OSError:
        return False


def _wsl_open(file_path: Path) -> subprocess.Popen | None:
    """
    Open a file using the Windows default application from WSL2.

    Converts the Linux path to a Windows UNC path using wslpath,
    then launches it with cmd.exe /c start.
    """
    try:
        result = subprocess.run(
            ["wslpath", "-w", str(file_path)],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0:
            logger.warning(f"wslpath failed: {result.stderr}")
            return None

        win_path = result.stdout.strip()
        logger.info(f"Opening in Windows: {win_path}")

        process = subprocess.Popen(
            ["cmd.exe", "/c", "start", "", win_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        time.sleep(1)
        return process

    except Exception as e:
        logger.warning(f"WSL open failed: {e}")
        return None


def open_document(file_path: Path, wait: bool = True) -> subprocess.Popen | None:
    """
    Open a document file (PDF, DOCX, DOC) in the default viewer.

    Detects WSL2 and uses the Windows default application via cmd.exe.
    On native Linux, tries evince, okular, then xdg-open.

    Args:
        file_path: Path to the document file to open
        wait: If True, waits for user confirmation before returning

    Returns:
        The Popen process if wait=False, None if wait=True

    Raises:
        FileNotFoundError: If file doesn't exist
        RuntimeError: If no viewer can be launched
    """
    file_path = Path(file_path).resolve()

    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    logger.info(f"Opening document: {file_path.name}")

    process = None

    if _is_wsl():
        process = _wsl_open(file_path)
        viewer_name = "Windows (cmd.exe start)"
    else:
        # Native Linux — try dedicated viewers
        if file_path.suffix.lower() == ".pdf":
            viewers = ["evince", "okular", "xdg-open"]
        else:
            viewers = ["xdg-open", "libreoffice"]

        last_error = None
        viewer_name = None

        for viewer in viewers:
            try:
                process = subprocess.Popen(
                    [viewer, str(file_path)],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                time.sleep(0.5)
                returncode = process.poll()
                if returncode is not None:
                    stderr = process.stderr.read().decode("utf-8", errors="ignore")
                    logger.debug(f"{viewer} exited with code {returncode}: {stderr}")
                    last_error = stderr
                    process = None
                    continue
                viewer_name = viewer
                break
            except FileNotFoundError:
                logger.debug(f"{viewer} not found, trying next...")
            except Exception as e:
                logger.warning(f"Error launching {viewer}: {e}")
                last_error = str(e)

        if process is None:
            error_msg = f"Could not open document viewer. Last error: {last_error}" if last_error else "No suitable document viewer found"
            raise RuntimeError(error_msg)

    logger.info(f"Launched {viewer_name} successfully")

    if wait:
        time.sleep(1)
        print(f"\n   >>> Documento abierto con {viewer_name}")
        print("   >>> Presione Enter cuando termine de revisar el documento <<<\n")
        try:
            input("   Presione Enter para continuar: ")
        except (EOFError, KeyboardInterrupt):
            print()
        return None
    else:
        return process


def open_pdf_viewer(pdf_path: Path, wait: bool = True) -> subprocess.Popen | None:
    """
    Open a PDF file in a viewer for manual inspection.

    This is a wrapper around open_document for backwards compatibility.

    Args:
        pdf_path: Path to the PDF file to open
        wait: If True, waits for user confirmation before returning

    Returns:
        The Popen process if wait=False, None if wait=True

    Raises:
        FileNotFoundError: If PDF file doesn't exist
        RuntimeError: If viewer cannot be launched
    """
    return open_document(pdf_path, wait)


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
                if not score_input:
                    print("  ⚠ Debes ingresar un puntaje")
                    continue

                score = int(score_input)
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


def prompt_citas_textuales_check() -> dict[str, Any]:
    """
    Ask the tutor if they observed direct textual quotes in the document.

    A "cita textual" is text enclosed in quotation marks copied verbatim
    from a bibliographic source (NOT parenthetical citations like (Author, 2024)).

    Returns:
        Dictionary with:
        - has_citas_textuales: bool
        - details: str (optional details if yes)
    """
    print("\n" + "-" * 60)
    print("VERIFICACIÓN DE CITAS TEXTUALES")
    print("-" * 60)
    print("Una 'cita textual' es texto ENTRE COMILLAS copiado de una fuente.")
    print("Ejemplo: \"La motivación es clave\" (García, 2023, p. 45)")
    print("NO confundir con referencias parentéticas (Autor, Año) que son correctas.")
    print("-" * 60)

    while True:
        try:
            response = input("\n¿Observaste citas textuales en el documento? (s/n): ").strip().lower()
            if response in ["s", "si", "sí", "y", "yes"]:
                details = input("Describe brevemente dónde las observaste (opcional, Enter para omitir): ").strip()
                return {
                    "has_citas_textuales": True,
                    "details": details if details else "El tutor observó citas textuales en el documento.",
                }
            elif response in ["n", "no"]:
                return {
                    "has_citas_textuales": False,
                    "details": "",
                }
            else:
                print("  ⚠ Responde 's' para sí o 'n' para no")
        except EOFError:
            print("\n  ⚠ Entrada cancelada, asumiendo que no hay citas textuales")
            return {
                "has_citas_textuales": False,
                "details": "",
            }
