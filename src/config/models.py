"""Configuration data models."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class MoodleSettings:
    """Moodle LMS connection settings."""

    url: str
    token: str | None = None
    course_id: int | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MoodleSettings":
        return cls(
            url=data["url"],
            token=data.get("token"),
            course_id=data.get("course_id"),
        )


@dataclass
class TurnitinSettings:
    """Turnitin integration settings."""

    enabled: bool = False
    api_key: str | None = None
    api_url: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TurnitinSettings":
        return cls(
            enabled=data.get("enabled", False),
            api_key=data.get("api_key"),
            api_url=data.get("api_url"),
        )


@dataclass
class AssignmentConfig:
    """Configuration for a single assignment."""

    name: str
    moodle_id: int | None = None
    rubric_file: str | None = None
    prompt_template: str | None = None
    max_points: float = 100.0
    due_date: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AssignmentConfig":
        return cls(
            name=data["name"],
            moodle_id=data.get("moodle_id"),
            rubric_file=data.get("rubric_file"),
            prompt_template=data.get("prompt_template"),
            max_points=data.get("max_points", 100.0),
            due_date=data.get("due_date"),
        )


@dataclass
class CourseConfig:
    """Complete course configuration."""

    name: str
    code: str
    semester: str
    moodle: MoodleSettings
    turnitin: TurnitinSettings = field(default_factory=lambda: TurnitinSettings())
    assignments: list[AssignmentConfig] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CourseConfig":
        moodle = MoodleSettings.from_dict(data.get("moodle", {}))
        turnitin = TurnitinSettings.from_dict(data.get("turnitin", {}))
        assignments = [
            AssignmentConfig.from_dict(a) for a in data.get("assignments", [])
        ]

        return cls(
            name=data["name"],
            code=data["code"],
            semester=data["semester"],
            moodle=moodle,
            turnitin=turnitin,
            assignments=assignments,
        )


@dataclass
class GradingConfig:
    """Grading system configuration."""

    model: str = "gpt-4"
    temperature: float = 0.3
    max_tokens: int = 2000
    feedback_language: str = "en"
    include_rubric_breakdown: bool = True

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GradingConfig":
        return cls(
            model=data.get("model", "gpt-4"),
            temperature=data.get("temperature", 0.3),
            max_tokens=data.get("max_tokens", 2000),
            feedback_language=data.get("feedback_language", "en"),
            include_rubric_breakdown=data.get("include_rubric_breakdown", True),
        )
