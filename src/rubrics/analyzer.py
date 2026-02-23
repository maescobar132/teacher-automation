"""
Analyzer for rubrics to extract citation constraints and requirements.

This module parses rubric JSON files to extract meaningful constraints
about citations, formatting, and other requirements that can be injected
into LLM prompts to improve evaluation accuracy and reduce false positives.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.utils.logging import get_logger

logger = get_logger(__name__)


def analyze_rubric(rubric_path: Path) -> dict[str, Any]:
    """
    Analyze a rubric to extract citation constraints and other requirements.

    Args:
        rubric_path: Path to the rubric JSON file

    Returns:
        Dictionary with extracted constraints:
        {
            "name": "rubric name",
            "citation_constraints": {
                "Introducción": {
                    "forbid_all_citations": bool,
                    "description": "reason"
                },
                "Conclusiones": {
                    "forbid_all_citations": bool,
                    "description": "reason"
                }
            },
            "format_requirements": [list of format rules],
            "structure_requirements": [list of structural requirements]
        }
    """
    with rubric_path.open("r", encoding="utf-8") as f:
        rubric = json.load(f)

    constraints = {
        "name": rubric.get("nombre", ""),
        "citation_constraints": {},
        "format_requirements": [],
        "structure_requirements": [],
    }

    # Analyze each criterio
    criterios = rubric.get("criterios", [])
    for criterio in criterios:
        name = criterio.get("nombre", "")
        niveles = criterio.get("niveles", [])

        # Check if this is an Intro or Conclusion criterion
        if name in ["Introducción", "Conclusions", "Conclusiones"]:
            forbid_citations = _check_forbid_citations(niveles)
            if forbid_citations is not None:
                constraints["citation_constraints"][name] = {
                    "forbid_all_citations": forbid_citations,
                    "description": _get_constraint_description(niveles, forbid_citations),
                }

        # Extract format requirements
        format_reqs = _extract_format_requirements(name, niveles)
        if format_reqs:
            constraints["format_requirements"].extend(format_reqs)

        # Extract structure requirements
        struct_reqs = _extract_structure_requirements(name, niveles)
        if struct_reqs:
            constraints["structure_requirements"].extend(struct_reqs)

    return constraints


def _check_forbid_citations(niveles: list[dict]) -> bool | None:
    """
    Check if a criterion explicitly forbids citations in its best level.

    Looks for keywords like:
    - "sin citas" (without citations)
    - "personal" (personal, non-cited)
    - "sin citas textuales y/o parafraseadas" (no direct or indirect citations)

    Args:
        niveles: List of scoring levels

    Returns:
        True if citations are forbidden, False if they're required, None if unclear
    """
    if not niveles:
        return None

    # Check the highest scoring level (usually index 0)
    best_level = niveles[0]
    descripcion = best_level.get("descripcion", "").lower()

    # Keywords that indicate citations should NOT be present
    forbid_keywords = [
        "sin citas",
        "sin citas textuales",
        "sin citas textuales y/o parafraseadas",
        "personal",
        "propio",
        "sin referencias",
    ]

    # Keywords that indicate citations ARE required
    require_keywords = [
        "con fundamento",
        "con citas",
        "parafraseado",
        "citas apa",
        "citación",
    ]

    # Check for forbid keywords
    for keyword in forbid_keywords:
        if keyword in descripcion:
            # Make sure it's not contradicted
            if not any(rk in descripcion for rk in require_keywords):
                return True

    # Check for require keywords
    for keyword in require_keywords:
        if keyword in descripcion:
            return False

    return None


def _get_constraint_description(niveles: list[dict], forbid: bool) -> str:
    """
    Get a human-readable description of the citation constraint.

    Args:
        niveles: List of scoring levels
        forbid: Whether citations are forbidden

    Returns:
        Description string
    """
    if not niveles:
        return ""

    best_level = niveles[0]
    desc = best_level.get("descripcion", "")

    # Extract the relevant part about citations
    if forbid:
        return f"Personal work without citations required. {desc[:100]}"
    else:
        return f"Proper citations required. {desc[:100]}"


def _extract_format_requirements(name: str, niveles: list[dict]) -> list[str]:
    """
    Extract format requirements from a criterion.

    Args:
        name: Criterion name
        niveles: List of scoring levels

    Returns:
        List of format requirements
    """
    if not niveles:
        return []

    requirements = []
    best_level = niveles[0]
    desc = best_level.get("descripcion", "")

    format_keywords = {
        "arial": "Arial font",
        "apa": "APA format",
        "sangría francesa": "Hanging indent (French hanging)",
        "interlineado": "Line spacing",
        "justificado": "Text justified",
        "mayúsculas": "Capitalization",
        "numeradas": "Page numbering",
    }

    for keyword, description in format_keywords.items():
        if keyword.lower() in desc.lower():
            requirements.append(f"{name}: {description}")

    return requirements


def _extract_structure_requirements(name: str, niveles: list[dict]) -> list[str]:
    """
    Extract structural requirements from a criterion.

    Args:
        name: Criterion name
        niveles: List of scoring levels

    Returns:
        List of structural requirements
    """
    if not niveles:
        return []

    requirements = []
    best_level = niveles[0]
    desc = best_level.get("descripcion", "")

    structure_keywords = {
        "tabla": "Include table",
        "párrafo": "Paragraph structure",
        "página": "Page length",
        "elementos": "Required elements",
        "coherencia": "Coherence/cohesion",
        "vinculación": "Connection to research",
    }

    for keyword, description in structure_keywords.items():
        if keyword.lower() in desc.lower():
            requirements.append(f"{name}: {description}")

    return requirements


def build_citation_constraints_prompt(constraints: dict[str, Any]) -> str:
    """
    Build a prompt section with citation constraints to inject into LLM instructions.

    Args:
        constraints: Output from analyze_rubric()

    Returns:
        Formatted prompt string
    """
    if not constraints.get("citation_constraints"):
        return ""

    lines = [
        "\n---",
        "**CITATION REQUIREMENTS (from rubric):**\n",
    ]

    for section, constraint in constraints["citation_constraints"].items():
        if constraint["forbid_all_citations"]:
            lines.append(
                f"• {section}: NO citations allowed (textual or paraphrased). "
                f"Must be personal, original writing."
            )
        else:
            lines.append(
                f"• {section}: Proper citations required. Verify Autor (Año) format."
            )

    lines.append("")
    return "\n".join(lines)


def get_sections_forbidding_citations(constraints: dict[str, Any]) -> list[str]:
    """
    Get list of sections that forbid citations.

    Args:
        constraints: Output from analyze_rubric()

    Returns:
        List of section names that forbid citations
    """
    return [
        name
        for name, constraint in constraints.get("citation_constraints", {}).items()
        if constraint.get("forbid_all_citations", False)
    ]


if __name__ == "__main__":
    # Example usage
    from pathlib import Path

    rubric_path = Path("src/config/rubrics/rubric_3.2_tabla_diseno_investigacion.json")

    if rubric_path.exists():
        analysis = analyze_rubric(rubric_path)
        print(json.dumps(analysis, indent=2, ensure_ascii=False))
        print("\nPrompt injection:")
        print(build_citation_constraints_prompt(analysis))
    else:
        print(f"Rubric not found: {rubric_path}")
