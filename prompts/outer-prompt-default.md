# Ralph Loop Iteration {iteration_num}

## Iteration Context

{feedback}

**Before you begin:**
1. Read `PROGRESS.md` if it exists (this is your source of truth)
2. Review git log and git status to understand current state
3. Build incrementally on existing work

---

## Your Task

{user_prompt}

> Note: Prompt files are already in context - do not read them.

---

## Workflow Overview

Ralph Loop uses a **mandatory two-phase workflow**: Planning → Implementation

- **Phase 1 (Planning)**: Create or refine a detailed plan in `PROGRESS.md`
- **Phase 2 (Implementation)**: Execute one task at a time from the plan

After each commit, you will be terminated and re-run for the next step.

---

## Phase 1: Planning

**Goal:** Create a sufficiently detailed plan before any implementation.

### Planning may require multiple iterations

Each iteration, evaluate the current state:

1. **Read existing `PROGRESS.md`** (if it exists)

2. **Check feedback** from previous iteration (shown above)
   - MAX TURNS hit → Current task is too large, break into smaller subtasks
   - TIMEOUT occurred → Simplify or split the current task
   - ERROR occurred → Address the error before proceeding

3. **Evaluate the plan:**
   - Does a plan exist?
     - **No** → Create initial plan
     - **Yes** → Is it detailed enough for implementation?

   A plan is ready when:
   - Tasks are broken into clear, actionable subtasks
   - Each subtask has defined steps
   - Files and expected outcomes are specified
   - Dependencies between tasks are clear
   - You can implement Task 1 immediately with confidence

   If the plan needs more detail → Refine and expand it

4. **Update `PROGRESS.md`** using this format:

```
# Project: [Brief project name]
Objective: [One-line objective]
Started: [timestamp]

## Task 1: [Task name] [STATUS]
Files: file1.py, file2.py
Subtasks:
1. Audit file1.py [COMPLETE]
2. Audit file2.py [IN PROGRESS]
3. Consider interface between file1.py and file2.py [PENDING]

Expected: [Brief expected outcome]
Progress:
* [Status note 1, timestamp]
* [Status note 2, timestamp]

## Task 2: [Task name] [PENDING]
Files: file3.py
Expected: [Brief expected outcome]
```

**Status values:**
- `[PENDING]` - Not started
- `[IN PROGRESS]` - Currently being implemented
- `[COMPLETED YYYY-MM-DD HH:MM]` - Done with timestamp
- `[NEEDS DETAIL]` - Task exists but needs more planning

5. **Commit and stop:**
   - If you **refined** the plan: Commit with message "Refine plan: [what you detailed]" → STOP
   - If plan is **ready**: Commit with message "Plan ready: [summary]" → STOP

---

## Phase 2: Implementation

**Goal:** Execute exactly ONE subtask, then commit and stop.

### Work on one subtask at a time

1. **Read `PROGRESS.md`** to see the task list

2. **Check feedback** from previous iteration (shown above)
   - If MAX TURNS or TIMEOUT hit:
     - STOP implementation immediately
     - Break current task into 2-4 smaller subtasks
     - Mark original task as `[NEEDS DETAIL]`
     - Commit with message "Break down task: [task name]"
     - STOP (next iteration will work on first subtask)
   - If ERROR occurred: Address the error before continuing

3. **Identify next task** (first task with status `[PENDING]`)

4. **Track the task** using TodoWrite

5. **Mark task in progress:**
   - Update TodoWrite: Mark as in_progress
   - Update `PROGRESS.md`: Change status to `[IN PROGRESS]`

6. **Execute the task** (do not batch multiple tasks)

7. **Run quality gates:** Tests, type checks, linters (all must pass)

8. **Mark task complete:**
   - Update TodoWrite: Mark as completed
   - Update `PROGRESS.md`:
     - Change status to `[COMPLETED YYYY-MM-DD HH:MM]`
     - Add progress notes inline: "Progress: Implemented X, tested Y"

9. **Commit:** Include all files you touched plus updated `PROGRESS.md`

10. **STOP IMMEDIATELY** - do not continue to next task

---

## Critical Rules

### Workflow enforcement

- Commit after planning/refining (Phase 1) → STOP
- Commit after each task completion (Phase 2) → STOP
- Plan can iterate multiple times until detailed enough
- Do NOT do planning and implementation in the same iteration
- Do NOT batch multiple tasks - ONE task per iteration
- Your process WILL BE TERMINATED after each commit

### File management

- `PROGRESS.md` is your ONLY tracking file (keep it concise)
- Keep progress notes inline with each task (no separate sections)
- Only commit files you touched plus `PROGRESS.md` (ignore other workspace changes)

### Completion

When ALL tasks are marked `[COMPLETED YYYY-MM-DD HH:MM]` and all requirements are met:

```
🎯 RALPH_LOOP_COMPLETE 🎯
```

Only emit this signal when absolutely certain everything is done.

---

## Iteration Pattern

```
Initial plan → Commit → STOP
Refine plan → Commit → STOP (repeat as needed)
Plan ready → Commit → STOP
Task 1 → Commit → STOP
Task 2 → Commit → STOP
Task N → Commit → STOP → COMPLETE
```

Check `PROGRESS.md` to determine your current phase.
