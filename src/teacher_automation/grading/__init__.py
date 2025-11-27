"""
Grading module.

Handles automated grading using rubrics and AI-assisted feedback generation.
"""

from .grader import Grader
from .feedback import FeedbackGenerator
from .generate_feedback import (
    generate_feedback_for_text,
    generate_feedback_batch,
    load_rubric,
    load_prompt_template,
    build_prompt,
)

__all__ = [
    "Grader",
    "FeedbackGenerator",
    "generate_feedback_for_text",
    "generate_feedback_batch",
    "load_rubric",
    "load_prompt_template",
    "build_prompt",
]
