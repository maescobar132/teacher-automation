"""Output generation module for teacher-automation."""

from .pdf_generator import generate_pdf_from_feedback, generate_pdfs_from_directory

__all__ = ["generate_pdf_from_feedback", "generate_pdfs_from_directory"]
