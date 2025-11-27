"""Configuration loader for course and system settings."""

from pathlib import Path
from typing import Any

import yaml

from .models import CourseConfig, GradingConfig


class ConfigLoader:
    """Loads and validates configuration files."""

    def __init__(self, config_dir: Path | None = None):
        """Initialize the config loader.

        Args:
            config_dir: Directory containing config files. Defaults to ./config
        """
        self.config_dir = config_dir or (Path(__file__).parent)

    def load_course(self, course_file: str | Path) -> CourseConfig:
        """Load a course configuration from YAML.

        Args:
            course_file: Path to the course YAML file

        Returns:
            Parsed CourseConfig object
        """
        path = self._resolve_path(course_file)
        data = self._load_yaml(path)
        return CourseConfig.from_dict(data)

    def load_grading(self, grading_file: str | Path) -> GradingConfig:
        """Load grading configuration from YAML.

        Args:
            grading_file: Path to the grading config YAML file

        Returns:
            Parsed GradingConfig object
        """
        path = self._resolve_path(grading_file)
        data = self._load_yaml(path)
        return GradingConfig.from_dict(data)

    def _resolve_path(self, file_path: str | Path) -> Path:
        """Resolve a config file path."""
        path = Path(file_path)
        if not path.is_absolute():
            path = self.config_dir / path
        return path

    def _load_yaml(self, path: Path) -> dict[str, Any]:
        """Load and parse a YAML file."""
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")

        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f)
