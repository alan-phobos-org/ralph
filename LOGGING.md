# Ralph Loop Logging

Ralph Loop creates a single, comprehensive log file for each run to help you understand and debug agent behavior.

## Log File Structure

Each Ralph run creates a single timestamped log file in `/tmp/`:

```
/tmp/ralph_myproject_20260126_143022_iteration.log
```

The filename includes:
- `ralph_` prefix
- Work directory basename (e.g., `myproject`)
- Timestamp (`YYYYMMDD_HHMMSS`)
- `_iteration.log` suffix

## Log File Contents

The single log file contains everything from the entire run in chronological order:

### Initial Configuration Section
- Task description
- Start time
- Configuration settings (max iterations, max turns, timeout, CLI type, model)
- **Initial wrapped prompt** (shown once at the start)

### Per-Iteration Sections
Each iteration includes:
- Header with iteration number, timestamp, and duration
- Command executed
- Status (success/failure, max turns, timeout indicators)
- Token usage statistics (input, output, total)
- Tool summary (count and names of tools used)
- **Full Claude output with line-by-line timestamps**
- Error output if any

### Run Summary Section
At the end of the file:
- Task description
- Start/end times and total elapsed time
- Number of iterations completed
- Cumulative token usage across all iterations
- Configuration summary

## Enhanced Log Format

The log file uses an enhanced format with detailed timestamps and tool information. The wrapped prompt is shown **only once** at the start of the file, not before each iteration:

```
================================================================================
Ralph Loop - Initial Configuration
================================================================================

Task: Fix all type errors in the codebase
Start time: 2026-01-26 14:30:00
Max iterations: 10
Max turns per iteration: 50
Timeout per iteration: 600 seconds
CLI: claude
Model: opus

--- INITIAL WRAPPED PROMPT ---
[Full wrapped prompt shown here once]
--- END INITIAL WRAPPED PROMPT ---


================================================================================
Ralph Loop - Iteration 1
Timestamp: 2026-01-26 14:30:22
Duration: 45.32s
================================================================================

Command:
  claude --print --dangerously-skip-permissions --max-turns 50 --model opus -p [prompt]

Status: ✅ Success

Token Usage (estimated):
  Input:  5,234 tokens
  Output: 1,823 tokens
  Total:  7,057 tokens

Tools Used: 2
  1. Read
  2. Edit

================================================================================
Claude Output (with timestamps)
================================================================================

[14:30:25.123] Let me read the file first.
[14:30:25.124]
[14:30:25.125] <invoke name="Read">
[14:30:25.126] <parameter name="file_path">/path/to/file.txt</parameter>
[14:30:25.127] </invoke>
[14:30:26.445]
[14:30:26.446] <function_results>
[14:30:26.447] File content goes here...
[14:30:26.448] </function_results>
[14:30:26.789]
[14:30:26.790] Now I'll make the edits...
[14:30:26.791]
[14:30:26.792] <invoke name="Edit">
[14:30:26.793] <parameter name="file_path">/path/to/file.txt</parameter>
[14:30:26.794] <parameter name="old_string">old text</parameter>
[14:30:26.795] <parameter name="new_string">new text</parameter>
[14:30:26.796] </invoke>
[14:30:27.234]
[14:30:27.235] <function_results>
[14:30:27.236] The file /path/to/file.txt has been updated successfully.
[14:30:27.237] </function_results>

================================================================================
End of Iteration 1
================================================================================

[Additional iterations follow...]

================================================================================
Ralph Loop Run Summary
================================================================================

Task: Fix all type errors in the codebase
Start time: 2026-01-26 14:30:00
End time: 2026-01-26 14:45:30
Total elapsed: 0:15:30
Iterations completed: 3
Max iterations: 10

Token usage (estimated):
  Input:  15,234 tokens
  Output: 8,432 tokens
  Total:  23,666 tokens

Configuration:
  CLI type: claude
  Model: opus
  Max turns: 50
  Timeout: 600s
```

### Key Features

1. **Line-by-Line Timestamps**: Every line of Claude's output is prefixed with `[HH:MM:SS.mmm]` showing exactly when it was received
2. **Tool Summary**: Quick overview at the top showing count and names of all tools used in the iteration
3. **Inline Tool Details**: All tool invocations, parameters, results, and errors are shown inline in the timestamped output with:
   - Tool input parameters (with first 1024 chars shown inline)
   - Tool output/results (with first 1024 chars shown inline)
   - Error messages and return codes when tools fail (e.g., `Exit code 1` for Bash commands)
4. **Truncation Indicators**: Long inputs/outputs show `... [truncated, X more chars]` in the parsing metadata

## What's Captured

### Claude Output Structure

The `log.txt` and `output.txt` files capture the full Claude CLI output, which includes:

1. **Thinking blocks** - Claude's internal reasoning (when available)
2. **Tool use** - Function calls with parameters
3. **Tool results** - Return values from tool executions including errors
4. **Text responses** - Claude's messages to the user
5. **Status updates** - Progress indicators, completions, errors

This gives you visibility into:
- What Claude is thinking at each step
- Which tools it's using and why
- The results it's getting back
- **When tools fail** - including error messages and return codes
- How it's reasoning about the task

### Error Information

Tool failures are captured in the timestamped output with full detail:

- **Error tags**: `<error>` blocks showing error messages
- **Return codes**: For Bash commands, `Exit code N` is shown
- **Error detection**: The parser identifies errors and tracks them in metadata
- **Inline visibility**: All errors appear exactly where they occurred in the execution flow

Example of a failed tool:
```
[14:30:27.234] <invoke name="Bash">
[14:30:27.235] <parameter name="command">ls /nonexistent</parameter>
[14:30:27.236] </invoke>
[14:30:27.450]
[14:30:27.451] <function_results>
[14:30:27.452] ls: /nonexistent: No such file or directory
[14:30:27.453] Exit code 1
[14:30:27.454] </function_results>
```

### Timing Information

- **Line-by-line timestamps**: Each output line is timestamped with millisecond precision
- Overall duration per iteration
- Timestamp for when each iteration started
- Elapsed time from run start (in detailed logger events)
- Ability to see exactly when Claude produced each piece of output

### Token Usage

- Estimated input tokens (prompt size)
- Estimated output tokens (response size)
- Cumulative totals across iterations
- Per-iteration breakdowns

## Usage Tips

### Viewing the Log File

```bash
# View the entire log file
less /tmp/ralph_myproject_20260126_143022_iteration.log

# View just the initial configuration and prompt
head -100 /tmp/ralph_myproject_20260126_143022_iteration.log

# View the summary at the end
tail -50 /tmp/ralph_myproject_20260126_143022_iteration.log

# Search for a specific iteration
grep -A 30 "Iteration 3" /tmp/ralph_myproject_20260126_143022_iteration.log
```

### Debugging a Failed Iteration

1. Search for the iteration number in the log file
2. Look for "Status: ❌ Failed" lines
3. Check for "Max turns limit reached" or "Timeout occurred" warnings
4. Review the error section for that iteration
5. Examine the timestamped output to see where it failed

### Understanding Agent Behavior

1. Read through the log file sequentially to see the full story
2. Look for patterns in tool usage across iterations
3. Check if timeouts or max turns are hit repeatedly
4. The initial prompt is shown once at the top for reference

### Performance Analysis

1. Look at each iteration's duration and token counts
2. Check the summary section at the end for overall statistics
3. Compare iteration durations to identify slow operations
4. Review cumulative token usage to estimate costs

### Searching and Filtering

```bash
# Find all errors
grep -n "Status: ❌" /tmp/ralph_*.log

# Extract all iteration headers
grep -n "Ralph Loop - Iteration" /tmp/ralph_*.log

# View all tool summaries
grep -A 5 "Tools Used:" /tmp/ralph_*.log

# Find specific tool uses
grep -B 2 -A 2 "invoke name=\"Edit\"" /tmp/ralph_*.log
```

### Analyzing Tool Performance

The timestamped output lets you measure tool execution times:

```bash
# Find tool invocations and their timestamps
grep "invoke name=" /tmp/ralph_*.log

# Calculate time between invocation and result
# Look for the timestamp on the <invoke> line and the <function_results> line
grep -A 20 "invoke name=" /tmp/ralph_*.log | grep "^\["
```

## Log Rotation

Ralph does not automatically clean up old log files. You may want to periodically remove old logs:

```bash
# Remove logs older than 7 days
find /tmp -name "ralph_*_iteration.log" -type f -mtime +7 -delete

# List all Ralph logs sorted by date
ls -lht /tmp/ralph_*_iteration.log
```

## Custom Log Locations

You can specify a custom log file location:

```bash
./ralph.py "task" --log-file /path/to/custom.log
```

This will create the log file at the specified path instead of the default `/tmp/` location.
