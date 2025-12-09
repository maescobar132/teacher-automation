# Command: /research_codebase
# Purpose: Deep architectural analysis before starting a new feature or major refactor.

## 1. Goal
The primary goal is to **understand the current implementation's structure, identify all relevant files, and pinpoint all dependencies** related to the research topic.

## 2. Methodology
1.  **Analyze Context & User Query:** Determine the goal (e.g., "Implement new reporting format," "Refactor grading loop").
2.  **Codebase Search:** Use the project context to locate all files that implement or interact with the functionality described in the user query.
3.  **Dependency Mapping:** Trace the execution path starting from `run_activity.py` through any relevant modules (`processing`, `grading`, `output`) to the functions involved.
4.  **Style/Standard Check:** Note any recurring style deviations (e.g., lack of typing, inconsistent docstrings) in the relevant files.
5.  **Documentation Search:** Search the `thoughts/shared/research` directory for any prior work or decisions that might impact the new feature.

## 3. Output Format: Research Document
Generate a comprehensive, neutral Markdown document saved to `thoughts/shared/research/YYYY-MM-DD_[topic].md` with the following sections. **Do NOT write any code or plan implementation.**

### Research Findings: [Feature/Topic Name]

#### Summary of Current Architecture
* A 2-3 sentence overview of how the functionality currently works, citing the core modules involved.

#### Relevant Code References
* A list of all files and key line numbers involved. This is crucial for the Planning phase.
    * `src/teacher_automation/grading/api.py:L142`: Function responsible for Claude API call.
    * `run_activity.py:L500-550`: The main execution loop for the feature.

#### Identified Constraints & Assumptions
* List any hardcoded values, foreign-language dependencies (Spanish content), or implicit assumptions (e.g., "Assumes all rubric files are JSON, not YAML").

#### Open Questions (Needs User Input)
* List any ambiguities that must be clarified before planning can begin.
* *Example: "Should the new feature support Hybrid Mode?"*

---
