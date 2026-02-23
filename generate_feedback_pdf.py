#!/usr/bin/env python3
"""
Script para generar PDFs de retroalimentación desde archivos JSON existentes
sin necesidad de reejecutar el procesamiento.

Uso:
    python generate_feedback_pdf.py --input-dir outputs/FI09/unidad_2/actividad_2.2
    python generate_feedback_pdf.py -i outputs/FI09/unidad_2/actividad_2.2 -o outputs_pdf/FI09/unidad_2/actividad_2.2
"""

import argparse
import json
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(
        description="Genera PDFs de retroalimentación desde JSONs existentes",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python generate_feedback_pdf.py -i outputs/FI09/unidad_2/actividad_2.2
  python generate_feedback_pdf.py -i outputs/FI09/unidad_2/actividad_2.2 -o outputs_pdf/FI09/unidad_2/actividad_2.2
        """,
    )

    parser.add_argument(
        "-i", "--input-dir",
        required=True,
        help="Directorio con archivos JSON de retroalimentación",
    )
    parser.add_argument(
        "-o", "--output-dir",
        default=None,
        help="Directorio de salida para PDFs (default: outputs_pdf paralelo a inputs)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Mostrar información de debug",
    )

    args = parser.parse_args()

    # Setup paths
    input_dir = Path(args.input_dir).expanduser().resolve()

    if not input_dir.exists() or not input_dir.is_dir():
        print(f"✗ Error: Directorio no encontrado: {input_dir}", file=sys.stderr)
        sys.exit(1)

    # Find all JSON files (exclude summary)
    json_files = list(input_dir.glob("*.json"))
    json_files = [f for f in json_files if not f.name.startswith("_")]

    if not json_files:
        print(f"✗ Error: No se encontraron archivos JSON en: {input_dir}", file=sys.stderr)
        sys.exit(1)

    print(f"\n✓ Encontrados {len(json_files)} archivos JSON")

    # Determine output directory
    if args.output_dir:
        output_dir = Path(args.output_dir).expanduser().resolve()
    else:
        # Try to infer from input path structure
        # outputs/COURSE/unidad_X/actividad_Y -> outputs_pdf/COURSE/unidad_X/actividad_Y
        parts = input_dir.parts
        if "outputs" in parts:
            idx = parts.index("outputs")
            output_parts = list(parts[:idx]) + ["outputs_pdf"] + list(parts[idx + 1 :])
            output_dir = Path(*output_parts) if output_parts else Path("outputs_pdf")
        else:
            output_dir = input_dir.parent / "outputs_pdf" / input_dir.name

    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"✓ Directorio de salida: {output_dir}\n")

    # Generate PDFs
    print("=" * 60)
    print("GENERANDO PDFs...")
    print("=" * 60)

    try:
        from src.output.pdf_generator import generate_hybrid_pdf_from_feedback

        successful = 0
        failed = 0

        for i, json_path in enumerate(json_files, 1):
            student_name = json_path.stem
            pdf_path = output_dir / json_path.with_suffix(".pdf").name

            try:
                print(f"[{i}/{len(json_files)}] {student_name}...", end=" ")
                generate_hybrid_pdf_from_feedback(json_path, pdf_path)
                print("✓")
                successful += 1
            except Exception as e:
                print(f"✗ {str(e)[:60]}")
                if args.debug:
                    import traceback
                    traceback.print_exc()
                failed += 1

        print("\n" + "=" * 60)
        print("RESUMEN")
        print("=" * 60)
        print(f"Exitosos: {successful}")
        print(f"Fallidos: {failed}")
        print(f"PDFs guardados en: {output_dir}")
        print("=" * 60)

        sys.exit(0 if failed == 0 else 1)

    except Exception as e:
        print(f"\n✗ Error: {e}", file=sys.stderr)
        if args.debug:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
