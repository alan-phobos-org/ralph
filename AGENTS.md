# Agent Instructions

## What This Is

Ralph Loop: iterative AI agent execution pattern. Feeds same prompt repeatedly to AI until task complete. Progress persists in files/git, not context.

**Core principle:** Naive persistence beats sophisticated complexity.

## Files

- [ralph.py](ralph.py) - Current implementation (preferred)
- [ralph-old.py](ralph-old.py) - Original implementation (reference)
- [RALPH.md](RALPH.md) - Comprehensive documentation and patterns

## Key Mechanisms

1. **External verification** - Agent reviews own work each iteration, identifies gaps, improves
2. **Self-correcting** - Each iteration sees previous changes via git/files, fixes bugs
3. **Fresh context** - When context fills, fresh agent continues from file state
4. **File system = truth** - Git history + files persist; LLM memory does not

## Implementation Pattern

Agent receives wrapped prompt with mandatory workflow:
1. Read progress.md (ground truth)
2. Do ONE task only
3. Run quality gates (tests/types/lint)
4. Update progress.md
5. Commit work + progress.md
6. STOP (loop re-invokes for next task)

Forced constraints:
- Low max-turns (8) prevents overwork
- Aggressive timeout (180s)
- Commit detection forces continuation
- Mechanical limits beat prompt compliance

## GIT COMMITS

**DO NOT CREATE GIT COMMITS.**

User manages all git operations. Focus on code changes only.

## Logging & Output Status

**Goal:** Clean human-readable console + comprehensive detailed log file

**Current State (ralph.py):**
- ✓ Single consolidated log file per run
- ✓ Real-time streaming with timestamps
- ✓ JSON parsing for tool invocations
- ✓ Structured metadata and iteration summaries
- ✓ Compaction detection and heartbeat monitoring
- ✗ Console output messy - raw JSON streams via TeeLogger
- ✗ TeeLogger duplicates everything to both destinations

**Design Decisions (finalized):**

Console Output:
- Real-time streaming as tools execute
- Plain text (no ANSI colors/escape codes)
- Verbose: tool name + truncated input
- Emojis allowed (visual markers)
- Format: "🔧 Read config.py (lines 10-50)"
- Format: "⚡ Bash: git status"
- NO raw JSON streaming

Log File Output:
- Console output duplicated (for continuity)
- Plus full JSON with timestamps
- No emojis in structured sections
- Section delimiters (=====)
- Complete metadata and summaries
- Note: May evolve to pure human-readable later

**Implementation Complete:**
✓ Added console_print() function (uses sys.__stdout__ to bypass TeeLogger)
✓ Added get_tool_emoji() for visual markers
✓ Added truncate_smart() for intelligent text truncation
✓ Modified stream_output_reader() to emit dual outputs:
  - Parses JSON and prints clean summaries to console
  - Continues writing full JSON to log file
  - Handles tool invocations with verbose details
  - Shows completion status (✓/✗) with error summaries
✓ Tool-specific formatting:
  - Read: shows file path + line ranges
  - Edit/Write: shows file path
  - Bash: shows command (60 chars) + exit code + output preview (64 chars)
  - Grep/Glob: shows pattern (50 chars)
  - Task: shows description (50 chars)
  - TodoWrite: shows task count + status breakdown
✓ Final iteration summary with duration and turns
✓ Deferred printing system:
  - Tools NOT printed when invoked (avoids duplication)
  - Only printed when result arrives (single line per tool)
  - Tool + result appear together as atomic block
  - Cleaner output for parallel execution

**Example Console Output:**
```
📖 Read: /Users/alan/rc/ralph/ralph.py (lines 100-150)
  ✓ Completed
⚡ Bash: git status --short
  ✓ Exit 0: M ralph.py
?? test.py
✏️ Edit: config.py
  ✓ Completed
⚡ Bash: npm test
  ✓ Exit 1: FAIL src/utils.test.ts
  ✕ should validate input...
📋 TodoWrite: 4 tasks (1 completed, 1 in_progress, 2 pending)
  ✓ Completed

--- Iteration Complete: success ---
Duration: 12.3s | Turns: 5
```

Note: Each tool appears only once (when result arrives), creating compact output.

**Recent Fixes:**
✓ Removed raw JSON output from console (lines 1303-1304)
  - Tool output already shown via console_print() during execution
  - Removed duplicate output printing after iteration completes
✓ Cleaned up error output (lines 1285-1289)
  - Don't print raw JSON stdout on errors
  - User directed to log file for full details

**Status:**
Console now shows ONLY clean tool summaries + iteration stats.
All JSON/system messages go to log file only.

## Your Role

When working in this repo:
- Analyze/improve ralph loop implementation
- Test/verify script functionality
- Keep docs accurate (RALPH.md, AGENTS.md)
- Propose improvements to wrapper prompts or constraints
- NO commits - user handles git
