"""Moodle data models."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class Student:
    """Represents a student enrolled in a Moodle course."""

    id: int
    username: str
    email: str
    first_name: str = ""
    last_name: str = ""

    @property
    def full_name(self) -> str:
        """Get the student's full name."""
        return f"{self.first_name} {self.last_name}".strip() or self.username

    @classmethod
    def from_api_response(cls, data: dict[str, Any]) -> "Student":
        """Create a Student from Moodle API response data."""
        return cls(
            id=data["id"],
            username=data.get("username", ""),
            email=data.get("email", ""),
            first_name=data.get("firstname", ""),
            last_name=data.get("lastname", ""),
        )


@dataclass
class Assignment:
    """Represents a Moodle assignment."""

    id: int
    name: str
    course_id: int
    description: str = ""
    due_date: datetime | None = None
    max_grade: float = 100.0
    submission_types: list[str] = field(default_factory=list)

    @classmethod
    def from_api_response(cls, data: dict[str, Any]) -> "Assignment":
        """Create an Assignment from Moodle API response data."""
        due_date = None
        if data.get("duedate"):
            due_date = datetime.fromtimestamp(data["duedate"])

        return cls(
            id=data["id"],
            name=data.get("name", ""),
            course_id=data.get("course", 0),
            description=data.get("intro", ""),
            due_date=due_date,
            max_grade=data.get("grade", 100.0),
        )


@dataclass
class SubmissionFile:
    """Represents a file attached to a submission."""

    filename: str
    url: str
    mimetype: str = ""
    filesize: int = 0


@dataclass
class Submission:
    """Represents a student's submission to an assignment."""

    id: int
    assignment_id: int
    user_id: int
    status: str = "new"
    submitted_at: datetime | None = None
    files: list[SubmissionFile] = field(default_factory=list)
    text_content: str = ""
    grade: float | None = None
    feedback: str = ""

    @property
    def is_graded(self) -> bool:
        """Check if this submission has been graded."""
        return self.grade is not None

    @classmethod
    def from_api_response(cls, data: dict[str, Any]) -> "Submission":
        """Create a Submission from Moodle API response data."""
        submitted_at = None
        if data.get("timemodified"):
            submitted_at = datetime.fromtimestamp(data["timemodified"])

        files = [
            SubmissionFile(
                filename=f.get("filename", ""),
                url=f.get("fileurl", ""),
                mimetype=f.get("mimetype", ""),
                filesize=f.get("filesize", 0),
            )
            for f in data.get("files", [])
        ]

        return cls(
            id=data["id"],
            assignment_id=data.get("assignment", 0),
            user_id=data.get("userid", 0),
            status=data.get("status", "new"),
            submitted_at=submitted_at,
            files=files,
            text_content=data.get("onlinetext", ""),
        )
