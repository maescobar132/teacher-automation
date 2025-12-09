# Command: /create_plan
# Purpose: Generate a detailed, iterative, and verifiable implementation plan from a research document.

## 1. Goal
Transform the research findings (provided as a file in the user's prompt) into a **concrete, phased plan** ready for implementation. The plan must adhere to the project's quality standards.

## 2. Methodology
1.  **Consume Research:** Read the entire provided research document (`@thoughts/shared/research/...`).
2.  **Define Scope:** Identify the *minimum number of phases* required to complete the feature or refactoring goal. Each phase must be deliverable and independently verifiable.
3.  **Refactoring Standard:** When refactoring, prioritize **moving utility functions out of `run_activity.py`** and into the appropriate package modules (`config`, `processing`, `output`).
4.  **Error Prevention:** For each phase, consider the impact on the existing system (especially Hybrid Mode and prompt caching) and include specific steps to mitigate risk.

## 3. Output Format: Plan Document
Generate a Markdown document saved to `thoughts/shared/plans/YYYY-MM-DD_[topic].md`. **The plan must be interactive and iterative (ask for review/refinement).**

### Implementation Plan: [Feature/Refactor Name]

#### Project Context
* Reference the source research document.
* State the ultimate goal (e.g., "Decouple config loading from CLI logic").

#### Phase Breakdown (MUST be sequential)
* **Phase N: [Clear, Actionable Title]**
    * **Goal:** (1-2 sentences)
    * **Files to Modify:**
        * `src/teacher_automation/config/activity_loader.py` (CREATE)
        * `run_activity.py` (UPDATE: Remove local functions L36-82)
    * **Code Snippet/High-Level Action:** (Show the class/function signature being added or removed.)

#### Success Criteria (Verification)
* **Automated Verification:** List all unit tests and linting/type checks to run *after* each phase.
* **Manual Verification:** List specific functional tests for the human user (e.g., "Run with a DOCX file in Normal Mode to ensure extraction still works").

**Initial Review:** Please review this initial 3-phase plan. Does it miss any edge cases, or would you like to refine the scope of any phase?

---
