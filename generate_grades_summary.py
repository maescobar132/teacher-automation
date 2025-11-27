#!/usr/bin/env python3
"""
Generate a CSV summary of grades from feedback JSON files.

Usage:
    python generate_grades_summary.py --dir outputs/FI08/unidad_1/actividad_1.1
    python generate_grades_summary.py --dir outputs/FI08/unidad_1/actividad_1.1 --output grades.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path


def extract_grades_from_json(json_path: Path) -> dict | None:
    """Extract student name and grades from a feedback JSON file."""
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        metadata = data.get("metadata", {})
        retroalimentacion = data.get("retroalimentacion", {})
        puntajes = retroalimentacion.get("puntajes", [])

        # Extract student name (first part before underscore)
        estudiante_full = metadata.get("estudiante", json_path.stem)
        estudiante = estudiante_full.split("_")[0].strip()

        # Calculate total score
        total = sum(p.get("puntaje", 0) for p in puntajes)
        max_total = sum(p.get("maximo", 0) for p in puntajes)

        result = {
            "estudiante": estudiante,
            "estudiante_completo": estudiante_full,
            "archivo": metadata.get("archivo_original", ""),
            "total": total,
            "maximo": max_total,
            "porcentaje": round(total / max_total * 100, 1) if max_total > 0 else 0,
        }

        # Add individual criteria scores
        for p in puntajes:
            criterio = p.get("criterio", "")
            result[f"score_{criterio}"] = p.get("puntaje", 0)

        return result

    except Exception as e:
        print(f"Error reading {json_path.name}: {e}", file=sys.stderr)
        return None


def generate_summary(feedback_dir: Path, output_path: Path | None = None) -> Path:
    """Generate a CSV summary of all grades in a directory."""
    json_files = sorted(f for f in feedback_dir.glob("*.json") if not f.stem.startswith("_"))

    if not json_files:
        print(f"No JSON files found in {feedback_dir}", file=sys.stderr)
        sys.exit(1)

    # Extract grades from all files
    all_grades = []
    all_criteria = set()

    for json_path in json_files:
        grade_data = extract_grades_from_json(json_path)
        if grade_data:
            all_grades.append(grade_data)
            # Collect all criteria names
            for key in grade_data:
                if key.startswith("score_"):
                    all_criteria.add(key)

    if not all_grades:
        print("No valid grade data extracted", file=sys.stderr)
        sys.exit(1)

    # Sort criteria for consistent column order
    sorted_criteria = sorted(all_criteria)

    # Define output path
    if output_path is None:
        output_path = feedback_dir / "grades_summary.csv"

    # Write CSV
    fieldnames = ["estudiante", "total", "maximo", "porcentaje"] + sorted_criteria + ["estudiante_completo", "archivo"]

    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()

        # Sort by student name
        for grade in sorted(all_grades, key=lambda x: x["estudiante"]):
            writer.writerow(grade)

    print(f"Generated: {output_path}")
    print(f"Students:  {len(all_grades)}")

    # Print summary statistics
    totals = [g["total"] for g in all_grades]
    avg = sum(totals) / len(totals)
    print(f"Average:   {avg:.1f} / {all_grades[0]['maximo']}")
    print(f"Min:       {min(totals)}")
    print(f"Max:       {max(totals)}")

    return output_path


def main():
    parser = argparse.ArgumentParser(
        description="Generate CSV summary of grades from feedback JSON files"
    )
    parser.add_argument(
        "-d", "--dir",
        required=True,
        help="Directory containing feedback JSON files",
    )
    parser.add_argument(
        "-o", "--output",
        help="Output CSV file path (default: <dir>/grades_summary.csv)",
    )

    args = parser.parse_args()

    feedback_dir = Path(args.dir).expanduser().resolve()

    if not feedback_dir.exists():
        print(f"Error: Directory not found: {feedback_dir}", file=sys.stderr)
        sys.exit(1)

    output_path = Path(args.output) if args.output else None

    generate_summary(feedback_dir, output_path)


if __name__ == "__main__":
    main()
