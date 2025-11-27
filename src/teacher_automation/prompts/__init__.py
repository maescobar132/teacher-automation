"""
Prompt templates module.

Contains and manages prompt templates for AI-assisted grading and feedback.
"""

from .loader import PromptLoader
from .templates import PromptTemplate

__all__ = ["PromptLoader", "PromptTemplate"]
