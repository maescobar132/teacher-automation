"""Turnitin data models."""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class MatchSource:
    """A source that matched in the similarity report."""

    name: str
    percentage: float
    url: str | None = None
    source_type: str = "internet"  # internet, publication, student_paper


@dataclass
class SimilarityReport:
    """Similarity report from Turnitin."""

    submission_id: str
    overall_similarity: float
    internet_similarity: float = 0.0
    publication_similarity: float = 0.0
    student_paper_similarity: float = 0.0
    generated_at: datetime | None = None
    top_matches: list[MatchSource] = field(default_factory=list)
    report_url: str | None = None

    @property
    def is_concerning(self, threshold: float = 25.0) -> bool:
        """Check if similarity is above a concerning threshold."""
        return self.overall_similarity >= threshold

    def get_summary(self) -> str:
        """Get a text summary of the report."""
        lines = [
            f"Overall Similarity: {self.overall_similarity:.1f}%",
            f"  - Internet: {self.internet_similarity:.1f}%",
            f"  - Publications: {self.publication_similarity:.1f}%",
            f"  - Student Papers: {self.student_paper_similarity:.1f}%",
        ]

        if self.top_matches:
            lines.append("\nTop Matches:")
            for match in self.top_matches[:5]:
                lines.append(f"  - {match.name}: {match.percentage:.1f}%")

        return "\n".join(lines)
