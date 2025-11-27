"""Rubric data models."""

from dataclasses import dataclass, field


@dataclass
class PerformanceLevel:
    """A performance level within a criterion."""

    name: str
    points: float
    description: str


@dataclass
class Criterion:
    """A single grading criterion within a rubric."""

    name: str
    description: str = ""
    weight: float = 1.0
    max_points: float = 100
    levels: list[PerformanceLevel] = field(default_factory=list)

    def get_level_by_points(self, points: float) -> PerformanceLevel | None:
        """Find the performance level closest to given points."""
        if not self.levels:
            return None

        sorted_levels = sorted(self.levels, key=lambda l: l.points, reverse=True)
        for level in sorted_levels:
            if points >= level.points:
                return level
        return sorted_levels[-1]


@dataclass
class Rubric:
    """A complete grading rubric."""

    name: str
    description: str = ""
    total_points: float = 100
    criteria: list[Criterion] = field(default_factory=list)

    def calculate_weighted_score(
        self, criterion_scores: dict[str, float]
    ) -> float:
        """Calculate total weighted score from individual criterion scores.

        Args:
            criterion_scores: Dict mapping criterion names to scores

        Returns:
            Total weighted score
        """
        total_weight = sum(c.weight for c in self.criteria)
        if total_weight == 0:
            return 0.0

        weighted_sum = 0.0
        for criterion in self.criteria:
            if criterion.name in criterion_scores:
                score = criterion_scores[criterion.name]
                normalized = score / criterion.max_points
                weighted_sum += normalized * criterion.weight

        return (weighted_sum / total_weight) * self.total_points

    def to_prompt_text(self) -> str:
        """Convert rubric to text for inclusion in AI prompts."""
        lines = [f"# Rubric: {self.name}", ""]
        if self.description:
            lines.extend([self.description, ""])

        lines.append("## Criteria:")
        for criterion in self.criteria:
            lines.append(f"\n### {criterion.name} (Weight: {criterion.weight})")
            if criterion.description:
                lines.append(criterion.description)

            if criterion.levels:
                lines.append("\nPerformance Levels:")
                for level in sorted(criterion.levels, key=lambda l: l.points, reverse=True):
                    lines.append(f"- {level.name} ({level.points} pts): {level.description}")

        return "\n".join(lines)
