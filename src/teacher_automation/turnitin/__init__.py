"""
Turnitin integration module.

Handles submission to Turnitin for plagiarism checking and
retrieval of similarity reports.
"""

from .client import TurnitinClient
from .models import SimilarityReport

__all__ = ["TurnitinClient", "SimilarityReport"]
