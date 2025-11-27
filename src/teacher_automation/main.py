#!/usr/bin/env python3
"""
Teacher Automation Pipeline

Main entry point for the grading automation system.
This script orchestrates the complete workflow from fetching submissions
to uploading grades back to Moodle.
"""

import argparse
import logging
import sys
from pathlib import Path

from .config.loader import ConfigLoader
from .config.models import CourseConfig
from .grading.grader import Grader, GradeResult
from .grading.feedback import FeedbackGenerator
from .moodle.client import MoodleClient
from .moodle.models import Submission
from .processing.extractor import SubmissionExtractor
from .processing.parser import DocumentParser
from .prompts.loader import PromptLoader
from .rubrics.loader import RubricLoader
from .turnitin.client import TurnitinClient
from .utils.logging import setup_logging, get_logger

logger = get_logger(__name__)


class GradingPipeline:
    """Orchestrates the complete grading workflow."""

    def __init__(
        self,
        course_config: CourseConfig,
        work_dir: Path,
        dry_run: bool = False,
    ):
        """Initialize the grading pipeline.

        Args:
            course_config: Course configuration
            work_dir: Working directory for temporary files
            dry_run: If True, don't upload grades to Moodle
        """
        self.config = course_config
        self.work_dir = work_dir
        self.dry_run = dry_run

        # Initialize components
        self.moodle = MoodleClient(
            url=course_config.moodle.url,
            token=course_config.moodle.token or "",
        )
        self.extractor = SubmissionExtractor(work_dir / "submissions")
        self.parser = DocumentParser()
        self.rubric_loader = RubricLoader()
        self.prompt_loader = PromptLoader()
        self.grader = Grader()
        self.feedback_gen = FeedbackGenerator()

        # Optional Turnitin client
        self.turnitin = None
        if course_config.turnitin.enabled and course_config.turnitin.api_key:
            self.turnitin = TurnitinClient(
                api_key=course_config.turnitin.api_key,
                api_url=course_config.turnitin.api_url,
            )

    def run(self, assignment_name: str | None = None) -> dict[str, list[GradeResult]]:
        """Run the grading pipeline.

        Args:
            assignment_name: Optional name of specific assignment to grade

        Returns:
            Dict mapping assignment names to lists of GradeResults
        """
        logger.info(f"Starting grading pipeline for course: {self.config.name}")
        results: dict[str, list[GradeResult]] = {}

        # Filter assignments if specific one requested
        assignments = self.config.assignments
        if assignment_name:
            assignments = [a for a in assignments if a.name == assignment_name]
            if not assignments:
                logger.error(f"Assignment not found: {assignment_name}")
                return results

        for assignment in assignments:
            logger.info(f"Processing assignment: {assignment.name}")
            assignment_results = self._process_assignment(assignment)
            results[assignment.name] = assignment_results

        logger.info("Grading pipeline complete")
        return results

    def _process_assignment(self, assignment) -> list[GradeResult]:
        """Process a single assignment.

        Args:
            assignment: Assignment configuration

        Returns:
            List of GradeResults for this assignment
        """
        results = []

        # Load rubric and prompt template
        rubric = None
        if assignment.rubric_file:
            try:
                rubric = self.rubric_loader.load(assignment.rubric_file)
            except FileNotFoundError:
                logger.warning(f"Rubric not found: {assignment.rubric_file}")

        prompt_template = None
        if assignment.prompt_template:
            try:
                prompt_template = self.prompt_loader.load(assignment.prompt_template)
            except FileNotFoundError:
                logger.warning(f"Prompt template not found: {assignment.prompt_template}")

        if not rubric or not prompt_template:
            logger.error("Cannot grade without rubric and prompt template")
            return results

        # Fetch submissions from Moodle
        if assignment.moodle_id:
            submissions = self.moodle.get_submissions(assignment.moodle_id)
        else:
            logger.warning("No Moodle ID configured, skipping fetch")
            submissions = []

        # Process each submission
        for submission in submissions:
            result = self._grade_submission(
                submission=submission,
                assignment=assignment,
                rubric=rubric,
                prompt_template=prompt_template,
            )
            if result:
                results.append(result)

                # Upload grade if not in dry run mode
                if not self.dry_run:
                    self._upload_grade(submission, result, assignment.moodle_id)

        return results

    def _grade_submission(
        self,
        submission: Submission,
        assignment,
        rubric,
        prompt_template,
    ) -> GradeResult | None:
        """Grade a single submission.

        Args:
            submission: The submission to grade
            assignment: Assignment configuration
            rubric: Grading rubric
            prompt_template: Prompt template for AI grading

        Returns:
            GradeResult or None if grading failed
        """
        logger.info(f"Grading submission {submission.id} from user {submission.user_id}")

        try:
            # Get submission content
            if submission.text_content:
                content = submission.text_content
            elif submission.files:
                # Download and parse first file
                file_path = self.moodle.download_submission(
                    submission,
                    self.work_dir / "downloads",
                )
                content = self.parser.parse(file_path)
            else:
                logger.warning(f"No content in submission {submission.id}")
                return None

            # Check plagiarism if Turnitin is configured
            if self.turnitin:
                self._check_plagiarism(submission, content)

            # Grade the submission
            result = self.grader.grade(
                submission_content=content,
                rubric=rubric,
                prompt_template=prompt_template,
                assignment_name=assignment.name,
                language="python",  # Default, should be configurable
            )

            return result

        except Exception as e:
            logger.error(f"Error grading submission {submission.id}: {e}")
            return None

    def _check_plagiarism(self, submission: Submission, content: str) -> None:
        """Submit content for plagiarism checking.

        Args:
            submission: The submission being checked
            content: Text content to check
        """
        if not self.turnitin:
            return

        # Write content to temp file for submission
        temp_file = self.work_dir / "temp" / f"submission_{submission.id}.txt"
        temp_file.parent.mkdir(parents=True, exist_ok=True)
        temp_file.write_text(content)

        try:
            submission_id = self.turnitin.submit_document(
                file_path=temp_file,
                title=f"Submission {submission.id}",
                author_name=f"User {submission.user_id}",
            )
            logger.info(f"Submitted to Turnitin: {submission_id}")
        finally:
            temp_file.unlink(missing_ok=True)

    def _upload_grade(
        self,
        submission: Submission,
        result: GradeResult,
        assignment_id: int | None,
    ) -> None:
        """Upload a grade to Moodle.

        Args:
            submission: The graded submission
            result: Grading result
            assignment_id: Moodle assignment ID
        """
        if not assignment_id:
            return

        # Format feedback for Moodle
        feedback_html = self.feedback_gen.format_for_moodle(
            feedback=result.feedback,
            score=result.total_score,
            max_score=result.max_score,
        )

        success = self.moodle.upload_grade(
            assignment_id=assignment_id,
            user_id=submission.user_id,
            grade=result.total_score,
            feedback=feedback_html,
        )

        if success:
            logger.info(f"Uploaded grade for submission {submission.id}")
        else:
            logger.error(f"Failed to upload grade for submission {submission.id}")


def main():
    """Main entry point for the CLI."""
    parser = argparse.ArgumentParser(
        description="Teacher Automation Grading Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Grade all assignments in a course
  python -m teacher_automation.main --config course.yaml

  # Grade a specific assignment
  python -m teacher_automation.main --config course.yaml --assignment "Assignment 1"

  # Dry run (don't upload grades)
  python -m teacher_automation.main --config course.yaml --dry-run

  # Verbose output
  python -m teacher_automation.main --config course.yaml -v
        """,
    )

    parser.add_argument(
        "--config",
        "-c",
        type=Path,
        required=True,
        help="Path to course configuration YAML file",
    )
    parser.add_argument(
        "--assignment",
        "-a",
        type=str,
        help="Name of specific assignment to grade (grades all if not specified)",
    )
    parser.add_argument(
        "--work-dir",
        "-w",
        type=Path,
        default=Path("./work"),
        help="Working directory for temporary files (default: ./work)",
    )
    parser.add_argument(
        "--dry-run",
        "-n",
        action="store_true",
        help="Run without uploading grades to Moodle",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging",
    )
    parser.add_argument(
        "--log-file",
        type=Path,
        help="Path to log file (logs to console only if not specified)",
    )

    args = parser.parse_args()

    # Setup logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    setup_logging(level=log_level, log_file=args.log_file)

    # Load configuration
    try:
        config_loader = ConfigLoader()
        course_config = config_loader.load_course(args.config)
    except FileNotFoundError:
        logger.error(f"Configuration file not found: {args.config}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error loading configuration: {e}")
        sys.exit(1)

    # Create and run pipeline
    pipeline = GradingPipeline(
        course_config=course_config,
        work_dir=args.work_dir,
        dry_run=args.dry_run,
    )

    try:
        results = pipeline.run(assignment_name=args.assignment)

        # Print summary
        total_graded = sum(len(r) for r in results.values())
        logger.info(f"Graded {total_graded} submissions across {len(results)} assignments")

        for assignment_name, assignment_results in results.items():
            if assignment_results:
                avg_score = sum(r.percentage for r in assignment_results) / len(assignment_results)
                logger.info(f"  {assignment_name}: {len(assignment_results)} submissions, avg: {avg_score:.1f}%")

    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.error(f"Pipeline error: {e}")
        if args.verbose:
            raise
        sys.exit(1)


if __name__ == "__main__":
    main()
