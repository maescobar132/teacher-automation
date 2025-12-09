"""
Moodle integration module.

Handles communication with Moodle LMS via its web services API,
including fetching assignments, downloading submissions, and uploading grades.
"""

from .api import (
    MoodleAPI,
    MoodleAPIError,
    MoodleAuthError,
    MoodleNotFoundError,
    MoodleValidationError,
    ForumPost,
    ForumDiscussion,
    create_api_client,
)
from .models import Assignment, Submission, SubmissionFile, Student

__all__ = [
    # API client
    "MoodleAPI",
    "create_api_client",
    # Exceptions
    "MoodleAPIError",
    "MoodleAuthError",
    "MoodleNotFoundError",
    "MoodleValidationError",
    # Models
    "Assignment",
    "Submission",
    "SubmissionFile",
    "Student",
    "ForumPost",
    "ForumDiscussion",
]
