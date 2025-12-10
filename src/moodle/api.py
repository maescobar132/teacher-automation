"""
Moodle REST API wrapper functions.

This module provides high-level wrapper functions for interacting with
Moodle's Web Services REST API. All functions handle authentication,
error handling, and response parsing.

Moodle Web Services Documentation:
https://docs.moodle.org/dev/Web_service_API_functions
"""

from dataclasses import dataclass
from typing import Any

import httpx

from src.utils.logging import get_logger
from .models import Assignment, Submission, SubmissionFile

logger = get_logger(__name__)


# -----------------------------------------------------------------------------
# Exceptions
# -----------------------------------------------------------------------------


class MoodleAPIError(Exception):
    """Base exception for Moodle API errors."""

    def __init__(self, message: str, error_code: str | None = None, debug_info: str | None = None):
        super().__init__(message)
        self.error_code = error_code
        self.debug_info = debug_info


class MoodleAuthError(MoodleAPIError):
    """Authentication or authorization error."""

    pass


class MoodleNotFoundError(MoodleAPIError):
    """Resource not found error."""

    pass


class MoodleValidationError(MoodleAPIError):
    """Invalid parameters or validation error."""

    pass


# -----------------------------------------------------------------------------
# Data Classes for Forum Posts
# -----------------------------------------------------------------------------


@dataclass
class ForumPost:
    """Represents a forum post or discussion."""

    id: int
    discussion_id: int
    parent_id: int
    user_id: int
    subject: str
    message: str
    created_at: int  # Unix timestamp
    modified_at: int  # Unix timestamp
    author_name: str = ""
    author_picture_url: str = ""
    attachments: list[dict[str, Any]] | None = None

    @classmethod
    def from_api_response(cls, data: dict[str, Any]) -> "ForumPost":
        """Create a ForumPost from Moodle API response data."""
        return cls(
            id=data.get("id", 0),
            discussion_id=data.get("discussion", 0),
            parent_id=data.get("parent", 0),
            user_id=data.get("userid", data.get("author", {}).get("id", 0)),
            subject=data.get("subject", ""),
            message=data.get("message", ""),
            created_at=data.get("created", data.get("timecreated", 0)),
            modified_at=data.get("modified", data.get("timemodified", 0)),
            author_name=data.get("userfullname", data.get("author", {}).get("fullname", "")),
            author_picture_url=data.get("userpictureurl", data.get("author", {}).get("urls", {}).get("image", "")),
            attachments=data.get("attachments"),
        )


@dataclass
class ForumDiscussion:
    """Represents a forum discussion thread."""

    id: int
    forum_id: int
    name: str
    user_id: int
    group_id: int
    time_start: int
    time_modified: int
    num_replies: int
    pinned: bool
    locked: bool
    first_post: ForumPost | None = None

    @classmethod
    def from_api_response(cls, data: dict[str, Any]) -> "ForumDiscussion":
        """Create a ForumDiscussion from Moodle API response data."""
        first_post = None
        if data.get("firstpost"):
            first_post = ForumPost.from_api_response(data["firstpost"])

        return cls(
            id=data.get("id", data.get("discussion", 0)),
            forum_id=data.get("forum", 0),
            name=data.get("name", data.get("subject", "")),
            user_id=data.get("userid", 0),
            group_id=data.get("groupid", 0),
            time_start=data.get("timestart", 0),
            time_modified=data.get("timemodified", 0),
            num_replies=data.get("numreplies", 0),
            pinned=data.get("pinned", False),
            locked=data.get("locked", False),
            first_post=first_post,
        )


# -----------------------------------------------------------------------------
# API Client
# -----------------------------------------------------------------------------


class MoodleAPI:
    """
    Low-level Moodle REST API client.

    Handles HTTP requests, authentication, and error handling for
    Moodle's Web Services API.

    Usage:
        api = MoodleAPI(
            base_url="https://moodle.example.edu",
            token="your_webservice_token"
        )
        submissions = api.get_submissions(assignment_id=123)
    """

    # Request timeout in seconds
    DEFAULT_TIMEOUT = 30.0

    # Moodle web service response format
    RESPONSE_FORMAT = "json"

    def __init__(
        self,
        base_url: str,
        token: str,
        timeout: float = DEFAULT_TIMEOUT,
        verify_ssl: bool = True,
    ):
        """
        Initialize the Moodle API client.

        Args:
            base_url: Base URL of the Moodle instance (e.g., https://moodle.example.edu)
            token: Web services API token (generated in Moodle admin)
            timeout: Request timeout in seconds
            verify_ssl: Whether to verify SSL certificates
        """
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout
        self.verify_ssl = verify_ssl
        self._client: httpx.Client | None = None

    @property
    def client(self) -> httpx.Client:
        """Get or create the HTTP client."""
        if self._client is None:
            self._client = httpx.Client(
                timeout=self.timeout,
                verify=self.verify_ssl,
                headers={"Accept": "application/json"},
            )
        return self._client

    def close(self) -> None:
        """Close the HTTP client."""
        if self._client is not None:
            self._client.close()
            self._client = None

    def __enter__(self) -> "MoodleAPI":
        return self

    def __exit__(self, *args) -> None:
        self.close()

    # -------------------------------------------------------------------------
    # Core API Methods
    # -------------------------------------------------------------------------

    def _call(self, wsfunction: str, **params: Any) -> Any:
        """
        Make a call to the Moodle Web Services API.

        Args:
            wsfunction: The Moodle web service function name
            **params: Function parameters

        Returns:
            Parsed JSON response data

        Raises:
            MoodleAPIError: If the API returns an error
            MoodleAuthError: If authentication fails
            httpx.HTTPError: If the HTTP request fails
        """
        endpoint = f"{self.base_url}/webservice/rest/server.php"

        # Build request parameters
        request_params = {
            "wstoken": self.token,
            "wsfunction": wsfunction,
            "moodlewsrestformat": self.RESPONSE_FORMAT,
            **self._flatten_params(params),
        }

        logger.debug(f"Calling Moodle API: {wsfunction}")

        try:
            response = self.client.post(endpoint, data=request_params)
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error calling {wsfunction}: {e}")
            raise MoodleAPIError(f"HTTP {e.response.status_code}: {e.response.text}") from e
        except httpx.RequestError as e:
            logger.error(f"Request error calling {wsfunction}: {e}")
            raise MoodleAPIError(f"Request failed: {e}") from e

        # Parse response
        data = response.json()

        # Check for Moodle-level errors
        self._check_error(data, wsfunction)

        return data

    def _flatten_params(self, params: dict[str, Any], prefix: str = "") -> dict[str, Any]:
        """
        Flatten nested parameters for Moodle's expected format.

        Moodle expects array parameters in the format:
        param[0][key] = value

        Args:
            params: Parameters to flatten
            prefix: Current parameter prefix

        Returns:
            Flattened parameter dictionary
        """
        result = {}

        for key, value in params.items():
            full_key = f"{prefix}[{key}]" if prefix else key

            if value is None:
                continue
            elif isinstance(value, dict):
                result.update(self._flatten_params(value, full_key))
            elif isinstance(value, (list, tuple)):
                for i, item in enumerate(value):
                    if isinstance(item, dict):
                        result.update(self._flatten_params(item, f"{full_key}[{i}]"))
                    else:
                        result[f"{full_key}[{i}]"] = item
            elif isinstance(value, bool):
                result[full_key] = int(value)
            else:
                result[full_key] = value

        return result

    def _check_error(self, data: Any, wsfunction: str) -> None:
        """
        Check API response for errors.

        Args:
            data: Parsed response data
            wsfunction: The function that was called

        Raises:
            MoodleAuthError: If authentication/authorization failed
            MoodleNotFoundError: If resource was not found
            MoodleValidationError: If validation failed
            MoodleAPIError: For other errors
        """
        if not isinstance(data, dict):
            return

        # Check for error response
        if "exception" in data or "errorcode" in data:
            error_code = data.get("errorcode", "unknown")
            message = data.get("message", data.get("exception", "Unknown error"))
            debug_info = data.get("debuginfo")

            logger.error(f"Moodle API error in {wsfunction}: [{error_code}] {message}")

            # Map to specific exception types
            if error_code in ("invalidtoken", "accessexception", "requireloginerror"):
                raise MoodleAuthError(message, error_code, debug_info)
            elif error_code in ("invalidrecord", "cannotfindrecord"):
                raise MoodleNotFoundError(message, error_code, debug_info)
            elif error_code in ("invalidparameter", "invalidargument"):
                raise MoodleValidationError(message, error_code, debug_info)
            else:
                raise MoodleAPIError(message, error_code, debug_info)

    # -------------------------------------------------------------------------
    # Assignment Submissions API
    # -------------------------------------------------------------------------

    def get_submissions(
        self,
        assignment_id: int,
        status: str = "",
        since: int = 0,
        before: int = 0,
    ) -> list[Submission]:
        """
        Get submissions for an assignment.

        Uses: mod_assign_get_submissions

        Args:
            assignment_id: The assignment ID
            status: Filter by status ('new', 'submitted', 'draft', '')
            since: Only return submissions modified since this timestamp
            before: Only return submissions modified before this timestamp

        Returns:
            List of Submission objects

        Raises:
            MoodleNotFoundError: If assignment doesn't exist
            MoodleAPIError: For other API errors
        """
        logger.info(f"Fetching submissions for assignment {assignment_id}")

        params: dict[str, Any] = {
            "assignmentids": [assignment_id],
        }

        if status:
            params["status"] = status
        if since:
            params["since"] = since
        if before:
            params["before"] = before

        response = self._call("mod_assign_get_submissions", **params)

        submissions = []

        # Parse response structure
        assignments = response.get("assignments", [])
        for assignment_data in assignments:
            if assignment_data.get("assignmentid") != assignment_id:
                continue

            for submission_data in assignment_data.get("submissions", []):
                # Extract submission plugins (files, online text, etc.)
                files = []
                text_content = ""

                for plugin in submission_data.get("plugins", []):
                    plugin_type = plugin.get("type", "")

                    if plugin_type == "file":
                        # Extract file submissions
                        for file_area in plugin.get("fileareas", []):
                            for file_data in file_area.get("files", []):
                                files.append(
                                    SubmissionFile(
                                        filename=file_data.get("filename", ""),
                                        url=file_data.get("fileurl", ""),
                                        mimetype=file_data.get("mimetype", ""),
                                        filesize=file_data.get("filesize", 0),
                                    )
                                )

                    elif plugin_type == "onlinetext":
                        # Extract online text submission
                        for editor_field in plugin.get("editorfields", []):
                            if editor_field.get("name") == "onlinetext":
                                text_content = editor_field.get("text", "")

                submission = Submission(
                    id=submission_data.get("id", 0),
                    assignment_id=assignment_id,
                    user_id=submission_data.get("userid", 0),
                    status=submission_data.get("status", "new"),
                    submitted_at=None,  # Will be set from timemodified
                    files=files,
                    text_content=text_content,
                )

                # Set submitted_at from timemodified if available
                if submission_data.get("timemodified"):
                    from datetime import datetime

                    submission.submitted_at = datetime.fromtimestamp(
                        submission_data["timemodified"]
                    )

                submissions.append(submission)

        logger.info(f"Found {len(submissions)} submissions for assignment {assignment_id}")
        return submissions

    def get_assignment_metadata(self, assignment_id: int) -> Assignment:
        """
        Get metadata for an assignment.

        Uses: mod_assign_get_assignments

        Args:
            assignment_id: The assignment ID

        Returns:
            Assignment object with full metadata

        Raises:
            MoodleNotFoundError: If assignment doesn't exist
            MoodleAPIError: For other API errors
        """
        logger.info(f"Fetching metadata for assignment {assignment_id}")

        # First, get assignment by searching across courses
        # We need to use a different approach - get by course or by cmid
        # For direct lookup, we'll use mod_assign_get_assignments with courseids

        # Alternative: use core_course_get_course_module to get the assignment
        # But mod_assign_get_assignments is more complete

        # We need the course ID, so let's try to get it from the assignment ID
        # using core_course_get_course_module first
        try:
            cm_response = self._call(
                "core_course_get_course_module",
                cmid=assignment_id,
            )
            course_id = cm_response.get("cm", {}).get("course", 0)
        except MoodleAPIError:
            # Try treating assignment_id as instance ID instead of cmid
            # This is a fallback - ideally the caller provides the course_id
            raise MoodleNotFoundError(
                f"Could not find assignment with ID {assignment_id}. "
                "Make sure you're using the correct ID type (cmid or instance id).",
                "invalidrecord",
            )

        # Now get full assignment details
        response = self._call(
            "mod_assign_get_assignments",
            courseids=[course_id],
        )

        # Find the specific assignment
        for course_data in response.get("courses", []):
            for assign_data in course_data.get("assignments", []):
                if assign_data.get("cmid") == assignment_id or assign_data.get("id") == assignment_id:
                    return self._parse_assignment(assign_data, course_id)

        raise MoodleNotFoundError(
            f"Assignment {assignment_id} not found",
            "cannotfindrecord",
        )

    def _parse_assignment(self, data: dict[str, Any], course_id: int) -> Assignment:
        """Parse assignment data from API response."""
        from datetime import datetime

        due_date = None
        if data.get("duedate"):
            due_date = datetime.fromtimestamp(data["duedate"])

        # Extract submission types from configs
        submission_types = []
        for config in data.get("configs", []):
            if config.get("plugin") == "file" and config.get("name") == "enabled":
                if config.get("value") == "1":
                    submission_types.append("file")
            elif config.get("plugin") == "onlinetext" and config.get("name") == "enabled":
                if config.get("value") == "1":
                    submission_types.append("onlinetext")

        return Assignment(
            id=data.get("cmid", data.get("id", 0)),
            name=data.get("name", ""),
            course_id=course_id,
            description=data.get("intro", ""),
            due_date=due_date,
            max_grade=float(data.get("grade", 100)),
            submission_types=submission_types,
        )

    # -------------------------------------------------------------------------
    # Grading API
    # -------------------------------------------------------------------------

    def upload_grade(
        self,
        assignment_id: int,
        user_id: int,
        grade: float,
        feedback_html: str = "",
        attempt_number: int = -1,
        apply_to_all: bool = False,
        feedback_format: int = 1,  # 1 = HTML format
    ) -> bool:
        """
        Upload a grade for a student's submission.

        Uses: mod_assign_save_grade

        Args:
            assignment_id: The assignment ID (cmid or instance id)
            user_id: The student's user ID
            grade: The numeric grade (must be within assignment's grade range)
            feedback_html: HTML-formatted feedback text
            attempt_number: Attempt number (-1 for latest attempt)
            apply_to_all: Apply grade to all team members (for group assignments)
            feedback_format: Format of feedback (1=HTML, 0=plain text)

        Returns:
            True if grade was saved successfully

        Raises:
            MoodleValidationError: If grade is invalid
            MoodleNotFoundError: If assignment or user not found
            MoodleAPIError: For other API errors
        """
        logger.info(f"Uploading grade {grade} for user {user_id} on assignment {assignment_id}")

        # Build grade data structure
        # Moodle expects specific plugin data structure
        plugin_data = {
            "assignfeedback_comments_editor": {
                "text": feedback_html,
                "format": feedback_format,
            }
        }

        try:
            self._call(
                "mod_assign_save_grade",
                assignmentid=assignment_id,
                userid=user_id,
                grade=grade,
                attemptnumber=attempt_number,
                addattempt=0,  # Don't add new attempt
                workflowstate="",  # Use default workflow
                applytoall=int(apply_to_all),
                plugindata=plugin_data,
            )

            logger.info(f"Successfully saved grade for user {user_id}")
            return True

        except MoodleAPIError as e:
            logger.error(f"Failed to save grade: {e}")
            raise

    def upload_grades_batch(
        self,
        assignment_id: int,
        grades: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """
        Upload multiple grades in a single request.

        Uses: mod_assign_save_grades

        Args:
            assignment_id: The assignment ID
            grades: List of grade dictionaries with keys:
                - userid: Student user ID
                - grade: Numeric grade
                - feedbacktext: HTML feedback (optional)
                - feedbackformat: Format (1=HTML, default)

        Returns:
            Dict with success status and any warnings

        Raises:
            MoodleAPIError: For API errors
        """
        logger.info(f"Uploading batch of {len(grades)} grades for assignment {assignment_id}")

        # Format grades for API
        formatted_grades = []
        for g in grades:
            grade_entry = {
                "userid": g["userid"],
                "grade": g["grade"],
                "attemptnumber": g.get("attemptnumber", -1),
                "addattempt": 0,
                "workflowstate": "",
                "plugindata": {
                    "assignfeedback_comments_editor": {
                        "text": g.get("feedbacktext", ""),
                        "format": g.get("feedbackformat", 1),
                    }
                },
            }
            formatted_grades.append(grade_entry)

        response = self._call(
            "mod_assign_save_grades",
            assignmentid=assignment_id,
            applytoall=0,
            grades=formatted_grades,
        )

        logger.info(f"Batch grade upload complete")
        return response or {"success": True}

    # -------------------------------------------------------------------------
    # Forum API
    # -------------------------------------------------------------------------

    def get_forum_posts(
        self,
        forum_id: int,
        include_replies: bool = True,
        sort_by: str = "created",
        sort_direction: str = "DESC",
    ) -> list[ForumDiscussion]:
        """
        Get all discussions and posts from a forum.

        Uses: mod_forum_get_forum_discussions + mod_forum_get_discussion_posts

        Args:
            forum_id: The forum ID (cmid)
            include_replies: Whether to fetch replies for each discussion
            sort_by: Sort field ('created', 'modified', 'replies')
            sort_direction: Sort direction ('ASC' or 'DESC')

        Returns:
            List of ForumDiscussion objects with posts

        Raises:
            MoodleNotFoundError: If forum doesn't exist
            MoodleAPIError: For other API errors
        """
        logger.info(f"Fetching posts from forum {forum_id}")

        # Map sort options to Moodle's expected values
        sort_map = {
            "created": 1,  # Sort by created date
            "modified": 2,  # Sort by modified date
            "replies": 3,  # Sort by number of replies
        }
        sortby = sort_map.get(sort_by, 1)
        sortdirection = sort_direction.upper()

        # Get all discussions in the forum
        discussions_response = self._call(
            "mod_forum_get_forum_discussions",
            forumid=forum_id,
            sortby=sortby,
            sortdirection=sortdirection,
            page=0,
            perpage=0,  # 0 = all
        )

        discussions = []

        for disc_data in discussions_response.get("discussions", []):
            discussion = ForumDiscussion.from_api_response(disc_data)
            discussion.forum_id = forum_id

            discussions.append(discussion)

        logger.info(f"Found {len(discussions)} discussions in forum {forum_id}")

        # Optionally fetch all posts for each discussion
        if include_replies:
            for discussion in discussions:
                posts = self._get_discussion_posts(discussion.id)
                # First post is already in the discussion, add replies
                if posts and discussion.first_post is None:
                    discussion.first_post = posts[0] if posts else None

        return discussions

    def _get_discussion_posts(self, discussion_id: int) -> list[ForumPost]:
        """
        Get all posts in a discussion.

        Uses: mod_forum_get_discussion_posts

        Args:
            discussion_id: The discussion ID

        Returns:
            List of ForumPost objects
        """
        response = self._call(
            "mod_forum_get_discussion_posts",
            discussionid=discussion_id,
            sortby="created",
            sortdirection="ASC",
        )

        posts = []
        for post_data in response.get("posts", []):
            posts.append(ForumPost.from_api_response(post_data))

        return posts

    def get_forum_discussions_by_user(
        self,
        forum_id: int,
        user_id: int,
    ) -> list[ForumDiscussion]:
        """
        Get all discussions started by a specific user.

        Args:
            forum_id: The forum ID
            user_id: The user ID

        Returns:
            List of discussions started by the user
        """
        all_discussions = self.get_forum_posts(forum_id, include_replies=False)
        return [d for d in all_discussions if d.user_id == user_id]

    def get_user_forum_posts(
        self,
        forum_id: int,
        user_id: int,
    ) -> list[ForumPost]:
        """
        Get all posts by a specific user in a forum.

        Args:
            forum_id: The forum ID
            user_id: The user ID

        Returns:
            List of posts by the user
        """
        logger.info(f"Fetching posts by user {user_id} in forum {forum_id}")

        discussions = self.get_forum_posts(forum_id, include_replies=True)

        user_posts = []
        for discussion in discussions:
            # Check if user started the discussion
            if discussion.first_post and discussion.first_post.user_id == user_id:
                user_posts.append(discussion.first_post)

            # Get all replies and filter by user
            replies = self._get_discussion_posts(discussion.id)
            for post in replies:
                if post.user_id == user_id and post.id != (discussion.first_post.id if discussion.first_post else 0):
                    user_posts.append(post)

        logger.info(f"Found {len(user_posts)} posts by user {user_id}")
        return user_posts


# -----------------------------------------------------------------------------
# Convenience Functions
# -----------------------------------------------------------------------------


def create_api_client(
    base_url: str,
    token: str | None = None,
    token_env_var: str = "MOODLE_TOKEN",
) -> MoodleAPI:
    """
    Create a MoodleAPI client with token from environment if not provided.

    Args:
        base_url: Moodle instance URL
        token: API token (uses env var if not provided)
        token_env_var: Environment variable name for token

    Returns:
        Configured MoodleAPI instance

    Raises:
        ValueError: If no token is available
    """
    import os

    if token is None:
        token = os.environ.get(token_env_var)

    if not token:
        raise ValueError(
            f"Moodle API token required. Provide token parameter or set {token_env_var} environment variable."
        )

    return MoodleAPI(base_url=base_url, token=token)
