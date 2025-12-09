#!/usr/bin/env python3
"""
Pipeline verification tests for teacher-automation.

This script tests the full pipeline end-to-end without requiring pytest.
Run with: python tests/test_pipeline_verification.py

TEST CASE A: DOCX Pipeline
    - Processes DOCX files from ~/Downloads/test1
    - Generates JSON feedback in outputs/FI08/unidad_1/actividad_1.1/

TEST CASE B: JSON Input Pipeline
    - Reads existing JSON files from ~/Downloads/test2
    - Regenerates PDF output in outputs_pdf/FI08/unidad_1/actividad_1.1/
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


# Required fields in the output JSON
REQUIRED_TOP_LEVEL_FIELDS = ["metadata", "retroalimentacion"]
REQUIRED_METADATA_FIELDS = [
    "estudiante",
    "archivo_original",
    "fecha_procesamiento",
    "curso",
    "unidad",
    "actividad",
]
REQUIRED_RETROALIMENTACION_FIELDS = [
    "puntajes",
    "comentario_narrativo",
]


def find_latest_json(output_dir: Path) -> Path | None:
    """
    Find the most recently modified JSON file in a directory.

    Args:
        output_dir: Directory to search for JSON files

    Returns:
        Path to the most recent JSON file, or None if no JSON files found
    """
    if not output_dir.exists():
        return None

    json_files = list(output_dir.glob("*.json"))
    # Exclude summary files
    json_files = [f for f in json_files if not f.name.startswith("_")]

    if not json_files:
        return None

    # Sort by modification time, most recent first
    json_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
    return json_files[0]


def find_latest_pdf(output_dir: Path) -> Path | None:
    """
    Find the most recently modified PDF file in a directory.

    Args:
        output_dir: Directory to search for PDF files

    Returns:
        Path to the most recent PDF file, or None if no PDF files found
    """
    if not output_dir.exists():
        return None

    pdf_files = list(output_dir.glob("*.pdf"))

    if not pdf_files:
        return None

    # Sort by modification time, most recent first
    pdf_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
    return pdf_files[0]


def assert_json_has_required_fields(json_obj: dict) -> list[str]:
    """
    Check if a JSON object has all required fields.

    The JSON structure may have two formats:
    1. Flat: retroalimentacion contains puntajes, comentario_narrativo directly
    2. Nested: retroalimentacion contains another retroalimentacion with the actual feedback

    Args:
        json_obj: The parsed JSON dictionary

    Returns:
        List of missing field paths (empty list if all fields present)
    """
    missing = []

    # Check top-level fields
    for field in REQUIRED_TOP_LEVEL_FIELDS:
        if field not in json_obj:
            missing.append(field)

    # Check metadata fields
    if "metadata" in json_obj:
        metadata = json_obj["metadata"]
        for field in REQUIRED_METADATA_FIELDS:
            if field not in metadata:
                missing.append(f"metadata.{field}")
    else:
        for field in REQUIRED_METADATA_FIELDS:
            missing.append(f"metadata.{field}")

    # Check retroalimentacion fields
    # Handle both flat and nested structures
    if "retroalimentacion" in json_obj:
        retro = json_obj["retroalimentacion"]

        # Check if it's nested (has another retroalimentacion inside)
        if "retroalimentacion" in retro:
            retro = retro["retroalimentacion"]

        for field in REQUIRED_RETROALIMENTACION_FIELDS:
            if field not in retro:
                missing.append(f"retroalimentacion.{field}")
    else:
        for field in REQUIRED_RETROALIMENTACION_FIELDS:
            missing.append(f"retroalimentacion.{field}")

    return missing


def run_pipeline(command_list: list[str], timeout: int = 300) -> tuple[str, str, int]:
    """
    Run a pipeline command and capture output.

    Args:
        command_list: Command and arguments as a list
        timeout: Maximum seconds to wait for completion

    Returns:
        Tuple of (stdout, stderr, exit_code)
    """
    try:
        result = subprocess.run(
            command_list,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=Path(__file__).parent.parent,  # Project root
        )
        return result.stdout, result.stderr, result.returncode
    except subprocess.TimeoutExpired:
        return "", "TIMEOUT: Command exceeded time limit", -1
    except Exception as e:
        return "", f"EXCEPTION: {e}", -1


def test_case_a_docx_pipeline() -> tuple[bool, list[str]]:
    """
    TEST CASE A: DOCX Pipeline

    Tests processing of DOCX files from ~/Downloads/test1
    and generation of JSON feedback.

    Returns:
        Tuple of (success, list of error messages)
    """
    errors = []

    # Configuration
    input_dir = Path.home() / "Downloads" / "test1"
    output_dir = (
        Path(__file__).parent.parent
        / "outputs"
        / "FI08"
        / "unidad_1"
        / "actividad_1.1"
    )

    # Check input directory exists
    if not input_dir.exists():
        errors.append(f"Input directory not found: {input_dir}")
        return False, errors

    # Check for input files
    input_files = list(input_dir.glob("*.docx")) + list(input_dir.glob("*.pdf"))
    if not input_files:
        errors.append(f"No DOCX or PDF files found in {input_dir}")
        return False, errors

    # Run the pipeline (no --rename to keep original filenames)
    command = [
        sys.executable,
        "run_activity.py",
        "--course", "FI08",
        "--unit", "1",
        "--activity", "1.1",
        "--dir", str(input_dir),
    ]

    print(f"  Running: {' '.join(command)}")
    stdout, stderr, exit_code = run_pipeline(command)

    # Check for manual instruction prompt (should NOT appear)
    if "Pega aquí las instrucciones" in stdout:
        errors.append("Script prompted for manual instructions (should use YAML)")

    # Check exit code
    if exit_code != 0:
        errors.append(f"Pipeline exited with code {exit_code}")
        if stderr:
            errors.append(f"STDERR: {stderr[:500]}")

    # Check for output JSON
    latest_json = find_latest_json(output_dir)
    if not latest_json:
        errors.append(f"No JSON output found in {output_dir}")
        return False, errors

    print(f"  Found output: {latest_json.name}")

    # Validate JSON structure
    try:
        with latest_json.open("r", encoding="utf-8") as f:
            json_data = json.load(f)

        missing_fields = assert_json_has_required_fields(json_data)
        if missing_fields:
            errors.append(f"Missing fields in JSON: {missing_fields}")

    except json.JSONDecodeError as e:
        errors.append(f"Invalid JSON in output file: {e}")
    except Exception as e:
        errors.append(f"Error reading JSON: {e}")

    return len(errors) == 0, errors


def test_case_b_json_input_pipeline() -> tuple[bool, list[str]]:
    """
    TEST CASE B: JSON Input Pipeline

    Tests reading existing JSON files from ~/Downloads/test2
    and regenerating PDF output.

    Returns:
        Tuple of (success, list of error messages)
    """
    errors = []

    # Configuration
    input_dir = Path.home() / "Downloads" / "test2"
    output_dir = (
        Path(__file__).parent.parent
        / "outputs_pdf"
        / "FI08"
        / "unidad_1"
        / "actividad_1.1"
    )

    # Check input directory exists
    if not input_dir.exists():
        errors.append(f"Input directory not found: {input_dir}")
        return False, errors

    # Check for input JSON files
    input_files = list(input_dir.glob("*.json"))
    if not input_files:
        errors.append(f"No JSON files found in {input_dir}")
        return False, errors

    print(f"  Found {len(input_files)} JSON file(s) in input directory")

    # Check if there's a PDF generation script
    # Try to find and run the PDF generation command
    project_root = Path(__file__).parent.parent

    # Look for PDF generation script
    pdf_scripts = [
        project_root / "generate_pdf.py",
        project_root / "run_pdf_generation.py",
        project_root / "src" / "teacher_automation" / "output" / "generate_pdf.py",
    ]

    pdf_script = None
    for script in pdf_scripts:
        if script.exists():
            pdf_script = script
            break

    if not pdf_script:
        # Try using the module directly
        command = [
            sys.executable,
            "-m", "src.teacher_automation.output.pdf_generator",
            "--input-dir", str(input_dir),
            "--output-dir", str(output_dir),
        ]
    else:
        command = [
            sys.executable,
            str(pdf_script),
            "--input-dir", str(input_dir),
            "--output-dir", str(output_dir),
        ]

    print(f"  Running: {' '.join(command)}")
    stdout, stderr, exit_code = run_pipeline(command)

    # Check exit code (may fail if PDF generator doesn't exist yet)
    if exit_code != 0:
        # Check if it's a "module not found" error - this is acceptable
        if "No module named" in stderr or "ModuleNotFoundError" in stderr:
            errors.append("PDF generator module not implemented yet")
            return False, errors
        elif "No such file" in stderr:
            errors.append("PDF generator script not found")
            return False, errors
        else:
            errors.append(f"Pipeline exited with code {exit_code}")
            if stderr:
                errors.append(f"STDERR: {stderr[:500]}")

    # Check for output PDF
    if output_dir.exists():
        latest_pdf = find_latest_pdf(output_dir)
        if latest_pdf:
            print(f"  Found output: {latest_pdf.name}")

            # Verify filename contains student name
            # Read any input JSON to get estudiante name
            try:
                with input_files[0].open("r", encoding="utf-8") as f:
                    input_json = json.load(f)
                estudiante = input_json.get("metadata", {}).get("estudiante", "")
                if estudiante and estudiante.lower() not in latest_pdf.name.lower():
                    errors.append(
                        f"PDF filename '{latest_pdf.name}' does not contain "
                        f"estudiante name '{estudiante}'"
                    )
            except Exception:
                pass  # Skip filename validation if we can't read input JSON
        else:
            errors.append(f"No PDF output found in {output_dir}")
    else:
        errors.append(f"Output directory not created: {output_dir}")

    return len(errors) == 0, errors


def print_summary(results: dict[str, tuple[bool, list[str]]]) -> None:
    """
    Print a human-readable summary of test results.

    Args:
        results: Dictionary mapping test name to (success, errors) tuple
    """
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)

    all_passed = True

    for test_name, (success, errors) in results.items():
        status = "OK" if success else "FAIL"
        print(f"\n{test_name} -> {status}")

        if not success:
            all_passed = False
            for error in errors:
                print(f"  - {error}")

    print("\n" + "=" * 60)
    if all_passed:
        print("ALL TESTS PASSED")
    else:
        print("SOME TESTS FAILED")
    print("=" * 60)


def main():
    """Run all test cases and print summary."""
    print("=" * 60)
    print("PIPELINE VERIFICATION TESTS")
    print("=" * 60)

    results = {}

    # Test Case A: DOCX Pipeline
    print("\n[TEST CASE A] DOCX Pipeline")
    print("-" * 40)
    try:
        success, errors = test_case_a_docx_pipeline()
        results["TEST A DOCX"] = (success, errors)
    except Exception as e:
        results["TEST A DOCX"] = (False, [f"Unexpected exception: {e}"])

    # Test Case B: JSON Input Pipeline
    print("\n[TEST CASE B] JSON Input Pipeline")
    print("-" * 40)
    try:
        success, errors = test_case_b_json_input_pipeline()
        results["TEST B JSON"] = (success, errors)
    except Exception as e:
        results["TEST B JSON"] = (False, [f"Unexpected exception: {e}"])

    # Print summary
    print_summary(results)

    # Exit with appropriate code
    all_passed = all(success for success, _ in results.values())
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
