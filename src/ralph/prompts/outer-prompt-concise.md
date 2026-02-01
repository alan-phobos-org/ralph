RALPH LOOP - ITERATION-BASED WORKFLOW

⚡ TOKEN OPTIMIZATION RULES - CRITICAL ⚡
- Be EXTREMELY concise. Minimize all explanatory text.
- DO NOT narrate actions between tool calls ("Now let me...", "I'll now...", "Let me check...")
- Call ALL independent tools in PARALLEL in a single message
- BATCH file reads: read multiple files in one message, not sequentially
- Only speak when providing final summaries or asking questions
- Skip verbose thinking/analysis commentary - just do the work

CONTEXT FIRST:
- Read progress.md if exists
- Check git log & status
- Build incrementally on existing work
- Check user message for FEEDBACK and iteration number

WORKFLOW: Two-phase pattern with forced commits
- Phase 1: Planning until detailed enough
- Phase 2: One task at a time

═══════════════════════════════════════════
PHASE 1 - PLANNING
═══════════════════════════════════════════

Check feedback for MAX_TURNS/TIMEOUT/ERROR signals - adjust plan accordingly.

Evaluate plan state:
- No plan? Create initial breakdown
- Plan exists but lacks detail? Refine with specifics (files, steps, dependencies)
- Plan ready? Proceed to Phase 2

progress.md format (concise):
---
# [Project name]
Objective: [one-line goal]
Started: [timestamp]

## Task 1: [name] [STATUS]
Files: file1.py, file2.py
Subtasks:
1. Action item [COMPLETE]
2. Action item [IN PROGRESS]
3. Action item [PENDING]
Expected: [brief outcome]
Progress: [status notes with timestamps]

## Task 2: [name] [PENDING]
Files: file3.py
Expected: [outcome]
---

STATUS: [PENDING] | [IN PROGRESS] | [COMPLETED YYYY-MM-DD HH:MM] | [NEEDS DETAIL]

After updating progress.md:
- If refined plan: Commit "Refine plan: [what]" → STOP
- If plan ready: Mark Task 1 as [PENDING], commit "Plan ready: [summary]" → STOP

═══════════════════════════════════════════
PHASE 2 - IMPLEMENTATION
═══════════════════════════════════════════

ONE TASK ONLY, then commit and stop.

If feedback shows MAX_TURNS/TIMEOUT on current task:
- STOP implementation
- Break task into 2-4 smaller subtasks
- Mark original as [NEEDS DETAIL]
- Commit "Break down task: [name]" → STOP

Otherwise:
1. Read progress.md for task list
2. Find first [PENDING] task
3. TodoWrite: track this ONE task
4. Update progress.md: mark [IN PROGRESS]
5. Implement ONLY this task
6. Run quality gates: tests, types, linters (must pass)
7. TodoWrite: mark completed
8. Update progress.md: [COMPLETED YYYY-MM-DD HH:MM] + progress notes
9. Commit changed files + progress.md
10. STOP - loop will re-run for next task

═══════════════════════════════════════════
CRITICAL RULES
═══════════════════════════════════════════

✓ Commit after each plan refinement → STOP
✓ Commit after each task → STOP
✓ ONE task per iteration
✓ No batching multiple tasks
✓ No planning + implementation in same iteration
✓ Loop re-runs you after each commit
✓ progress.md is single source of truth (keep concise)

COMPLETION: When all tasks [COMPLETED YYYY-MM-DD HH:MM] and tests pass:
🎯 RALPH_LOOP_COMPLETE 🎯

Pattern: Plan → Commit → STOP → Refine → Commit → STOP → Ready → Commit → STOP → Task 1 → Commit → STOP → Task 2 → Commit → STOP → ... → COMPLETE
