# Command: /validate_plan
# Purpose: Perform a comprehensive, systematic review of the implementation against the original plan.

## 1. Goal
Verify that all changes required by the provided plan document are correctly implemented, all success criteria are met, and no unrelated functionality (like Hybrid Mode or caching) was damaged.

## 2. Methodology
1.  **Consume Plan:** Read the entire provided plan document (`@thoughts/shared/plans/...`).
2.  **Review Changes:** Systematically review the current state of the code against the "Code Snippet/High-Level Action" for *every phase* in the plan.
3.  **Run All Checks:** Execute *all* automated verification steps listed in the plan (not just for one phase).
4.  **Impact Assessment:** Specifically check the refactored `run_activity.py` to ensure it only uses the newly created/imported functions and that all local utility functions marked for removal are gone.

## 3. Output Format: Validation Report
Generate a Markdown report summarizing the stability and completeness of the feature/refactor.

### Validation Report: [Feature/Refactor Name]

#### Plan Completion Status
* **Total Phases:** [N]
* **Phases Completed:** [N]

#### Automated Verification Results
* **Overall Unit Tests:** [PASS/FAIL]
* **Linting/Type Check:** [CLEAN/ERRORS]

#### Code Review Findings
* **Deviations Found:** [List any instances where the code does not perfectly match the plan, or state "None."]
* **Key Successes:** [List 1-2 major architectural improvements achieved, e.g., "Config loading is fully decoupled."]

#### Final Manual Checklist
* **Review Remaining Items from Plan:**
    * [ ] [Manual Check 1 from plan]
    * [ ] [Manual Check 2 from plan]

**Final Recommendation:** The codebase appears [STABLE/NEEDS FIXES]. Please run the final manual checklist and provide feedback.

---
