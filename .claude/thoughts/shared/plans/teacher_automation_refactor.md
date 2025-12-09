Project Purpose

 teacher-automation is a grading automation system for doctoral education programs (specifically designed for Colombian doctoral students). It
 automates:

 1. Student Submission Processing: Extracts text from PDF/DOCX/DOC files
 2. AI-Powered Feedback Generation: Uses Claude API to evaluate student work against rubrics
 3. Formative Feedback: Generates constructive, personalized feedback in Spanish
 4. Two Operating Modes:
   - Normal Mode: Batch processing with prompt caching for cost efficiency
   - Hybrid Mode: AI evaluation + manual review for format-based criteria (portada, referencias, APA formatting)
 5. PDF Output: Generates student-facing PDF feedback documents

 Workflow

 Input: Student submissions (ZIP or directory of PDFs/DOCX)
   ↓
 Config: Load course YAML → Find activity → Get rubric + prompt
   ↓
 Extract: Pull text from each document
   ↓
 Evaluate: Claude API grades against rubric criteria
   ↓
 Output: JSON feedback files + PDF reports

 Key Configuration Files

 - Course YAML (src/teacher_automation/config/courses/FI08.yml): Defines units, activities, rubrics, prompts
 - Rubrics (config/rubrics/*.json): Grading criteria with performance levels
 - Prompts (config/prompts/*.txt): AI instructions for feedback generation

 ---
 Current State of run_activity.py

 The 926-line script is the sole entry point for the grading pipeline. It works correctly but:
 - Reimplements functionality that exists in package modules
 - Has local utility functions that should be in the package
 - Doesn't leverage the structured classes available

 What works well (keep as-is):
 - generate_feedback_batch and generate_feedback_for_text from grading module
 - clean_and_rename_files from processing module
 - manual_review functions for hybrid mode
 - PDF generation from output module
 - JSON rubric loading (RubricLoader expects YAML, rubrics are JSON)

 What should be refactored:
 - Local config loading functions → Use package loaders
 - Local text extraction fallback → Use package's extract_text
 - Local file discovery → Move to package module

 ---
 Refactoring Steps

 Step 1: Create ActivityConfigLoader for course/activity configuration

 Current (lines 36-82): Two local functions for config loading
 def load_course_config(course_id: str) -> dict:
     # Loads YAML from src/teacher_automation/config/courses/{course_id}.yml

 def find_activity(config: dict, unit_num: int, activity_id: str) -> dict | None:
     # Searches unidades[].actividades[] for matching activity

 Create: src/teacher_automation/config/activity_loader.py
 from dataclasses import dataclass
 from pathlib import Path
 from typing import Optional
 import yaml

 @dataclass
 class ActivityConfig:
     """Configuration for a single activity from course YAML."""
     id: str
     titulo: str
     tipo: str  # 'escrito' or 'foro'
     extraer_texto: bool
     rubrica: Path
     prompt: Path
     instrucciones: str

 class ActivityConfigLoader:
     """Loads course configurations with the unidades/actividades structure."""

     def __init__(self, config_dir: Path | None = None):
         self.config_dir = config_dir or (
             Path(__file__).parent / "courses"
         )

     def load_course(self, course_id: str) -> dict:
         """Load course YAML by ID (e.g., 'FI08')."""
         path = self.config_dir / f"{course_id}.yml"
         if not path.exists():
             raise FileNotFoundError(f"Course config not found: {path}")
         with open(path, encoding="utf-8") as f:
             return yaml.safe_load(f)

     def find_activity(
         self,
         config: dict,
         unit: int,
         activity_id: str
     ) -> Optional[ActivityConfig]:
         """Find activity by unit number and activity ID."""
         for unidad in config.get("unidades", []):
             if unidad.get("unidad") == unit:
                 for act in unidad.get("actividades", []):
                     if act.get("id") == activity_id:
                         return ActivityConfig(
                             id=act["id"],
                             titulo=act.get("titulo", ""),
                             tipo=act.get("tipo", "escrito"),
                             extraer_texto=act.get("extraer_texto", False),
                             rubrica=Path(act.get("rubrica", "")),
                             prompt=Path(act.get("prompt", "")),
                             instrucciones=act.get("instrucciones", ""),
                         )
         return None

 Update: src/teacher_automation/config/__init__.py to export new class

 ---
 Step 2: Create submissions.py for file discovery utilities

 Current (lines 85-128): Local functions for finding submission files
 def get_submission_files(directory: Path) -> list[Path]:
     # Finds PDF/DOCX/DOC, deduplicates by stem with priority

 def extract_student_name_from_file(file_path: Path) -> str:
     return file_path.stem  # Simple wrapper

 Create: src/teacher_automation/processing/submissions.py
 from pathlib import Path

 SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".doc"}
 EXTENSION_PRIORITY = {".pdf": 0, ".docx": 1, ".doc": 2}

 def get_submission_files(directory: Path) -> list[Path]:
     """
     Get submission files from directory, deduplicated by stem.

     If multiple files have same stem (e.g., student.pdf and student.docx),
     prefers PDF > DOCX > DOC.
     """
     files = []
     for ext in SUPPORTED_EXTENSIONS:
         files.extend(directory.glob(f"*{ext}"))
         files.extend(directory.glob(f"*{ext.upper()}"))

     # Deduplicate by stem, keeping highest priority extension
     seen_stems = {}
     for f in files:
         stem = f.stem
         ext_lower = f.suffix.lower()
         priority = EXTENSION_PRIORITY.get(ext_lower, 99)
         if stem not in seen_stems or priority < seen_stems[stem][1]:
             seen_stems[stem] = (f, priority)

     return sorted([f for f, _ in seen_stems.values()])

 def get_student_name(file_path: Path) -> str:
     """Extract student name from filename (uses stem)."""
     return file_path.stem

 Update: src/teacher_automation/processing/__init__.py to export new functions

 ---
 Step 3: Remove read_raw_text() - use extract_text() instead

 Current (lines 147-165): Manual encoding detection fallback
 def read_raw_text(file_path: Path) -> str:
     encodings = ["utf-8", "utf-8-sig", "latin-1", "cp1252"]
     for encoding in encodings:
         try:
             return file_path.read_text(encoding=encoding)
         except UnicodeDecodeError:
             continue
     return file_path.read_text(encoding="utf-8", errors="replace")

 Action: Delete function. The package's extract_text() already handles:
 - Encoding detection with chardet
 - BOM detection (utf-8-sig, utf-16, etc.)
 - Fallback to error-replacing read

 Replace in run_activity.py (lines 563-566):
 # Before:
 if extraer_texto:
     student_text = extract_text_from_file(file_path)
 else:
     student_text = read_raw_text(file_path)

 # After:
 student_text = extract_text_from_file(file_path)

 ---
 Step 4: Simplify extract_text_from_file() wrapper

 Current (lines 131-144): Thin wrapper that just returns .text
 def extract_text_from_file(file_path: Path) -> str:
     from src.teacher_automation.processing.parser import extract_text
     result = extract_text(file_path)
     return result.text

 Keep as-is - This is a reasonable simplification wrapper.

 ---
 Step 5: Keep load_rubric() and load_prompt() as-is

 Rationale:
 - load_rubric(): Rubrics are JSON, RubricLoader expects YAML. Converting would be disruptive.
 - load_prompt(): Single-line function, PromptLoader adds complexity without benefit.

 ---
 Files Changed Summary

 | File                                             | Action                      |
 |--------------------------------------------------|-----------------------------|
 | src/teacher_automation/config/activity_loader.py | CREATE                      |
 | src/teacher_automation/config/__init__.py        | UPDATE exports              |
 | src/teacher_automation/processing/submissions.py | CREATE                      |
 | src/teacher_automation/processing/__init__.py    | UPDATE exports              |
 | run_activity.py                                  | Refactor to use new modules |

 ---
 Expected Outcome

 After refactoring:
 - ~50 lines removed from run_activity.py (local utility functions moved to package)
 - 2 new reusable modules in the package
 - Better separation of concerns: CLI logic vs. business logic
 - Improved testability: New modules can be unit tested independently
 - No breaking changes: Same CLI interface, same output format

 Execution Order

 1. Create activity_loader.py - New module for config loading
 2. Create submissions.py - New module for file discovery
 3. Update __init__.py files - Export new classes/functions
 4. Refactor run_activity.py - Replace local functions with imports
 5. Remove dead code - Delete read_raw_text(), unused imports
 6. Test - Run python run_activity.py --help and process a test submission


---
Step 6: Integrate Table Extraction for DOCX and PDF

Overview:
Add robust table extraction utility to support grading based on structured data within student submissions. This functionality requires external dependencies (python-docx, tabula-py, pandas).

Changes Required:
1. UPDATE src/teacher_automation/processing/submissions.py: Add the following functions:
    - _get_table_data_docx
    - _extract_from_docx
    - _extract_from_pdf
    - extract_tables_from_submission (The main router function)

2. UPDATE run_activity.py: Import extract_tables_from_submission and modify the main processing loop to call this function and log the number of tables found (for initial debug).

Code Snippet/High-Level Action:
The implementation must use the provided Python code snippets for table extraction via python-docx and tabula-py.

Success Criteria:
Automated Verification:
- [ ] Unit tests pass (if any table extraction tests exist).
- [ ] No linting errors.
Manual Verification:
- [ ] Process a test DOCX file with 2 tables; verify the log shows 2 DataFrames extracted.
- [ ] Process a test PDF file with 1 table; verify the log shows 1 DataFrame extracted.
