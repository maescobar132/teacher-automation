#!/usr/bin/env python3
"""
CLI para procesar entregas de estudiantes y generar retroalimentación formativa.

Uso:
    python run_activity.py --course FI08 --unit 1 --activity 1.1 --dir ~/Downloads/entregas
    python run_activity.py --course FI08 --unit 1 --activity 1.1 --dir ~/Downloads/entregas --rename

Modo Híbrido (evaluación manual de formato):
    python run_activity.py --course FI08 --unit 1 --activity 1.3 --dir ~/Downloads/a --rename --hybrid

Este script:
1. Carga la configuración del curso desde el YAML
2. (Opcional) Limpia y renombra archivos con --rename
3. Procesa todos los archivos PDF, DOCX, DOC en el directorio
4. Genera retroalimentación para cada estudiante
5. (Modo híbrido) Abre el documento para revisión manual y solicita puntajes de formato
6. Guarda los resultados en outputs/<curso>/<unidad>/<actividad>/<Estudiante>.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

import yaml

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".doc"}


def load_course_config(course_id: str) -> dict:
    """
    Carga la configuración del curso desde el archivo YAML.

    Args:
        course_id: Identificador del curso (ej: FI08)

    Returns:
        Diccionario con la configuración del curso
    """
    config_path = (
        Path(__file__).parent
        / "src"
        / "config"
        / "courses"
        / f"{course_id}.yml"
    )

    if not config_path.exists():
        raise FileNotFoundError(
            f"No se encontró configuración para el curso: {course_id}\n"
            f"Ruta: {config_path}"
        )

    with config_path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def find_activity(config: dict, unit_num: int, activity_id: str) -> dict | None:
    """
    Busca una actividad específica en la configuración del curso.

    Args:
        config: Configuración del curso
        unit_num: Número de unidad
        activity_id: ID de la actividad

    Returns:
        Diccionario con la configuración de la actividad o None
    """
    for unidad in config.get("unidades", []):
        if unidad.get("unidad") == unit_num:
            for actividad in unidad.get("actividades", []):
                if actividad.get("id") == activity_id:
                    return actividad
    return None


def get_submission_files(directory: Path) -> list[Path]:
    """
    Obtiene todos los archivos de entrega en un directorio.

    Si hay múltiples archivos con el mismo nombre base (stem) pero diferentes
    extensiones, se prefiere PDF > DOCX > DOC.

    Args:
        directory: Directorio con las entregas

    Returns:
        Lista de rutas a archivos soportados (uno por estudiante)
    """
    files = []
    for ext in SUPPORTED_EXTENSIONS:
        files.extend(directory.glob(f"*{ext}"))
        files.extend(directory.glob(f"*{ext.upper()}"))

    # Deduplicate by stem, preferring PDF > DOCX > DOC
    extension_priority = {".pdf": 0, ".docx": 1, ".doc": 2}
    seen_stems = {}

    for f in files:
        stem = f.stem
        ext_lower = f.suffix.lower()
        priority = extension_priority.get(ext_lower, 99)

        if stem not in seen_stems or priority < seen_stems[stem][1]:
            seen_stems[stem] = (f, priority)

    return sorted([f for f, _ in seen_stems.values()])


def extract_student_name_from_file(file_path: Path) -> str:
    """
    Extrae el nombre del estudiante del nombre del archivo.

    Maneja nombres Moodle como:
      "JUAN PEREZ_123456_assignsubmission_file_informe.pdf" -> "JUAN_PEREZ"

    Args:
        file_path: Ruta al archivo

    Returns:
        Nombre del estudiante limpio (sin metadatos de Moodle)
    """
    from src.processing.filenames import extract_student_name as _extract
    raw = _extract(file_path.name)
    # Convert spaces to underscores for a valid identifier
    return raw.replace(" ", "_")


def extract_text_from_file(file_path: Path) -> str:
    """
    Extrae texto de un archivo usando el módulo de procesamiento.

    Args:
        file_path: Ruta al archivo

    Returns:
        Texto extraído
    """
    from src.processing.parser import extract_text

    result = extract_text(file_path)
    return result.text


def extract_tables_from_file(file_path: Path) -> list:
    """
    Extrae tablas de un archivo DOCX o PDF.

    Args:
        file_path: Ruta al archivo

    Returns:
        Lista de DataFrames de pandas, uno por tabla encontrada
    """
    from src.processing.submissions import extract_tables_from_submission

    return extract_tables_from_submission(file_path)


def build_table_injection_context(tables: list, activity_id: str, activity: dict | None = None) -> str:
    """
    Construye el contexto de inyección de tablas para el prompt.

    Se inyectan tablas si la actividad tiene extraer_tablas: true en su config YAML,
    o como fallback si el activity_id está en el conjunto legacy {"3.1", "3.2"}.

    Args:
        tables: Lista de DataFrames extraídos del documento
        activity_id: ID de la actividad (ej: "3.1", "3.2")
        activity: Diccionario de configuración de la actividad (del YAML)

    Returns:
        Cadena de contexto para inyectar en el prompt, o cadena vacía si
        la actividad no requiere inyección de tablas.
    """
    # Check YAML config first; fall back to legacy hardcoded set
    if activity is not None:
        requires_tables = activity.get("extraer_tablas", False)
    else:
        requires_tables = activity_id in {"3.1", "3.2"}

    if not requires_tables:
        return ""

    if not tables:
        return ""

    from src.processing.submissions import dataframes_to_markdown_context

    table_markdown = dataframes_to_markdown_context(tables, activity_id)

    return (
        f"CONTEXTO ADICIONAL DE LA ACTIVIDAD: Actividad {activity_id}\n\n"
        f"El estudiante ha presentado la siguiente información estructurada (tablas) "
        f"extraída de su documento:\n"
        f"{table_markdown}\n\n"
        f"Asegúrate de evaluar la coherencia de estos datos estructurados con las "
        f"instrucciones y el resto del texto.\n\n"
    )


def load_rubric(rubric_path: Path) -> dict:
    """
    Carga la rúbrica desde un archivo JSON.

    Args:
        rubric_path: Ruta al archivo de rúbrica

    Returns:
        Diccionario con la rúbrica
    """
    with rubric_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_prompt(prompt_path: Path) -> str:
    """
    Carga el prompt desde un archivo de texto.

    Args:
        prompt_path: Ruta al archivo de prompt

    Returns:
        Contenido del prompt
    """
    return prompt_path.read_text(encoding="utf-8")


def save_feedback(
    output_path: Path,
    student_name: str,
    feedback: dict,
    original_filename: str,
    course: str,
    unit: int,
    activity_id: str,
    rubric_file: str,
    activity_instructions: str,
    yaml_description: str,
) -> None:
    """
    Guarda la retroalimentación en un archivo JSON con trazabilidad completa.

    Args:
        output_path: Ruta al archivo de salida
        student_name: Nombre del estudiante
        feedback: Diccionario con la retroalimentación
        original_filename: Nombre del archivo original
        course: Código del curso
        unit: Número de unidad
        activity_id: ID de la actividad
        rubric_file: Nombre del archivo de rúbrica usado
        activity_instructions: Instrucciones de la actividad ingresadas por el tutor
        yaml_description: Descripción de la actividad desde el YAML
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    output_data = {
        "metadata": {
            "estudiante": student_name,
            "archivo_original": original_filename,
            "fecha_procesamiento": datetime.now().isoformat(),
            "curso": course,
            "unidad": unit,
            "actividad": activity_id,
            "rubrica_usada": rubric_file,
            "descripcion_yaml": yaml_description,
            "activity_instructions": activity_instructions,
        },
        "retroalimentacion": feedback,
    }

    with output_path.open("w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)


def process_submission(
    file_path: Path,
    rubric_path: Path,
    prompt_path: Path,
    yaml_description: str,
    activity_instructions: str,
    output_dir: Path,
    model: str,
    course: str,
    unit: int,
    activity_id: str,
) -> dict:
    """
    Procesa una entrega individual.

    Args:
        file_path: Ruta al archivo de entrega
        rubric_path: Ruta a la rúbrica
        prompt_path: Ruta al prompt
        yaml_description: Descripción de la actividad desde el YAML
        activity_instructions: Instrucciones de la actividad ingresadas por el tutor
        output_dir: Directorio de salida
        model: Modelo de Claude a usar
        course: Código del curso
        unit: Número de unidad
        activity_id: ID de la actividad

    Returns:
        Diccionario con resultado del procesamiento
    """
    from src.grading.generate_feedback import generate_feedback_for_text

    student_name = extract_student_name_from_file(file_path)

    # Extraer texto del documento
    student_text = extract_text_from_file(file_path)

    if not student_text.strip():
        return {
            "student": student_name,
            "file": file_path.name,
            "success": False,
            "error": "El archivo está vacío o no se pudo extraer texto",
        }

    # Generar retroalimentación
    feedback = generate_feedback_for_text(
        student_text=student_text,
        rubric_path=rubric_path,
        prompt_path=prompt_path,
        estudiante=student_name,
        archivo_original=file_path.name,
        curso=course,
        unidad=unit,
        actividad=activity_id,
        activity_instructions=activity_instructions,
        descripcion_yaml=yaml_description,
        model=model,
    )

    # Guardar resultado con trazabilidad completa
    output_path = output_dir / f"{student_name}.json"
    save_feedback(
        output_path=output_path,
        student_name=student_name,
        feedback=feedback,
        original_filename=file_path.name,
        course=course,
        unit=unit,
        activity_id=activity_id,
        rubric_file=rubric_path.name,
        activity_instructions=activity_instructions,
        yaml_description=yaml_description,
    )

    return {
        "student": student_name,
        "file": file_path.name,
        "success": True,
        "output": str(output_path),
        "score": sum(p.get("puntaje", 0) for p in feedback.get("puntajes", [])),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Genera retroalimentación formativa para entregas estudiantiles",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python run_activity.py --course FI08 --unit 1 --activity 1.1 --dir ~/Downloads/entregas
  python run_activity.py -c FI08 -u 1 -a 1.1 -d ~/Downloads/entregas --rename

El script procesará todos los archivos PDF, DOCX y DOC en el directorio
especificado y generará retroalimentación para cada uno.
        """,
    )

    parser.add_argument(
        "-c", "--course",
        required=True,
        help="Código del curso (ej: FI08)",
    )
    parser.add_argument(
        "-u", "--unit",
        type=int,
        required=True,
        help="Número de unidad",
    )
    parser.add_argument(
        "-a", "--activity",
        required=True,
        help="ID de la actividad (ej: 1.1, 1.2)",
    )
    parser.add_argument(
        "-d", "--dir",
        required=True,
        help="Directorio o archivo ZIP con los archivos de entrega",
    )
    parser.add_argument(
        "--no-pdf",
        action="store_true",
        help="No generar PDFs de retroalimentación (solo JSON)",
    )
    parser.add_argument(
        "--rename",
        action="store_true",
        help="Limpiar y renombrar archivos antes de procesar",
    )
    parser.add_argument(
        "--force-extract",
        action="store_true",
        help="Re-extraer ZIP aunque el directorio ya exista (sobreescribe archivos existentes)",
    )
    parser.add_argument(
        "--provider",
        default="anthropic",
        choices=["anthropic", "deepseek"],
        help="Proveedor de LLM (default: anthropic)",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Modelo específico (si no se especifica, usa el default del proveedor)",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=1.0,
        help="Temperatura para generación de retroalimentación (default: 1.0)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Mostrar información de debug",
    )
    parser.add_argument(
        "--hybrid",
        action="store_true",
        help="Modo híbrido: evaluación AI + revisión manual de formato",
    )
    parser.add_argument(
        "--manual-criteria",
        nargs="+",
        default=None,
        help="Lista de nombres de criterios a evaluar manualmente. Si se usa, SOBRESCRIBE los criterios manuales por defecto.",
    )
    parser.add_argument(
        "--presentation",
        action="store_true",
        help="Modo presentación: calificación interactiva manual de presentaciones PPT",
    )

    args = parser.parse_args()

    # Banner
    print("\n" + "=" * 60)
    print("GENERADOR DE RETROALIMENTACIÓN FORMATIVA")
    if args.hybrid:
        print(">>> MODO HÍBRIDO: Evaluación AI + Manual <<<")
    if args.presentation:
        print(">>> MODO PRESENTACIÓN: Calificación Interactiva Manual <<<")
    print("=" * 60)
    print(f"Curso: {args.course}")
    print(f"Unidad: {args.unit}")
    print(f"Actividad: {args.activity}")
    print(f"Directorio: {args.dir}")
    if args.hybrid:
        print(f"Modo: HÍBRIDO (revisión manual de formato)")
    if args.presentation:
        print(f"Modo: PRESENTACIÓN (calificación interactiva)")
    print("=" * 60)

    # PRESENTATION MODE - Special workflow
    if args.presentation:
        from src.grading.grade_presentations import (
            batch_convert_presentations,
            load_rubric as load_rubric_presentations,
            load_prompt as load_prompt_presentations,
            load_progress,
            save_progress,
            open_pdf,
            grade_criterion_interactive,
            generate_feedback_with_llm,
            preview_and_edit_feedback,
        )
        from src.processing.filenames import extract_student_name, clean_name_no_swap

        project_root = Path(__file__).parent

        # Load configuration
        try:
            config = load_course_config(args.course)
            print(f"\n✓ Configuración cargada: {config.get('nombre', args.course)}")
        except FileNotFoundError as e:
            print(f"\n✗ Error: {e}", file=sys.stderr)
            sys.exit(1)

        # Find activity
        activity = find_activity(config, args.unit, args.activity)
        if not activity:
            print(
                f"\n✗ Error: No se encontró la actividad {args.activity} "
                f"en la unidad {args.unit}",
                file=sys.stderr,
            )
            sys.exit(1)

        # Get rubric and prompt paths
        rubric_path = project_root / activity.get("rubrica", "")
        prompt_path = project_root / activity.get("prompt", "")

        if not rubric_path.exists():
            print(f"\n✗ Error: No se encontró la rúbrica: {rubric_path}", file=sys.stderr)
            sys.exit(1)

        if not prompt_path.exists():
            print(f"\n✗ Error: No se encontró el prompt: {prompt_path}", file=sys.stderr)
            sys.exit(1)

        # Load rubric and prompt
        rubric = load_rubric_presentations(rubric_path)
        prompt_template = load_prompt_presentations(prompt_path)

        print(f"✓ Rúbrica: {rubric_path.name}")
        print(f"✓ Prompt: {prompt_path.name}")

        # Setup directories
        presentations_dir = Path(args.dir).expanduser().resolve()
        if not presentations_dir.exists() or not presentations_dir.is_dir():
            print(f"\n✗ Error: Directorio no encontrado: {presentations_dir}", file=sys.stderr)
            sys.exit(1)

        output_dir = project_root / "outputs" / args.course / f"unidad_{args.unit}" / f"actividad_{args.activity}"
        pdf_dir = output_dir / "pdfs"
        progress_path = output_dir / ".progress.json"

        # Step 1: Batch convert PPTX to PDF
        print("\n" + "=" * 60)
        print("PASO 1: CONVERSIÓN PPTX → PDF")
        print("=" * 60)

        conversions = batch_convert_presentations(presentations_dir, pdf_dir)
        if not conversions:
            print(f"\n✗ Error: No se encontraron presentaciones para convertir", file=sys.stderr)
            sys.exit(1)

        print(f"\n✓ {len(conversions)} presentaciones procesadas")

        # Step 2: Interactive grading
        print("\n" + "=" * 60)
        print("PASO 2: CALIFICACIÓN INTERACTIVA")
        print("=" * 60)

        progress = load_progress(progress_path)
        completed_students = set(progress.get("completed", []))
        all_scores = progress.get("scores", {})

        # Use PDFs from conversions (includes both converted and existing PDFs)
        pdf_files = sorted([pdf_path for _, pdf_path in conversions])
        pending_pdfs = [p for p in pdf_files if p.stem not in completed_students]

        if not pending_pdfs:
            print("\n✓ Todos los estudiantes ya han sido calificados")
        else:
            print(f"\nPendientes: {len(pending_pdfs)}/{len(pdf_files)}")
            print("(Presiona Ctrl+C en cualquier momento para guardar y salir)\n")

            try:
                for i, pdf_path in enumerate(pending_pdfs, 1):
                    student_id = pdf_path.stem

                    # Extract student name from filename
                    # Format: Firstname_Lastname.pdf (already in correct order, no swap needed)
                    raw_name = extract_student_name(pdf_path.name)
                    cleaned_name = clean_name_no_swap(raw_name)
                    student_display = cleaned_name.replace('_', ' ')

                    print(f"\n{'=' * 70}")
                    print(f"ESTUDIANTE [{i + len(completed_students)}/{len(pdf_files)}]: {student_display}")
                    print(f"Archivo: {pdf_path.name}")
                    print(f"{'=' * 70}")

                    # Open PDF
                    try:
                        open_pdf(pdf_path)
                        print("✓ PDF abierto (puedes revisar mientras calificas)")
                        print("  Cierra el visor cuando termines con este estudiante\n")
                    except Exception as e:
                        print(f"⚠ No se pudo abrir PDF: {e}")
                        print("  Continúa con la calificación...\n")

                    # Extract text from presentation for LLM context
                    presentation_text = ""
                    try:
                        from src.processing.parser import extract_text_from_pdf
                        result = extract_text_from_pdf(pdf_path)
                        presentation_text = result.text
                        logger.info(f"Extraído {len(presentation_text)} caracteres de {pdf_path.name}")
                    except Exception as e:
                        logger.warning(f"No se pudo extraer texto de {pdf_path.name}: {e}")
                        presentation_text = ""

                    # Grade each criterion
                    student_scores = {}
                    for criterio in rubric["criterios"]:
                        criterio_name = criterio["nombre"]

                        score, comment = grade_criterion_interactive(
                            criterio_name=criterio_name,
                            criterio_data=criterio,
                            student_num=i + len(completed_students),
                            total_students=len(pdf_files),
                            student_name=student_display,
                        )

                        student_scores[criterio_name] = (score, comment)

                    # Save scores and mark complete
                    all_scores[student_id] = {
                        "student_name": student_display,
                        "scores": student_scores,
                        "presentation_text": presentation_text,
                    }
                    completed_students.add(student_id)

                    progress["completed"] = list(completed_students)
                    progress["scores"] = all_scores
                    save_progress(progress_path, progress)

                    print(f"\n✓ Progreso guardado ({len(completed_students)}/{len(pdf_files)} completados)")

            except (KeyboardInterrupt, EOFError):
                print("\n\n⚠ Calificación interrumpida. Progreso guardado.")
                print(f"   Completados: {len(completed_students)}/{len(pdf_files)}")
                sys.exit(0)

        # Step 3: Generate LLM feedback for all completed
        print("\n" + "=" * 60)
        print("PASO 3: GENERACIÓN DE RETROALIMENTACIÓN CON LLM")
        print("=" * 60)

        if not completed_students:
            print("\n⚠ No hay estudiantes calificados para generar retroalimentación")
            sys.exit(0)

        output_dir.mkdir(parents=True, exist_ok=True)

        for student_id in completed_students:
            student_data = all_scores[student_id]
            student_name = student_data["student_name"]
            scores = student_data["scores"]
            presentation_text = student_data.get("presentation_text", "")

            # Check if JSON already exists
            json_path = output_dir / f"{student_id}.json"
            if json_path.exists():
                print(f"  ⊘ {student_name} - ya existe JSON, omitiendo")
                continue

            print(f"\n{'=' * 70}")
            print(f"Generando retroalimentación: {student_name}")
            print(f"{'=' * 70}")

            try:
                # Generate feedback with LLM
                feedback = generate_feedback_with_llm(
                    student_name=student_name,
                    rubric=rubric,
                    scores=scores,
                    prompt_template=prompt_template,
                    presentation_text=presentation_text,
                    provider=args.provider,
                    model=args.model,
                    temperature=args.temperature,
                )

                # Preview and edit
                feedback = preview_and_edit_feedback(feedback, student_name)

                # Build final JSON structure
                output_data = {
                    "metadata": {
                        "estudiante": student_name,
                        "archivo_original": f"{student_id}.pdf",
                        "fecha_procesamiento": datetime.now().isoformat(),
                        "curso": args.course,
                        "unidad": args.unit,
                        "actividad": args.activity,
                        "rubrica_usada": rubric_path.name,
                        "descripcion_yaml": activity.get("titulo", ""),
                        "activity_instructions": activity.get("instrucciones", ""),
                    },
                    "retroalimentacion": feedback,
                }

                # Save JSON
                with json_path.open("w", encoding="utf-8") as f:
                    json.dump(output_data, f, ensure_ascii=False, indent=2)

                print(f"\n✓ JSON guardado: {json_path.name}")

            except Exception as e:
                print(f"\n✗ Error generando retroalimentación: {e}")
                if args.debug:
                    import traceback
                    traceback.print_exc()

        # Generate CSV with grades
        try:
            import csv
            json_files = sorted([f for f in output_dir.glob("*.json") if f.name != ".progress.json"])

            if json_files:
                # Collect all unique criteria
                all_criterios = []
                for json_file in json_files:
                    with open(json_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    puntajes = data.get("retroalimentacion", {}).get("puntajes", [])
                    for p in puntajes:
                        criterio = p.get("criterio", "")
                        if criterio and criterio not in all_criterios:
                            all_criterios.append(criterio)

                # Build fieldnames and data
                fieldnames = ["Estudiante", "Archivo"] + all_criterios + ["Total", "Porcentaje"]
                rows = []

                for json_file in json_files:
                    with open(json_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)

                    metadata = data.get("metadata", {})
                    puntajes = data.get("retroalimentacion", {}).get("puntajes", [])
                    estudiante = metadata.get("estudiante", json_file.stem)

                    row = {field: "" for field in fieldnames}
                    row["Estudiante"] = estudiante.replace("_", " ")
                    row["Archivo"] = metadata.get("archivo_original", json_file.name)

                    total = 0
                    maximo = 0
                    for p in puntajes:
                        criterio = p.get("criterio", "")
                        puntaje = p.get("puntaje", 0)
                        max_pts = p.get("maximo", 0)
                        if criterio in row:
                            row[criterio] = f"{puntaje}/{max_pts}"
                        total += puntaje
                        maximo += max_pts

                    row["Total"] = f"{total}/{maximo}"
                    row["Porcentaje"] = f"{(total/maximo*100):.1f}%" if maximo > 0 else "0%"
                    rows.append(row)

                # Write CSV
                csv_path = output_dir / "calificaciones.csv"
                with open(csv_path, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(rows)

                print(f"\n✓ CSV generado: {csv_path.name}")
        except Exception as e:
            logger.warning(f"No se pudo generar CSV: {e}")

        print("\n" + "=" * 60)
        print("CALIFICACIÓN COMPLETADA")
        print("=" * 60)
        print(f"Total estudiantes: {len(completed_students)}")
        print(f"JSONs generados en: {output_dir}")
        print("\nPara generar PDFs, ejecuta:")
        print(f"  python -m src.output.pdf_generator --input-dir {output_dir}")
        print("=" * 60)

        sys.exit(0)

    # 1. Validar directorio o extraer ZIP
    input_path = Path(args.dir).expanduser().resolve()

    if not input_path.exists():
        print(f"\n✗ Error: No encontrado: {input_path}", file=sys.stderr)
        sys.exit(1)

    # If it's a ZIP file, extract it
    if input_path.is_file() and input_path.suffix.lower() == ".zip":
        import zipfile

        # Extract to a directory next to the zip
        extract_dir = input_path.parent / input_path.stem
        extract_dir.mkdir(exist_ok=True)

        # Check if directory already has submission files
        existing_files = []
        for ext in SUPPORTED_EXTENSIONS:
            existing_files.extend(extract_dir.glob(f"*{ext}"))
            existing_files.extend(extract_dir.glob(f"*{ext.upper()}"))
        # Also check one level deep (Moodle sometimes nests files)
        for ext in SUPPORTED_EXTENSIONS:
            existing_files.extend(extract_dir.glob(f"**/*{ext}"))

        if existing_files and not args.force_extract:
            print(f"\n📁 Usando directorio ya extraído: {extract_dir}")
            print(f"   ({len(existing_files)} archivos encontrados)")
            print(f"   Usa --force-extract para re-extraer el ZIP completo")
            submissions_dir = extract_dir
        else:
            print(f"\n📦 Extrayendo ZIP: {input_path.name}")
            try:
                with zipfile.ZipFile(input_path, 'r') as zip_ref:
                    zip_ref.extractall(extract_dir)
                print(f"✓ Extraído a: {extract_dir}")
                submissions_dir = extract_dir
            except zipfile.BadZipFile:
                print(f"\n✗ Error: Archivo ZIP inválido: {input_path}", file=sys.stderr)
                sys.exit(1)
    elif input_path.is_dir():
        submissions_dir = input_path
    else:
        print(f"\n✗ Error: Debe ser un directorio o archivo ZIP: {input_path}", file=sys.stderr)
        sys.exit(1)

    # 2. Cargar configuración del curso
    try:
        config = load_course_config(args.course)
        print(f"\n✓ Configuración cargada: {config.get('nombre', args.course)}")
    except FileNotFoundError as e:
        print(f"\n✗ Error: {e}", file=sys.stderr)
        sys.exit(1)

    # 3. Buscar la actividad
    activity = find_activity(config, args.unit, args.activity)
    if not activity:
        print(
            f"\n✗ Error: No se encontró la actividad {args.activity} "
            f"en la unidad {args.unit}",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"✓ Actividad: {activity.get('titulo', args.activity)}")
    print(f"  Tipo: {activity.get('tipo', 'escrito')}")
    print(f"  Extraer texto: {activity.get('extraer_texto', False)}")

    # 4. Obtener rutas de rúbrica y prompt
    project_root = Path(__file__).parent
    rubric_path = project_root / activity.get("rubrica", "")
    prompt_path = project_root / activity.get("prompt", "")

    if not rubric_path.exists():
        print(f"\n✗ Error: No se encontró la rúbrica: {rubric_path}", file=sys.stderr)
        sys.exit(1)

    if not prompt_path.exists():
        print(f"\n✗ Error: No se encontró el prompt: {prompt_path}", file=sys.stderr)
        sys.exit(1)

    print(f"✓ Rúbrica: {rubric_path.name}")
    print(f"✓ Prompt: {prompt_path.name}")

    # 5. Obtener instrucciones de la actividad (desde YAML o manual)
    yaml_instrucciones = activity.get("instrucciones", "")
    if yaml_instrucciones and yaml_instrucciones.strip():
        activity_instructions = yaml_instrucciones.strip()
        print(f"\n✓ Instrucciones cargadas desde YAML ({len(activity_instructions)} caracteres)")
    else:
        print("\n" + "=" * 60)
        print("INSTRUCCIONES DE LA ACTIVIDAD")
        print("=" * 60)
        print("Pega aquí las instrucciones completas de la actividad tomadas de Moodle.")
        print("Cuando termines, presiona Ctrl+D (Linux/Mac) o Ctrl+Z seguido de Enter (Windows).")
        print("-" * 60 + "\n")

        try:
            activity_instructions = sys.stdin.read().strip()
        except Exception:
            activity_instructions = ""

        if not activity_instructions:
            print("\n⚠️ ADVERTENCIA: No se ingresaron instrucciones de actividad.")
            print("   El modelo evaluará únicamente con la rúbrica y el texto del estudiante.\n")
        else:
            print(f"\n✓ Instrucciones recibidas ({len(activity_instructions)} caracteres)")

    # 6. Renombrar archivos si se solicita
    if args.rename:
        print("\n" + "-" * 60)
        print("RENOMBRANDO ARCHIVOS...")
        print("-" * 60)

        try:
            from src.processing.filenames import clean_and_rename_files

            renamed = clean_and_rename_files(submissions_dir)
            if renamed:
                print(f"✓ {len(renamed)} archivos renombrados")
                for old_path, new_path in renamed:
                    print(f"  • {old_path.name} -> {new_path.name}")
            else:
                print("  No se renombraron archivos")
        except Exception as e:
            print(f"\n✗ Error renombrando: {e}", file=sys.stderr)
            if args.debug:
                import traceback
                traceback.print_exc()
            sys.exit(1)

    # 7. Obtener archivos a procesar
    submission_files = get_submission_files(submissions_dir)

    if not submission_files:
        print(f"\n✗ Error: No se encontraron archivos en {submissions_dir}", file=sys.stderr)
        sys.exit(1)

    print(f"\n✓ Encontrados {len(submission_files)} archivos para procesar")

    # 8. Configurar directorio de salida
    output_dir = (
        project_root
        / "outputs"
        / args.course
        / f"unidad_{args.unit}"
        / f"actividad_{args.activity}"
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"✓ Directorio de salida: {output_dir}")

    # 9. Obtener descripción de la actividad desde YAML
    yaml_description = activity.get("titulo", "") or activity.get("descripcion", "")

    # 10. Load rubric early (before hybrid block) to avoid scoping issues
    rubric = load_rubric(rubric_path)

    # 10. Preparar submissions para batch processing
    print("\n" + "=" * 60)
    print("EXTRAYENDO TEXTO DE ENTREGAS...")
    print("=" * 60)

    submissions = []
    extraction_errors = []

    for i, file_path in enumerate(submission_files, 1):
        student_name = extract_student_name_from_file(file_path)
        print(f"[{i}/{len(submission_files)}] {student_name}...", end=" ")

        try:
            student_text = extract_text_from_file(file_path)

            if not student_text.strip():
                print("⚠ vacío")
                extraction_errors.append({
                    "student": student_name,
                    "file": file_path.name,
                    "error": "El archivo está vacío o no se pudo extraer texto",
                })
                continue

            # Extract tables for debug logging and potential injection
            tables = []
            try:
                tables = extract_tables_from_file(file_path)
                if args.debug and tables:
                    print(f"[{len(tables)} tablas] ", end="")
            except Exception as table_err:
                if args.debug:
                    print(f"[tablas: {table_err}] ", end="")

            # Build table injection context for activities 3.1 and 3.2
            table_context = build_table_injection_context(tables, args.activity, activity)

            # Prepend table context to student text if applicable
            if table_context:
                final_text = table_context + student_text
                if args.debug:
                    print("[+tabla_ctx] ", end="")
            else:
                final_text = student_text

            submissions.append({
                "id": student_name,
                "text": final_text,
                "estudiante": student_name,
                "archivo_original": file_path.name,
                "tables": tables,  # Include extracted tables in submission data
            })
            print("✓")

        except Exception as e:
            print(f"✗ {e}")
            extraction_errors.append({
                "student": student_name,
                "file": file_path.name,
                "error": str(e),
            })

    print(f"\n✓ {len(submissions)} archivos listos para procesar")
    if extraction_errors:
        print(f"⚠ {len(extraction_errors)} archivos con errores de extracción")

    # 11. Procesar entregas
    # En modo híbrido: procesar secuencialmente con revisión manual
    # En modo normal: procesar en batch con prompt caching

    if args.hybrid:
        # --- MODO HÍBRIDO ---
        print("\n" + "=" * 60)
        print("MODO HÍBRIDO: AI + REVISIÓN MANUAL")
        print("=" * 60)

        from src.grading.generate_feedback import generate_feedback_batch
        from src.manual.manual_review import (
            convert_to_pdf,
            open_pdf_viewer,
            prompt_manual_scores,
            merge_manual_scores,
            calculate_final_total,
            get_format_criteria,
            get_auto_full_score_criteria,
            generate_auto_scores,
            prompt_citas_textuales_check,
        )

        # --- LÓGICA DE CARGA DINÁMICA DE CRITERIOS MANUALES ---
        if args.manual_criteria:
            # Caso 1: Usar la lista de criterios provista por el usuario (CLI)
            manual_criteria_to_check = args.manual_criteria
            print(f"\n[INFO] Usando criterios manuales explícitos (CLI): {manual_criteria_to_check}")
        else:
            # Caso 2: Usar la lista de criterios por defecto (fallback)
            manual_criteria_to_check = get_format_criteria()
            print(f"\n[INFO] Usando criterios manuales por defecto: {manual_criteria_to_check}")

        # Criterios automáticos (siempre desde defaults)
        auto_criteria = get_auto_full_score_criteria()

        # Check which criteria exist in the rubric
        rubric_criteria_names = [c.get("nombre", "") for c in rubric.get("criterios", [])]
        valid_format_criteria = [c for c in manual_criteria_to_check if c in rubric_criteria_names]
        valid_auto_criteria = [c for c in auto_criteria if c in rubric_criteria_names]

        # Warn about criteria not found in rubric
        missing_criteria = [c for c in manual_criteria_to_check if c not in rubric_criteria_names]
        if missing_criteria:
            print(f"\n⚠ ADVERTENCIA: Criterios no encontrados en rúbrica: {missing_criteria}")
            print(f"   Criterios disponibles: {rubric_criteria_names}")

        # If user explicitly provided criteria via CLI but none are valid, fail early
        if args.manual_criteria and not valid_format_criteria:
            print(f"\n✗ ERROR: Ninguno de los criterios especificados existe en la rúbrica.")
            print(f"   Criterios solicitados: {args.manual_criteria}")
            print(f"   Criterios disponibles: {rubric_criteria_names}")
            sys.exit(1)

        if not valid_format_criteria and not valid_auto_criteria:
            print("\n⚠ ADVERTENCIA: No se encontraron criterios de formato en la rúbrica.")
            print("   Continuando sin evaluación manual...")
            args.hybrid = False  # Fall back to normal mode

        if args.hybrid:
            print(f"\nCriterios para evaluación manual:")
            for criterio in valid_format_criteria:
                print(f"  • {criterio}")
            if valid_auto_criteria:
                print(f"\nCriterios con puntaje completo automático:")
                for criterio in valid_auto_criteria:
                    print(f"  • {criterio}")

            # Process students with parallel AI generation
            # While AI processes student N, tutor reviews student N+1
            from concurrent.futures import ThreadPoolExecutor, Future

            results = []
            successful = 0
            failed = 0

            # Map original files to submissions for PDF conversion
            file_map = {sub["archivo_original"]: sub for sub in submissions}
            original_file_map = {f.name: f for f in submission_files}

            # Track pending AI tasks: list of (student_name, archivo_original, manual_result, future)
            pending_ai_tasks = []
            all_manual_criteria = valid_format_criteria + valid_auto_criteria

            def run_ai_generation(submission_with_manual):
                """Run AI generation in background thread."""
                return generate_feedback_batch(
                    submissions=[submission_with_manual],
                    rubric_path=rubric_path,
                    prompt_path=prompt_path,
                    curso=args.course,
                    unidad=args.unit,
                    actividad=args.activity,
                    activity_instructions=activity_instructions,
                    descripcion_yaml=yaml_description,
                    provider=args.provider,
                    model=args.model,
                    output_base_path=None,
                    temperature=args.temperature,
                    manual_criteria=all_manual_criteria,
                )

            # Use single-threaded executor (API calls should be sequential)
            executor = ThreadPoolExecutor(max_workers=1)

            try:
                for i, submission in enumerate(submissions, 1):
                    student_name = submission["estudiante"]
                    archivo_original = submission["archivo_original"]
                    original_file = original_file_map.get(archivo_original)
                    is_last = (i == len(submissions))

                    # Skip already-processed students
                    json_path = output_dir / f"{student_name}.json"
                    if json_path.exists():
                        print(f"\n  ⊘ [{i}/{len(submissions)}] {student_name.replace('_', ' ')} - ya procesado, omitiendo")
                        successful += 1
                        continue

                    print(f"\n{'=' * 60}")
                    print(f"[{i}/{len(submissions)}] PROCESANDO: {student_name.replace('_', ' ')}")
                    print(f"{'=' * 60}")

                    try:
                        # Step 1: Open document for manual review
                        print("\n1. Abriendo documento para revisión...")
                        if original_file and original_file.exists():
                            try:
                                # Rename file to clean student name for readable title in viewer
                                clean_file = original_file.parent / f"{student_name}{original_file.suffix}"
                                if clean_file != original_file and not clean_file.exists():
                                    original_file.rename(clean_file)
                                    original_file = clean_file

                                if original_file.suffix.lower() in ['.docx', '.doc']:
                                    pdf_path = convert_to_pdf(original_file)
                                    print(f"   Conversión exitosa: {pdf_path.name}")
                                    open_pdf_viewer(pdf_path, wait=True)
                                else:
                                    open_pdf_viewer(original_file, wait=True)
                            except Exception as e:
                                print(f"   ⚠ No se pudo convertir/abrir PDF: {e}")
                                print(f"   Intentando abrir documento original con visor por defecto...")
                                try:
                                    from src.manual.manual_review import open_document
                                    open_document(original_file, wait=True)
                                except Exception as e2:
                                    print(f"   ⚠ No se pudo abrir documento: {e2}")
                                    print("   Continuando con evaluación manual sin visor...")
                        else:
                            print(f"   ⚠ Archivo original no encontrado: {archivo_original}")

                        # Step 2: Ask about citas textuales
                        print("\n2. Verificación de citas textuales...")
                        citas_check = prompt_citas_textuales_check()

                        # Step 3: Prompt for manual scores
                        print("\n3. Evaluación manual de criterios de formato...")
                        manual_result = prompt_manual_scores(rubric, valid_format_criteria)

                        # Generate auto scores for criteria like Portada
                        auto_result = generate_auto_scores(rubric, valid_auto_criteria)
                        manual_result["scores"].update(auto_result["scores"])
                        manual_result["comments"].update(auto_result["comments"])

                        # Build manual_scores dict for AI
                        manual_scores_for_ai = {}
                        for criterio in all_manual_criteria:
                            criterio_data = next(
                                (c for c in rubric.get("criterios", []) if c.get("nombre") == criterio),
                                {}
                            )
                            manual_scores_for_ai[criterio] = {
                                "puntaje": manual_result["scores"].get(criterio, 0),
                                "maximo": criterio_data.get("puntaje_maximo", 5),
                                "comentario": manual_result["comments"].get(criterio, ""),
                            }

                        # Prepare submission with manual data
                        submission_with_manual = submission.copy()
                        submission_with_manual["manual_scores"] = manual_scores_for_ai
                        submission_with_manual["citas_textuales_check"] = citas_check

                        # Step 4: Start AI generation
                        if is_last:
                            # Last student: run synchronously
                            print("\n4. Generando retroalimentación AI...")
                            future = executor.submit(run_ai_generation, submission_with_manual)
                            pending_ai_tasks.append((student_name, archivo_original, manual_result, future))
                        else:
                            # Not last: run in background, continue to next student
                            print("\n4. Iniciando AI en segundo plano...")
                            future = executor.submit(run_ai_generation, submission_with_manual)
                            pending_ai_tasks.append((student_name, archivo_original, manual_result, future))
                            print("   → AI procesando mientras revisas el siguiente documento")

                    except Exception as e:
                        print(f"\n   ✗ Error en revisión manual de {student_name}: {e}")
                        if args.debug:
                            import traceback
                            traceback.print_exc()
                        failed += 1
                        results.append({
                            "student": student_name,
                            "file": archivo_original,
                            "success": False,
                            "error": str(e),
                        })

                # Process all AI results
                print("\n" + "=" * 60)
                print("PROCESANDO RESULTADOS DE AI...")
                print("=" * 60)

                for student_name, archivo_original, manual_result, future in pending_ai_tasks:
                    print(f"\n   Esperando AI para: {student_name}...", end=" ", flush=True)
                    try:
                        batch_result = future.result(timeout=300)  # 5 min timeout

                        if not batch_result or not batch_result[0].get("success"):
                            error_msg = batch_result[0].get("error", "Unknown") if batch_result else "No result"
                            print(f"✗ Error: {error_msg}")
                            failed += 1
                            results.append({
                                "student": student_name,
                                "file": archivo_original,
                                "success": False,
                                "error": error_msg,
                            })
                            continue

                        feedback = batch_result[0]["feedback"]
                        ai_puntajes = feedback["retroalimentacion"]["puntajes"]
                        ai_score = sum(p.get("puntaje", 0) for p in ai_puntajes)

                        # Merge AI scores with manual scores
                        merged_puntajes = merge_manual_scores(ai_puntajes, manual_result, rubric)
                        totals = calculate_final_total(merged_puntajes)

                        # Update feedback
                        feedback["retroalimentacion"]["puntajes"] = merged_puntajes
                        feedback["manual_scores"] = manual_result["scores"]
                        feedback["manual_comments"] = manual_result["comments"]
                        feedback["final_total"] = totals["total_obtenido"]
                        feedback["final_maximo"] = totals["total_maximo"]

                        # Save JSON
                        output_json_path = output_dir / f"{student_name}.json"
                        output_json_path.parent.mkdir(parents=True, exist_ok=True)
                        with output_json_path.open("w", encoding="utf-8") as f:
                            json.dump(feedback, f, ensure_ascii=False, indent=2)

                        final_score = totals["total_obtenido"]
                        print(f"✓ {final_score}/{totals['total_maximo']}")

                        successful += 1
                        results.append({
                            "student": student_name,
                            "file": archivo_original,
                            "success": True,
                            "score": final_score,
                            "ai_score": ai_score,
                            "manual_scores": manual_result["scores"],
                        })

                    except Exception as e:
                        print(f"✗ Error: {e}")
                        if args.debug:
                            import traceback
                            traceback.print_exc()
                        failed += 1
                        results.append({
                            "student": student_name,
                            "file": archivo_original,
                            "success": False,
                            "error": str(e),
                        })

            finally:
                executor.shutdown(wait=False)

    else:
        # --- MODO NORMAL (batch processing) ---
        print("\n" + "=" * 60)
        print("GENERANDO RETROALIMENTACIÓN (con prompt caching)...")
        print("=" * 60)

        from src.grading.generate_feedback import generate_feedback_batch

        batch_results = generate_feedback_batch(
            submissions=submissions,
            rubric_path=rubric_path,
            prompt_path=prompt_path,
            curso=args.course,
            unidad=args.unit,
            actividad=args.activity,
            activity_instructions=activity_instructions,
            descripcion_yaml=yaml_description,
            provider=args.provider,
            model=args.model,
            output_base_path=project_root / "outputs",
            temperature=args.temperature,
        )

        # Convert batch results to expected format
        results = []
        successful = 0
        failed = 0

        for br in batch_results:
            if br["success"]:
                successful += 1
                feedback = br["feedback"]["retroalimentacion"]
                score = sum(p.get("puntaje", 0) for p in feedback.get("puntajes", []))
                results.append({
                    "student": br["id"],
                    "file": br["feedback"]["metadata"]["archivo_original"],
                    "success": True,
                    "score": score,
                })
                print(f"  ✓ {br['id']} - Puntaje: {score}")
            else:
                failed += 1
                results.append({
                    "student": br["id"],
                    "file": "unknown",
                    "success": False,
                    "error": br.get("error", "Unknown"),
                })
                print(f"  ✗ {br['id']} - Error: {br.get('error', 'Unknown')}")

    # Add extraction errors to results
    for err in extraction_errors:
        failed += 1
        results.append({
            "student": err["student"],
            "file": err["file"],
            "success": False,
            "error": err["error"],
        })

    # 11. Resumen final
    print("\n" + "=" * 60)
    print("RESUMEN")
    print("=" * 60)
    print(f"Total procesados: {len(submission_files)}")
    print(f"Exitosos: {successful}")
    print(f"Fallidos: {failed}")
    print(f"Resultados guardados en: {output_dir}")

    # Guardar resumen con trazabilidad completa
    summary_path = output_dir / "_resumen_procesamiento.json"
    summary = {
        "fecha": datetime.now().isoformat(),
        "curso": args.course,
        "unidad": args.unit,
        "actividad": args.activity,
        "descripcion_yaml": yaml_description,
        "activity_instructions": activity_instructions,
        "rubrica_usada": rubric_path.name,
        "prompt_usado": prompt_path.name,
        "directorio_origen": str(submissions_dir),
        "modo_hibrido": args.hybrid,
        "total": len(submission_files),
        "exitosos": successful,
        "fallidos": failed,
        "resultados": results,
    }

    with summary_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(f"Resumen guardado en: {summary_path}")

    # 12. Generar PDFs de retroalimentación
    if not args.no_pdf and successful > 0:
        print("\n" + "=" * 60)
        print("GENERANDO PDFs DE RETROALIMENTACIÓN...")
        print("=" * 60)

        pdf_output_dir = (
            project_root
            / "outputs_pdf"
            / args.course
            / f"unidad_{args.unit}"
            / f"actividad_{args.activity}"
        )
        pdf_output_dir.mkdir(parents=True, exist_ok=True)

        if args.hybrid:
            # Use hybrid PDF generator for full feedback documents
            from src.output.pdf_generator import generate_hybrid_pdf_from_feedback

            pdf_results = []
            json_files = list(output_dir.glob("*.json"))
            json_files = [f for f in json_files if not f.name.startswith("_")]

            for json_path in json_files:
                try:
                    pdf_path = pdf_output_dir / json_path.with_suffix(".pdf").name
                    generate_hybrid_pdf_from_feedback(json_path, pdf_path)
                    pdf_results.append({"success": True, "input": str(json_path)})
                    print(f"  ✓ {pdf_path.name}")
                except Exception as e:
                    pdf_results.append({"success": False, "input": str(json_path), "error": str(e)})
                    print(f"  ✗ {json_path.name}: {e}")
        else:
            # Use standard PDF generator
            from src.output.pdf_generator import generate_pdfs_from_directory

            pdf_results = generate_pdfs_from_directory(
                input_dir=output_dir,
                output_dir=pdf_output_dir,
                recursive=False,
            )

        pdf_successful = sum(1 for r in pdf_results if r["success"])
        print(f"\n✓ {pdf_successful} PDFs generados en: {pdf_output_dir}")

    # 13. Generar CSV de calificaciones
    if successful > 0:
        print("\n" + "=" * 60)
        print("GENERANDO CSV DE CALIFICACIONES...")
        print("=" * 60)

        from generate_grades_summary import generate_summary

        try:
            csv_path = generate_summary(output_dir)
            print(f"✓ CSV generado: {csv_path}")
        except Exception as e:
            print(f"✗ Error generando CSV: {e}")

    print("=" * 60)

    # Exit code
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
