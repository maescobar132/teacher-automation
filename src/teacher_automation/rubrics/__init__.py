"""
Rubrics module.

Handles loading, parsing, and applying grading rubrics to student work.
"""

from .loader import RubricLoader
from .models import Rubric, Criterion

__all__ = ["RubricLoader", "Rubric", "Criterion"]
