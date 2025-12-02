#!/usr/bin/env python3
"""
Generate PDF feedback documents and grade summary from JSON feedback files.

This script processes all JSON feedback files in a directory and generates:
1. One PDF per student with formatted feedback
2. A resumen_calificaciones.txt with all grades

Usage:
    python run_pdf_feedback.py --json_dir outputs/FI08/unidad_1/actividad_1.1
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import re
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Generate PDF feedback documents from JSON files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python run_pdf_feedback.py --json_dir outputs/FI08/unidad_1/actividad_1.1
    python run_pdf_feedback.py --json_dir ./my_feedback_jsons
        """,
    )
    parser.add_argument(
        "--json_dir",
        type=Path,
        required=True,
        help="Directory containing JSON feedback files",
    )
    parser.add_argument(
        "--sanitize",
        action="store_true",
        help="Use sanitized student name from metadata instead of source filename",
    )
    return parser.parse_args()


def load_json_file(json_path: Path) -> dict[str, Any] | None:
    """
    Load a JSON file safely.

    Args:
        json_path: Path to JSON file

    Returns:
        Parsed JSON as dict, or None if failed
    """
    try:
        with json_path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        print(f"WARNING: JSON malformado en {json_path}: {e}")
        return None
    except Exception as e:
        print(f"WARNING: Error leyendo {json_path}: {e}")
        return None


def extract_metadata(data: dict[str, Any]) -> dict[str, Any]:
    """
    Extract metadata from a feedback JSON.

    Args:
        data: Parsed JSON data

    Returns:
        Dictionary with metadata fields
    """
    metadata = data.get("metadata", {})
    return {
        "estudiante": metadata.get("estudiante", "Desconocido"),
        "archivo_original": metadata.get("archivo_original", ""),
        "fecha_procesamiento": metadata.get("fecha_procesamiento", ""),
        "curso": metadata.get("curso", ""),
        "unidad": metadata.get("unidad", 1),
        "actividad": metadata.get("actividad", ""),
    }


def extract_retroalimentacion(data: dict[str, Any]) -> dict[str, Any]:
    """
    Extract retroalimentacion from a feedback JSON.

    Args:
        data: Parsed JSON data

    Returns:
        Dictionary with retroalimentacion fields
    """
    retro = data.get("retroalimentacion", {})
    return {
        "puntajes": retro.get("puntajes", []),
        "comentario_narrativo": retro.get("comentario_narrativo", ""),
        "resumen_para_moodle": retro.get("resumen_para_moodle", ""),
    }


def generate_markdown(metadata: dict[str, Any], retroalimentacion: dict[str, Any]) -> str:
    """
    Generate markdown content from feedback data.

    Args:
        metadata: Metadata dictionary
        retroalimentacion: Retroalimentacion dictionary

    Returns:
        Markdown string
    """
    lines = [
        "# Retroalimentación Académica",
        "",
        f"**Estudiante:** {metadata['estudiante']}  ",
        f"**Archivo original:** {metadata['archivo_original']}  ",
        f"**Curso:** {metadata['curso']}  ",
        f"**Unidad:** {metadata['unidad']}  ",
        f"**Actividad:** {metadata['actividad']}  ",
        f"**Fecha:** {metadata['fecha_procesamiento']}",
        "",
        "## Puntajes por criterio",
        "",
    ]

    # Generate puntajes table
    puntajes = retroalimentacion.get("puntajes", [])
    if puntajes:
        lines.append("| Criterio | Puntaje | Máximo | Justificación |")
        lines.append("| -------- | ------- | ------ | ------------- |")

        for p in puntajes:
            criterio = p.get("criterio", "")
            puntaje = p.get("puntaje", 0)
            maximo = p.get("maximo", 0)
            justificacion = p.get("justificacion", "")
            # Escape pipes in justificacion for markdown table
            justificacion_escaped = justificacion.replace("|", "\\|").replace("\n", " ")
            lines.append(f"| {criterio} | {puntaje} | {maximo} | {justificacion_escaped} |")
    else:
        lines.append("*No hay puntajes disponibles.*")

    lines.append("")
    lines.append("## Comentario narrativo")
    lines.append("")
    lines.append(retroalimentacion.get("comentario_narrativo", "*Sin comentario narrativo.*"))
    lines.append("")
    lines.append("## Resumen para Moodle")
    lines.append("")
    lines.append(retroalimentacion.get("resumen_para_moodle", "*Sin resumen.*"))

    return "\n".join(lines)


def sanitize_filename(name: str) -> str:
    """
    Sanitize a string for use as filename.

    Args:
        name: Original name

    Returns:
        Sanitized filename
    """
    import re
    sanitized = re.sub(r'[<>:"/\\|?*]', '_', name)
    sanitized = re.sub(r'\s+', '_', sanitized)
    sanitized = sanitized.strip('.')
    return sanitized or "unnamed"


def generate_pdf(markdown_content: str, pdf_path: Path) -> bool:
    """
    Generate PDF from markdown using Pandoc.

    Args:
        markdown_content: Markdown string
        pdf_path: Output PDF path

    Returns:
        True if successful, False otherwise
    """
    # Create temporary markdown file
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".md",
        encoding="utf-8",
        delete=False,
    ) as tmp:
        tmp.write(markdown_content)
        tmp_path = Path(tmp.name)

    try:
        # Run pandoc
        result = subprocess.run(
            [
                "pandoc",
                str(tmp_path),
                "-o", str(pdf_path),
                "--pdf-engine=xelatex"
            ],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            print(f"WARNING: Pandoc error: {result.stderr}")
            return False

        return True

    except FileNotFoundError:
        print("ERROR: Pandoc no encontrado. Instálalo con: sudo apt install pandoc texlive-xetex")
        return False
    except Exception as e:
        print(f"WARNING: Error generando PDF: {e}")
        return False
    finally:
        # Clean up temp file
        try:
            tmp_path.unlink()
        except Exception:
            pass


def compute_total_score(puntajes: list[dict[str, Any]]) -> int | str:
    """
    Compute total score from puntajes list.

    Args:
        puntajes: List of puntaje dictionaries

    Returns:
        Total score as int, or "ERROR (sin puntajes)" if empty
    """
    if not puntajes:
        return "ERROR (sin puntajes)"

    total = 0
    for p in puntajes:
        score = p.get("puntaje", 0)
        if isinstance(score, (int, float)):
            total += score

    return int(total)


def generate_resumen(grades: list[tuple[str, int | str]], output_path: Path) -> None:
    """
    Generate resumen_calificaciones.txt file.

    Args:
        grades: List of (estudiante, total_score) tuples
        output_path: Path to output file
    """
    # Sort alphabetically by student name
    grades_sorted = sorted(grades, key=lambda x: x[0].lower())

    lines = []
    for estudiante, score in grades_sorted:
        lines.append(f"{estudiante}: {score}")

    with output_path.open("w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def main() -> int:
    """Main entry point."""
    args = parse_args()

    json_dir = args.json_dir

    if not json_dir.exists():
        print(f"ERROR: Directorio no encontrado: {json_dir}")
        return 1

    if not json_dir.is_dir():
        print(f"ERROR: No es un directorio: {json_dir}")
        return 1

    # Discover all JSON files
    json_files = list(json_dir.glob("*.json"))

    if not json_files:
        print(f"ERROR: No se encontraron archivos JSON en {json_dir}")
        return 1

    print(f"Encontrados {len(json_files)} archivos JSON en {json_dir}")

    # Load first valid JSON to extract course/unit/activity
    curso = None
    unidad = None
    actividad = None

    for json_file in json_files:
        data = load_json_file(json_file)
        if data:
            meta = extract_metadata(data)
            curso = meta.get("curso")
            unidad = meta.get("unidad")
            actividad = meta.get("actividad")
            if curso and actividad:
                break

    if not curso:
        print("WARNING: No se pudo extraer 'curso' de los JSON. Usando 'unknown'.")
        curso = "unknown"

    if not unidad:
        unidad = 1

    if not actividad:
        print("WARNING: No se pudo extraer 'actividad' de los JSON. Usando 'unknown'.")
        actividad = "unknown"

    # Create output directory
    pdf_dir = Path("outputs_feedback") / curso / f"unidad_{unidad}" / f"actividad_{actividad}"
    pdf_dir.mkdir(parents=True, exist_ok=True)

    print(f"Directorio de salida: {pdf_dir}")

    # Process each JSON
    grades: list[tuple[str, int | str]] = []
    success_count = 0
    error_count = 0

    for json_file in json_files:
        print(f"Procesando: {json_file}")

        data = load_json_file(json_file)
        if not data:
            error_count += 1
            continue

        # Extract data
        metadata = extract_metadata(data)
        retroalimentacion = extract_retroalimentacion(data)

        estudiante = metadata.get("estudiante", "Desconocido")

        # Generate markdown
        markdown = generate_markdown(metadata, retroalimentacion)

	# Generate PDF
        if args.sanitize:
            pdf_filename = f"{sanitize_filename(estudiante)}.pdf"
        else:
            stem = json_file.stem.rstrip('. ')
            pdf_filename = f"{stem}.pdf"
        
        pdf_path = pdf_dir / pdf_filename
        
        
        if generate_pdf(markdown, pdf_path):
            print(f"PDF generado: {pdf_path}")
            success_count += 1
        else:
            print(f"WARNING: No se pudo generar PDF para {estudiante}")
            error_count += 1

        # Compute score for resumen
        puntajes = retroalimentacion.get("puntajes", [])
        total = compute_total_score(puntajes)
        grades.append((estudiante, total))

    # Generate resumen_calificaciones.txt
    resumen_path = pdf_dir / "resumen_calificaciones.txt"
    generate_resumen(grades, resumen_path)
    print(f"Resumen generado en: {resumen_path}")

    # Summary
    print()
    print("=" * 60)
    print(f"Procesamiento completado:")
    print(f"  - PDFs generados: {success_count}")
    print(f"  - Errores: {error_count}")
    print(f"  - Resumen: {resumen_path}")
    print("=" * 60)

    return 0 if error_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
