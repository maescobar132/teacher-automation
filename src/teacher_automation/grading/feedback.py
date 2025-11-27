"""Feedback generation utilities."""

from dataclasses import dataclass

from ..utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class FeedbackOptions:
    """Options for feedback generation."""

    include_rubric_breakdown: bool = True
    include_suggestions: bool = True
    max_length: int | None = None
    tone: str = "constructive"  # constructive, formal, casual


class FeedbackGenerator:
    """Generates and formats feedback for students."""

    def __init__(self, options: FeedbackOptions | None = None):
        """Initialize the feedback generator.

        Args:
            options: Feedback generation options
        """
        self.options = options or FeedbackOptions()

    def format_for_moodle(self, feedback: str, score: float, max_score: float) -> str:
        """Format feedback for Moodle's feedback field.

        Args:
            feedback: Raw feedback text
            score: Achieved score
            max_score: Maximum possible score

        Returns:
            HTML-formatted feedback for Moodle
        """
        percentage = (score / max_score * 100) if max_score > 0 else 0

        html_parts = [
            f"<h4>Score: {score:.1f} / {max_score:.1f} ({percentage:.1f}%)</h4>",
            "<hr>",
            self._markdown_to_html(feedback),
        ]

        return "\n".join(html_parts)

    def format_for_email(self, feedback: str, student_name: str, assignment_name: str) -> str:
        """Format feedback for email delivery.

        Args:
            feedback: Raw feedback text
            student_name: Student's name
            assignment_name: Name of the assignment

        Returns:
            Formatted email body
        """
        return f"""Dear {student_name},

Your submission for "{assignment_name}" has been graded. Please find the feedback below:

{feedback}

If you have any questions about this feedback, please don't hesitate to reach out.

Best regards,
Your Instructor
"""

    def combine_feedback(self, criterion_feedback: dict[str, str], summary: str = "") -> str:
        """Combine individual criterion feedback into a single message.

        Args:
            criterion_feedback: Dict mapping criterion names to feedback
            summary: Optional summary feedback

        Returns:
            Combined feedback text
        """
        parts = []

        if summary:
            parts.append(f"## Summary\n{summary}\n")

        if self.options.include_rubric_breakdown:
            parts.append("## Detailed Feedback")
            for criterion, feedback in criterion_feedback.items():
                parts.append(f"\n### {criterion}\n{feedback}")

        return "\n".join(parts)

    def _markdown_to_html(self, text: str) -> str:
        """Convert simple markdown to HTML.

        Args:
            text: Markdown text

        Returns:
            HTML formatted text
        """
        # Simple conversion - for production, use a proper markdown library
        html = text
        html = html.replace("\n\n", "</p><p>")
        html = html.replace("\n", "<br>")

        # Wrap in paragraph tags
        if not html.startswith("<"):
            html = f"<p>{html}</p>"

        return html
