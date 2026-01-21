#!/usr/bin/env python3
"""
Interactive presentation grading module.

Provides terminal-based interface for grading presentations with:
- PDF viewing (detached)
- Rubric-guided scoring
- Optional comments per criterion
- LLM-generated narrative feedback
- Resume capability
- Edit/preview workflow
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from src.llm.client import LLMClient, extract_json_from_response
from src.utils.logging import get_logger

logger = get_logger(__name__)


def load_rubric(rubric_path: Path) -> dict[str, Any]:
    """Load rubric from JSON file."""
    with rubric_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_prompt(prompt_path: Path) -> str:
    """Load prompt template from file."""
    return prompt_path.read_text(encoding="utf-8")


def load_progress(progress_path: Path) -> dict[str, Any]:
    """Load grading progress from file."""
    if not progress_path.exists():
        return {"completed": [], "scores": {}}

    with progress_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_progress(progress_path: Path, progress: dict[str, Any]) -> None:
    """Save grading progress to file."""
    progress_path.parent.mkdir(parents=True, exist_ok=True)
    with progress_path.open("w", encoding="utf-8") as f:
        json.dump(progress, f, ensure_ascii=False, indent=2)


def open_pdf(pdf_path: Path) -> subprocess.Popen:
    """
    Open PDF in viewer (detached, non-blocking).

    Returns the process handle but doesn't wait.
    """
    viewers = ["evince", "okular", "xdg-open"]

    for viewer in viewers:
        try:
            process = subprocess.Popen(
                [viewer, str(pdf_path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            logger.info(f"Opened {pdf_path.name} with {viewer}")
            return process
        except FileNotFoundError:
            continue

    raise RuntimeError("No PDF viewer found. Install evince or okular.")


def grade_criterion_interactive(
    criterio_name: str,
    criterio_data: dict[str, Any],
    student_num: int,
    total_students: int,
    student_name: str,
) -> tuple[int, str]:
    """
    Prompt user to grade a single criterion interactively.

    Returns:
        (score, comment)
    """
    maximo = criterio_data["maximo"]
    niveles = criterio_data["niveles"]

    print(f"\n{'=' * 70}")
    print(f"[{student_num}/{total_students}] {student_name}")
    print(f"{'=' * 70}")
    print(f"\nCRITERIO: {criterio_name} (máx: {maximo} puntos)\n")

    # Show scoring levels
    print("Niveles de desempeño:")
    for nivel in sorted(niveles, key=lambda x: x["score"], reverse=True):
        score = nivel["score"]
        desc = nivel["descripcion"][:100]
        print(f"  [{score:>3}] {desc}...")

    # Get score
    while True:
        try:
            score_input = input(f"\nPuntaje (0-{maximo}): ").strip()
            if not score_input:
                print("  ⚠ Debes ingresar un puntaje")
                continue

            score = int(score_input)
            if 0 <= score <= maximo:
                break
            else:
                print(f"  ⚠ El puntaje debe estar entre 0 y {maximo}")
        except ValueError:
            print("  ⚠ Ingrese un número válido")
        except (EOFError, KeyboardInterrupt):
            print("\n\n⚠ Grading interrupted. Progress saved.")
            raise

    # Get optional comment
    print("\nComentario opcional (Enter para omitir):")
    try:
        comment = input("  > ").strip()
    except (EOFError, KeyboardInterrupt):
        comment = ""

    return score, comment


def generate_feedback_with_llm(
    student_name: str,
    rubric: dict[str, Any],
    scores: dict[str, tuple[int, str]],
    prompt_template: str,
    presentation_text: str = "",
    provider: str = "deepseek",
    model: str | None = None,
    temperature: float = 1.0,
) -> dict[str, Any]:
    """
    Generate narrative feedback using LLM.

    Args:
        student_name: Student's full name (Firstname Lastname)
        rubric: Rubric dictionary
        scores: Dict of {criterio_name: (score, comment)}
        prompt_template: Prompt template text
        presentation_text: Extracted text from presentation PDF
        provider: LLM provider ("anthropic" or "deepseek")
        model: Model name (provider-specific, optional)
        temperature: Temperature for generation (default: 1.0)

    Returns:
        Dictionary with puntajes and comentario_narrativo
    """
    llm = LLMClient(provider=provider, model=model, temperature=temperature)

    # Build context for LLM
    context_parts = [
        f"NOMBRE DEL ESTUDIANTE: {student_name}",
        "(Usa solo el primer nombre al dirigirte al estudiante.)",
        "",
    ]

    # Add presentation content if available
    if presentation_text and len(presentation_text.strip()) > 50:
        # Limit to first 3000 chars to avoid token limits
        text_preview = presentation_text[:3000]
        context_parts.append("CONTENIDO DE LA PRESENTACIÓN:")
        context_parts.append("```")
        context_parts.append(text_preview)
        context_parts.append("```")
        context_parts.append("")

    context_parts.append("PUNTAJES ASIGNADOS POR EL TUTOR:")
    context_parts.append("")

    for criterio_name, (score, comment) in scores.items():
        # Find criterion in rubric
        criterio_data = next(
            (c for c in rubric["criterios"] if c["nombre"] == criterio_name),
            {}
        )
        maximo = criterio_data.get("maximo", 0)

        context_parts.append(f"  - {criterio_name}: {score}/{maximo}")
        if comment:
            context_parts.append(f"    Tu observación: {comment}")

    context_parts.append("")
    context_parts.append("IMPORTANTE: Genera retroalimentación en 3 párrafos (apertura positiva, desarrollo, cierre motivador).")
    if presentation_text and len(presentation_text.strip()) > 50:
        context_parts.append("Usa el contenido de la presentación para hacer la retroalimentación más específica y personalizada.")

    context = "\n".join(context_parts)

    # Call LLM
    raw_response = llm.generate_feedback(
        system_prompt=prompt_template,
        user_message=context,
        rubric=rubric,
        max_tokens=2000
    )

    # Extract JSON from response
    feedback = extract_json_from_response(raw_response)

    return feedback


def validate_narrative(narrative: str, student_name: str) -> list[str]:
    """
    Validate narrative feedback.

    Returns list of warnings (empty if all valid).
    """
    warnings = []

    # Check uses first name
    first_name = student_name.split()[0]
    if first_name not in narrative[:100]:
        warnings.append(f"⚠ No usa el primer nombre '{first_name}' al inicio")

    # Check has 3+ paragraphs
    paragraphs = [p.strip() for p in narrative.split("\n\n") if p.strip()]
    if len(paragraphs) < 3:
        warnings.append(f"⚠ Solo tiene {len(paragraphs)} párrafos (se esperan 3)")

    # Check minimum length
    if len(narrative) < 300:
        warnings.append(f"⚠ Muy corto ({len(narrative)} caracteres, mínimo 300)")

    return warnings


def preview_and_edit_feedback(
    feedback: dict[str, Any],
    student_name: str
) -> dict[str, Any]:
    """
    Show feedback preview and allow editing.

    Returns the (possibly edited) feedback.
    """
    narrative = feedback.get("comentario_narrativo", "")
    puntajes = feedback.get("puntajes", [])

    print("\n" + "=" * 70)
    print("PREVIEW DE RETROALIMENTACIÓN")
    print("=" * 70)

    # Show scores
    print("\nPuntajes:")
    total = sum(p.get("puntaje", 0) for p in puntajes)
    maximo = sum(p.get("maximo", 0) for p in puntajes)
    for p in puntajes:
        print(f"  {p['criterio']}: {p['puntaje']}/{p['maximo']}")
    print(f"\nTOTAL: {total}/{maximo}")

    # Show narrative
    print("\nComentario narrativo:")
    print("-" * 70)
    print(narrative)
    print("-" * 70)

    # Validate
    warnings = validate_narrative(narrative, student_name)
    if warnings:
        print("\n⚠ ADVERTENCIAS:")
        for w in warnings:
            print(f"  {w}")

    # Ask for acceptance
    while True:
        try:
            response = input("\n¿Aceptar? (y/n/q para salir): ").strip().lower()

            if response == 'q':
                raise KeyboardInterrupt()

            if response == 'y':
                return feedback

            if response == 'n':
                # Open in vim for editing
                with tempfile.NamedTemporaryFile(
                    mode='w',
                    suffix='.txt',
                    delete=False,
                    encoding='utf-8'
                ) as tmp:
                    tmp.write(narrative)
                    tmp_path = tmp.name

                try:
                    subprocess.run(['vim', tmp_path], check=True)

                    with open(tmp_path, 'r', encoding='utf-8') as f:
                        edited_narrative = f.read().strip()

                    feedback["comentario_narrativo"] = edited_narrative

                    # Show edited version
                    print("\nVersión editada:")
                    print("-" * 70)
                    print(edited_narrative)
                    print("-" * 70)

                    # Re-validate
                    warnings = validate_narrative(edited_narrative, student_name)
                    if warnings:
                        print("\n⚠ ADVERTENCIAS:")
                        for w in warnings:
                            print(f"  {w}")

                    # Ask again
                    continue

                finally:
                    Path(tmp_path).unlink(missing_ok=True)

            print("  ⚠ Responde 'y' (sí) o 'n' (editar) o 'q' (salir)")

        except (EOFError, KeyboardInterrupt):
            raise


def convert_pptx_to_pdf(pptx_path: Path, output_dir: Path) -> Path:
    """
    Convert PPTX to PDF using LibreOffice.

    Returns path to generated PDF.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    result = subprocess.run(
        [
            "libreoffice",
            "--headless",
            "--convert-to", "pdf",
            "--outdir", str(output_dir),
            str(pptx_path)
        ],
        capture_output=True,
        text=True,
        timeout=120
    )

    if result.returncode != 0:
        raise RuntimeError(f"LibreOffice conversion failed: {result.stderr}")

    pdf_path = output_dir / f"{pptx_path.stem}.pdf"
    if not pdf_path.exists():
        raise RuntimeError(f"PDF not created: {pdf_path}")

    return pdf_path


def batch_convert_presentations(
    presentations_dir: Path,
    pdf_output_dir: Path
) -> list[tuple[Path, Path]]:
    """
    Convert all PPTX/PPT files to PDF, skipping if PDF already exists.

    Also collects existing PDFs in the source directory.

    Returns list of (source_path, pdf_path) tuples.
    """
    pptx_files = []
    for ext in [".pptx", ".ppt", ".PPTX", ".PPT"]:
        pptx_files.extend(presentations_dir.glob(f"*{ext}"))

    # Also collect existing PDFs in source directory
    existing_pdfs = list(presentations_dir.glob("*.pdf")) + list(presentations_dir.glob("*.PDF"))

    conversions = []
    to_convert = []
    skipped = 0

    # Check which files need conversion
    for pptx_path in pptx_files:
        pdf_path = pdf_output_dir / f"{pptx_path.stem}.pdf"
        if pdf_path.exists():
            conversions.append((pptx_path, pdf_path))
            skipped += 1
        else:
            to_convert.append(pptx_path)

    # Add existing PDFs from source directory
    for pdf_path in existing_pdfs:
        conversions.append((pdf_path, pdf_path))

    if to_convert:
        print(f"\nConvirtiendo {len(to_convert)} presentaciones a PDF...")
        if skipped > 0:
            print(f"(Omitiendo {skipped} que ya tienen PDF)")

        for i, pptx_path in enumerate(to_convert, 1):
            try:
                print(f"[{i}/{len(to_convert)}] {pptx_path.name}...", end=" ")
                pdf_path = convert_pptx_to_pdf(pptx_path, pdf_output_dir)
                conversions.append((pptx_path, pdf_path))
                print("✓")
            except Exception as e:
                print(f"✗ {e}")
                logger.error(f"Failed to convert {pptx_path.name}: {e}")
    else:
        print(f"\n✓ Todas las presentaciones ya tienen PDF ({len(conversions)} archivos)")

    return conversions
