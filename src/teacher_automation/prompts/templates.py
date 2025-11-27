"""Prompt template classes."""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class PromptTemplate:
    """A template for generating AI prompts."""

    name: str
    content: str
    source_path: Path | None = None
    _variables: set[str] = field(default_factory=set, init=False, repr=False)

    def __post_init__(self):
        """Extract variables from template content."""
        self._variables = set(re.findall(r"\{(\w+)\}", self.content))

    @property
    def variables(self) -> set[str]:
        """Get the set of variables in this template."""
        return self._variables.copy()

    def render(self, **kwargs: Any) -> str:
        """Render the template with provided variables.

        Args:
            **kwargs: Variable values to substitute

        Returns:
            Rendered prompt string

        Raises:
            ValueError: If required variables are missing
        """
        missing = self._variables - set(kwargs.keys())
        if missing:
            raise ValueError(f"Missing required variables: {missing}")

        result = self.content
        for key, value in kwargs.items():
            if key in self._variables:
                result = result.replace(f"{{{key}}}", str(value))

        return result

    def render_partial(self, **kwargs: Any) -> str:
        """Render the template, leaving unfilled variables as-is.

        Args:
            **kwargs: Variable values to substitute

        Returns:
            Partially rendered prompt string
        """
        result = self.content
        for key, value in kwargs.items():
            if key in self._variables:
                result = result.replace(f"{{{key}}}", str(value))

        return result

    def with_prefix(self, prefix: str) -> "PromptTemplate":
        """Create a new template with a prefix added.

        Args:
            prefix: Text to prepend to the template

        Returns:
            New PromptTemplate with prefix
        """
        return PromptTemplate(
            name=self.name,
            content=prefix + self.content,
            source_path=self.source_path,
        )

    def with_suffix(self, suffix: str) -> "PromptTemplate":
        """Create a new template with a suffix added.

        Args:
            suffix: Text to append to the template

        Returns:
            New PromptTemplate with suffix
        """
        return PromptTemplate(
            name=self.name,
            content=self.content + suffix,
            source_path=self.source_path,
        )
