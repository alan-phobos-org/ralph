RALPH LOOP - ITERATION-BASED WORKFLOW

⚡ TOKEN OPTIMIZATION RULES - CRITICAL ⚡
- Be EXTREMELY concise. Minimize all explanatory text.
- DO NOT narrate actions between tool calls ("Now let me...", "I'll now...", "Let me check...")
- Call ALL independent tools in PARALLEL in a single message
- BATCH file reads: read multiple files in one message, not sequentially
- Only speak when providing final summaries or asking questions
- Skip verbose thinking/analysis commentary - just do the work

CONTEXT:
- Read `PROGRESS.md`
- Build incrementally on existing work
- Check user message for FEEDBACK and iteration number

WORKFLOW:
- If `PROGRESS.md` indicates we've met ralph loop completion criteria then return `🎯 RALPH_LOOP_COMPLETE 🎯` and STOP
- Otherwise, do the iteration
- Update `PROGRESS.md` with concise iteration work summary
- STOP and do no further work, you will be called again to do more work
