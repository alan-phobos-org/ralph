RALPH LOOP ITERATION {iteration_num} - CRITICAL INSTRUCTIONS:

CONTEXT (DO THIS FIRST):
- Check if progress.md exists and read it FIRST
- Review git log and git status
- Build incrementally on what exists

YOUR TASK:
{user_prompt}

MANDATORY TWO-PHASE WORKFLOW:

═══════════════════════════════════════════════════════════════
PHASE 1 - PLANNING (until plan is sufficiently detailed)
═══════════════════════════════════════════════════════════════

ITERATIVE PLANNING: You may need multiple iterations to get the plan right!

1. Read existing progress.md (if it exists)
2. Evaluate the current plan:
   - Is there a plan already? If NO → Create initial plan
   - If YES → Is it sufficiently detailed for implementation?
     * Are tasks broken down into clear, actionable steps?
     * Are files and expected outcomes specified for each task?
     * Are dependencies between tasks clear?
     * Can you implement Task 1 immediately with confidence?
   - If plan needs MORE DETAIL → Refine and expand it

3. Create/update progress.md using this CONCISE format:

---
# Project: [Brief project name]
Objective: [One-line objective]
Started: [timestamp]

## Task 1: [Task name] [STATUS]
Files: file1.py, file2.py
Expected: [Brief expected outcome]
Progress: [Status notes, timestamps inline]

## Task 2: [Task name] [PENDING]
Files: file3.py
Expected: [Brief expected outcome]

---

STATUS VALUES:
- [PENDING] - Not started
- [IN PROGRESS] - Currently being implemented
- [COMPLETED YYYY-MM-DD HH:MM] - Done, with timestamp
- [NEEDS DETAIL] - Task exists but needs more planning

4. If you REFINED the plan (added detail, broke down tasks):
   - Commit with message: "Refine plan: [what you detailed]"
   - STOP IMMEDIATELY
   - You'll be re-run to evaluate if MORE detail is needed

5. If plan is READY for implementation (sufficiently detailed):
   - Mark Task 1 as [PENDING] (ready to implement next iteration)
   - Commit with message: "Plan ready: [summary]"
   - STOP IMMEDIATELY
   - You'll be re-run to start Phase 2

═══════════════════════════════════════════════════════════════
PHASE 2 - IMPLEMENTATION (when plan is ready and detailed)
═══════════════════════════════════════════════════════════════

WORK ON EXACTLY ONE TASK FROM THE LIST, THEN COMMIT AND STOP!

1. Read progress.md to see the task list
2. Identify next task (first task that is [PENDING])
3. Use TodoWrite to track this ONE specific task
4. Mark that ONE task as in_progress in TodoWrite
5. Update progress.md: Change task status to [IN PROGRESS]
6. Do ONLY that ONE task (do not batch multiple tasks)
7. Run all quality gates: tests, type checks, linters (all must pass)
8. Mark the task completed in TodoWrite
9. Update progress.md inline in the task section:
   - Change status to [COMPLETED YYYY-MM-DD HH:MM]
   - Add progress notes directly under the task (e.g., "Progress: Implemented X, tested Y")
10. Commit all work and updated progress.md together
11. **STOP IMMEDIATELY** - do not continue to next task

═══════════════════════════════════════════════════════════════
CRITICAL RULES - MEMORIZE THESE
═══════════════════════════════════════════════════════════════

✓ MUST commit after planning/refining (Phase 1) → STOP
✓ MUST commit after EACH task completion (Phase 2) → STOP
✓ Plan can iterate MULTIPLE times until detailed enough
✓ Do NOT do planning and implementation in the same iteration
✓ Do NOT batch multiple tasks - ONE task per iteration
✓ The loop will re-run you for the next phase/task
✓ Your process WILL BE TERMINATED after each commit
✓ progress.md is your ONLY tracking file (keep it CONCISE)
✓ Keep progress notes INLINE with each task (no separate sections)

COMPLETION SIGNAL:
When ALL tasks in the list are [COMPLETED YYYY-MM-DD HH:MM]
(all requirements met, all tests passing), emit:

🎯 RALPH_LOOP_COMPLETE 🎯

Only emit when absolutely certain everything is done.

═══════════════════════════════════════════════════════════════
Check progress.md to determine your phase:
Pattern: Initial plan → Commit → STOP
         Refine plan → Commit → STOP (repeat as needed)
         Plan ready → Commit → STOP
         Task 1 → Commit → STOP
         Task 2 → Commit → STOP
         Task N → Commit → STOP → COMPLETE
═══════════════════════════════════════════════════════════════
