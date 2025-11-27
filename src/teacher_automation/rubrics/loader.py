"""Rubric loader for grading criteria."""

from pathlib import Path
from typing import Any

import yaml

from .models import Rubric, Criterion, PerformanceLevel


class RubricLoader:
    """Loads and parses grading rubrics from YAML files."""

    def __init__(self, rubrics_dir: Path | None = None):
        """Initialize the rubric loader.

        Args:
            rubrics_dir: Directory containing rubric files
        """
        self.rubrics_dir = rubrics_dir or Path("rubrics")

    def load(self, rubric_file: str | Path) -> Rubric:
        """Load a rubric from a YAML file.

        Args:
            rubric_file: Path to the rubric YAML file

        Returns:
            Parsed Rubric object
        """
        path = self._resolve_path(rubric_file)
        data = self._load_yaml(path)
        return self._parse_rubric(data)

    def _resolve_path(self, file_path: str | Path) -> Path:
        """Resolve a rubric file path."""
        path = Path(file_path)
        if not path.is_absolute():
            path = self.rubrics_dir / path
        return path

    def _load_yaml(self, path: Path) -> dict[str, Any]:
        """Load and parse a YAML file."""
        if not path.exists():
            raise FileNotFoundError(f"Rubric file not found: {path}")

        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f)

    def _parse_rubric(self, data: dict[str, Any]) -> Rubric:
        """Parse rubric data into a Rubric object."""
        criteria = []
        for criterion_data in data.get("criteria", []):
            levels = [
                PerformanceLevel(
                    name=level["name"],
                    points=level["points"],
                    description=level["description"],
                )
                for level in criterion_data.get("levels", [])
            ]
            criteria.append(
                Criterion(
                    name=criterion_data["name"],
                    description=criterion_data.get("description", ""),
                    weight=criterion_data.get("weight", 1.0),
                    max_points=criterion_data.get("max_points", 100),
                    levels=levels,
                )
            )

        return Rubric(
            name=data["name"],
            description=data.get("description", ""),
            total_points=data.get("total_points", 100),
            criteria=criteria,
        )
