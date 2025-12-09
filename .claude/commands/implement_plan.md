# Command: /implement_plan
# Purpose: Execute a single phase of a plan and run automated verification immediately.

## 1. Goal
Execute the actions defined in the specified phase of the provided plan (file reference). **DO NOT proceed to the next phase until the user confirms success.**

## 2. Methodology
1.  **Consume Plan:** Read the provided plan document (`@thoughts/shared/plans/...`) and isolate the target phase (e.g., "Phase 1").
2.  **Load Context:** Load all files listed in the "Files to Modify" section for the current phase.
3.  **Execute Changes:** Apply the code modifications *exactly* as specified in the plan.
4.  **Verification:** Run the "Automated Verification" steps listed in the plan (e.g., `uv run pytest`, `make lint`).
5.  **Output:** Report success/failure and prompt the user for the "Manual Verification" step.

## 3. Output Format
* If the phase is executed successfully:
    ```markdown
    ### Phase [N] Complete: [Phase Title]
    Automated verification passed:
    - [✓] Unit tests pass
    - [✓] No linting errors

    Please perform Manual Verification:
    - [ ] [Test 1 from plan]
    - [ ] [Test 2 from plan]

    Once validated, tell me to proceed to the next step, or report any bugs encountered.
    ```
* If a verification step fails, immediately report the error and wait for user instructions.

---
