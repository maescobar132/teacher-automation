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
        / "teacher_automation"
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

    Args:
        file_path: Ruta al archivo

    Returns:
        Nombre del estudiante (stem del archivo)
    """
    return file_path.stem


def extract_text_from_file(file_path: Path) -> str:
    """
    Extrae texto de un archivo usando el módulo de procesamiento.

    Args:
        file_path: Ruta al archivo

    Returns:
        Texto extraído
    """
    from src.teacher_automation.processing.parser import extract_text

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
    from src.teacher_automation.processing.submissions import extract_tables_from_submission

    return extract_tables_from_submission(file_path)


def build_table_injection_context(tables: list, activity_id: str) -> str:
    """
    Construye el contexto de inyección de tablas para el prompt.

    Solo se inyectan tablas para las actividades 3.1 y 3.2 que requieren
    evaluación de datos estructurados (Tabla de Operacionalización, etc.).

    Args:
        tables: Lista de DataFrames extraídos del documento
        activity_id: ID de la actividad (ej: "3.1", "3.2")

    Returns:
        Cadena de contexto para inyectar en el prompt, o cadena vacía si
        la actividad no requiere inyección de tablas.
    """
    # Solo inyectar tablas para actividades que lo requieran
    ACTIVITIES_REQUIRING_TABLES = {"3.1", "3.2"}

    if activity_id not in ACTIVITIES_REQUIRING_TABLES:
        return ""

    if not tables:
        return ""

    from src.teacher_automation.processing.submissions import dataframes_to_markdown_context

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
    from src.teacher_automation.grading.generate_feedback import generate_feedback_for_text

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
        "--model",
        default="claude-sonnet-4-20250514",
        help="Modelo de Claude (default: claude-sonnet-4-20250514)",
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

    args = parser.parse_args()

    # Banner
    print("\n" + "=" * 60)
    print("GENERADOR DE RETROALIMENTACIÓN FORMATIVA")
    if args.hybrid:
        print(">>> MODO HÍBRIDO: Evaluación AI + Manual <<<")
    print("=" * 60)
    print(f"Curso: {args.course}")
    print(f"Unidad: {args.unit}")
    print(f"Actividad: {args.activity}")
    print(f"Directorio: {args.dir}")
    if args.hybrid:
        print(f"Modo: HÍBRIDO (revisión manual de formato)")
    print("=" * 60)

    # 1. Validar directorio o extraer ZIP
    input_path = Path(args.dir).expanduser().resolve()

    if not input_path.exists():
        print(f"\n✗ Error: No encontrado: {input_path}", file=sys.stderr)
        sys.exit(1)

    # If it's a ZIP file, extract it
    if input_path.is_file() and input_path.suffix.lower() == ".zip":
        import zipfile
        import tempfile

        print(f"\n📦 Extrayendo ZIP: {input_path.name}")

        # Extract to a temp directory next to the zip
        extract_dir = input_path.parent / input_path.stem
        extract_dir.mkdir(exist_ok=True)

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
            from src.teacher_automation.processing.filenames import clean_and_rename_files

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
            table_context = build_table_injection_context(tables, args.activity)

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

        from src.teacher_automation.grading.generate_feedback import generate_feedback_batch
        from src.teacher_automation.manual.manual_review import (
            convert_to_pdf,
            open_pdf_viewer,
            prompt_manual_scores,
            merge_manual_scores,
            calculate_final_total,
            get_format_criteria,
            get_auto_full_score_criteria,
            generate_auto_scores,
        )

        # Load rubric for manual scoring reference
        rubric = load_rubric(rubric_path)
        format_criteria = get_format_criteria()
        auto_criteria = get_auto_full_score_criteria()

        # Check which format criteria exist in the rubric
        rubric_criteria_names = [c.get("nombre", "") for c in rubric.get("criterios", [])]
        valid_format_criteria = [c for c in format_criteria if c in rubric_criteria_names]
        valid_auto_criteria = [c for c in auto_criteria if c in rubric_criteria_names]

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

            # Process each student sequentially
            results = []
            successful = 0
            failed = 0

            # Map original files to submissions for PDF conversion
            file_map = {sub["archivo_original"]: sub for sub in submissions}
            original_file_map = {f.name: f for f in submission_files}

            for i, submission in enumerate(submissions, 1):
                student_name = submission["estudiante"]
                archivo_original = submission["archivo_original"]
                original_file = original_file_map.get(archivo_original)

                print(f"\n{'=' * 60}")
                print(f"[{i}/{len(submissions)}] PROCESANDO: {student_name}")
                print(f"{'=' * 60}")

                try:
                    # Step 1: Open document for manual review
                    print("\n1. Abriendo documento para revisión...")
                    if original_file and original_file.exists():
                        try:
                            pdf_path = convert_to_pdf(original_file)
                            print(f"   PDF: {pdf_path.name}")
                            print("   >>> Revise el documento y cierre el visor cuando termine <<<")
                            open_pdf_viewer(pdf_path, wait=True)
                        except Exception as e:
                            print(f"   ⚠ No se pudo abrir PDF: {e}")
                            print("   Continuando con evaluación manual sin visor...")
                    else:
                        print(f"   ⚠ Archivo original no encontrado: {archivo_original}")

                    # Step 2: Prompt for manual scores (formato, referencias)
                    print("\n2. Evaluación manual de criterios de formato...")
                    manual_result = prompt_manual_scores(rubric, valid_format_criteria)

                    # Generate auto scores for criteria like Portada
                    auto_result = generate_auto_scores(rubric, valid_auto_criteria)

                    # Merge auto scores into manual_result
                    manual_result["scores"].update(auto_result["scores"])
                    manual_result["comments"].update(auto_result["comments"])

                    # Build manual_scores dict for AI integration (includes both manual and auto)
                    all_manual_criteria = valid_format_criteria + valid_auto_criteria
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

                    # Step 3: Generate AI feedback (with manual scores integrated)
                    print("\n3. Generando retroalimentación AI...")
                    submission_with_manual = submission.copy()
                    submission_with_manual["manual_scores"] = manual_scores_for_ai

                    batch_result = generate_feedback_batch(
                        submissions=[submission_with_manual],
                        rubric_path=rubric_path,
                        prompt_path=prompt_path,
                        curso=args.course,
                        unidad=args.unit,
                        actividad=args.activity,
                        activity_instructions=activity_instructions,
                        descripcion_yaml=yaml_description,
                        model=args.model,
                        output_base_path=None,  # Don't save yet
                        manual_criteria=all_manual_criteria,
                    )

                    if not batch_result or not batch_result[0].get("success"):
                        error_msg = batch_result[0].get("error", "Unknown") if batch_result else "No result"
                        print(f"   ✗ Error AI: {error_msg}")
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
                    print(f"   ✓ Puntaje AI: {ai_score}")

                    # Step 4: Merge AI scores with manual scores
                    merged_puntajes = merge_manual_scores(ai_puntajes, manual_result, rubric)
                    totals = calculate_final_total(merged_puntajes)

                    # Update feedback with merged scores
                    feedback["retroalimentacion"]["puntajes"] = merged_puntajes

                    # Add manual scoring metadata
                    feedback["manual_scores"] = manual_result["scores"]
                    feedback["manual_comments"] = manual_result["comments"]
                    feedback["final_total"] = totals["total_obtenido"]
                    feedback["final_maximo"] = totals["total_maximo"]

                    # Step 5: Save final JSON
                    output_json_path = output_dir / f"{student_name}.json"
                    output_json_path.parent.mkdir(parents=True, exist_ok=True)
                    with output_json_path.open("w", encoding="utf-8") as f:
                        json.dump(feedback, f, ensure_ascii=False, indent=2)

                    final_score = totals["total_obtenido"]
                    print(f"\n   ✓ Puntaje final: {final_score}/{totals['total_maximo']}")
                    print(f"   ✓ JSON guardado: {output_json_path.name}")

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
                    print(f"\n   ✗ Error procesando {student_name}: {e}")
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

    else:
        # --- MODO NORMAL (batch processing) ---
        print("\n" + "=" * 60)
        print("GENERANDO RETROALIMENTACIÓN (con prompt caching)...")
        print("=" * 60)

        from src.teacher_automation.grading.generate_feedback import generate_feedback_batch

        batch_results = generate_feedback_batch(
            submissions=submissions,
            rubric_path=rubric_path,
            prompt_path=prompt_path,
            curso=args.course,
            unidad=args.unit,
            actividad=args.activity,
            activity_instructions=activity_instructions,
            descripcion_yaml=yaml_description,
            model=args.model,
            output_base_path=project_root / "outputs",
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
            from src.teacher_automation.output.pdf_generator import generate_hybrid_pdf_from_feedback

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
            from src.teacher_automation.output.pdf_generator import generate_pdfs_from_directory

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
