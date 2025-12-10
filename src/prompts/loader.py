"""Prompt template loader."""

from pathlib import Path
from typing import Any

from .templates import PromptTemplate


class PromptLoader:
    """Loads prompt templates from files."""

    def __init__(self, prompts_dir: Path | None = None):
        """Initialize the prompt loader.

        Args:
            prompts_dir: Directory containing prompt template files
        """
        self.prompts_dir = prompts_dir or Path("prompts")
        self._cache: dict[str, PromptTemplate] = {}

    def load(self, template_file: str | Path, use_cache: bool = True) -> PromptTemplate:
        """Load a prompt template from a file.

        Args:
            template_file: Path to the template file
            use_cache: Whether to use cached templates

        Returns:
            Loaded PromptTemplate
        """
        path = self._resolve_path(template_file)
        cache_key = str(path)

        if use_cache and cache_key in self._cache:
            return self._cache[cache_key]

        template = self._load_template(path)

        if use_cache:
            self._cache[cache_key] = template

        return template

    def clear_cache(self) -> None:
        """Clear the template cache."""
        self._cache.clear()

    def _resolve_path(self, file_path: str | Path) -> Path:
        """Resolve a template file path."""
        path = Path(file_path)
        if not path.is_absolute():
            path = self.prompts_dir / path
        return path

    def _load_template(self, path: Path) -> PromptTemplate:
        """Load a template from file."""
        if not path.exists():
            raise FileNotFoundError(f"Template file not found: {path}")

        content = path.read_text(encoding="utf-8")
        return PromptTemplate(
            name=path.stem,
            content=content,
            source_path=path,
        )
