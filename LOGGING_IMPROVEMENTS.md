# Ralph Loop Logging Improvements

This document outlines planned improvements to reduce duplication, professionalize output, and make logs more useful while preserving complete debugging information.

## 1. Smart Prompt Deduplication with Diff-Based Display

**Problem**: Prompts are repeated in full for each iteration (~300 lines each), but they do change between iterations due to the feedback mechanism.

**Solution**: Show full prompt for Iteration 1, then only diffs for subsequent iterations.

### Implementation

**Iteration 1**: Full prompt (baseline)
```
═══ Iteration 1 Prompt (5,524 chars) ═══
[full prompt text]
```

**Subsequent iterations**: Only show changes from previous iteration
```
═══ Iteration 2 Prompt (5,788 chars, +264 chars) ═══
[CHANGES FROM ITERATION 1]
+ ============================================================
+ FEEDBACK FROM PREVIOUS ITERATION:
+ ============================================================
+ ✅ Previous iteration completed successfully.
+ ============================================================
+
[UNCHANGED SECTIONS - 4,800 chars omitted, see Iteration 1]
```

**Impact**: Reduces ~70% of duplicate content while preserving debugging capability.

## 2. Standardized Metadata Block

**Problem**: Configuration appears in 3+ duplicate places per iteration (initial config, iteration summary, token usage separated).

**Solution**: Single consolidated header per iteration.

### Implementation

```
╔═══════════════════════════════════════════════════════════════
║ Iteration 1/10 | Started: 2026-01-31 16:32:23
╠═══════════════════════════════════════════════════════════════
║ Configuration:
║   Task file: ../ralph/prompts/prompt-code-review.md
║   Model: opus | Max turns: 50 | Timeout: 600s | HITL: false
║   CLI: claude --print --dangerously-skip-permissions [...]
║   Prompt size: 5,524 chars (1,381 tokens est.)
║   Environment: CLAUDE_CODE_YOLO=1
╠═══════════════════════════════════════════════════════════════
║ Result: ✅ Success | Duration: 41.84s | Turns: 12
║ Tokens: 1,381 in → 10,749 out → 12,130 total
║ Exit reason: Commit detected (ec3f176)
╚═══════════════════════════════════════════════════════════════
```

**Impact**: Eliminates duplicate config sections while improving scannability.

## 3. Preserve Full Tool Output with Better Organization

**Problem**: Tool invocations and results are verbose JSON with poor visual organization.

**Solution**: Keep ALL tool output (required for debugging) but structure it clearly with box-drawing characters and folding markers.

### Implementation

```
[16:32:28.959 +5.70s] TOOL INVOKED: Read
┌─ Input ──────────────────────────────────────
│ {
│   "file_path": "/Users/alan/rc/h2ai/progress.md"
│ }
├─ Result [+0.79s] ───────────────────────────────
│ ✗ ERROR: File does not exist.
└──────────────────────────────────────────────

[16:32:29.626 +6.37s] TOOL INVOKED: Read
┌─ Input ──────────────────────────────────────
│ {
│   "file_path": "/Users/alan/rc/ralph/prompts/prompt-code-review.md"
│ }
├─ Result [+0.15s] ───────────────────────────────
│      1→Act as a very experienced software engineer...
│      2→
│      3→Find and read any relevant `AGENTS.md` file
│   [... full 397 chars output ...]
│     10→5. Any passwords/tokens or other sensitive a... [397 more chars]
└──────────────────────────────────────────────

[16:32:30.641 +7.38s] TOOL INVOKED: Bash
┌─ Input ──────────────────────────────────────
│ {
│   "command": "git log --oneline -10",
│   "description": "Check recent git commits"
│ }
├─ Result [+1.16s] ───────────────────────────────
│ faadb21 Remove progress.md
│ 1878850 review: complete Task 5 - final code review report compiled
│ [... full output ...]
│ Exit code: 0
└──────────────────────────────────────────────
```

### Benefits
- Full debugging info preserved (complete requirement)
- Clear visual boundaries between tools
- Timing data prominent (invocation time + duration)
- Easy to scan or fold in editors
- Box drawing characters create hierarchy without clutter

## 4. Single Unified Flow (No Separation)

**Decision**: Keep chronological interleaved format of TEXT blocks and tool invocations as-is. Do NOT separate into "narrative" and "technical" sections.

## 5. Hierarchical Markers Replace Separators

**Problem**: 50+ lines of `========` separators that don't convey semantic meaning.

**Solution**: Use consistent hierarchical box-drawing markers.

### Implementation

**Current (wasteful)**:
```
================================================================================
Ralph Loop - Initial Configuration
================================================================================
[config content]
================================================================================

COMMAND: claude --print ...
================================================================================
STREAMING OUTPUT (real-time):
================================================================================
```

**Improved**:
```
╔══════════════════════════════════════════════════════════════════
║ RALPH LOOP EXECUTION
╠══════════════════════════════════════════════════════════════════
║ Initial Configuration
╟──────────────────────────────────────────────────────────────────
[config content]
╟──────────────────────────────────────────────────────────────────
║ Command: claude --print ...
╟──────────────────────────────────────────────────────────────────
║ Streaming Output (real-time)
╠══════════════════════════════════════════════════════════════════
```

### Box Drawing Characters
- `╔═╗` - Top-level boundaries
- `╠═╣` - Major section dividers
- `╟─╢` - Subsection dividers
- `║` - Section labels
- `┌─┐├─┤└─┘│` - Tool boundaries (lighter weight)

**Impact**: Eliminates ~40 meaningless separator lines while adding semantic meaning through hierarchy.

## Expected Results

**Log size reduction**: From 1,388 lines to ~800-900 lines
- ~70% reduction in prompt duplication
- ~40 lines of separators eliminated
- Metadata consolidation saves ~20 lines per iteration

**Improvements**:
- Complete debugging information preserved
- Better scannability with hierarchical structure
- Easier to fold/collapse sections in editors
- Clear timing information for performance analysis
- Professional appearance with semantic structure

## Implementation Files

Primary changes needed in:
- `ralph.py` - Lines 1303+ (console output formatting)
- Prompt diff calculation logic (new function)
- Box-drawing character constants (new module)
- Metadata consolidation in iteration summaries
