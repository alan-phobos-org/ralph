# Ralph Loop Logging

Ralph Loop creates detailed, structured logs for each run to help you understand and debug agent behavior.

## Directory Structure

Each Ralph run creates a timestamped directory in `/tmp/`:

```
/tmp/ralph_20260126_143022/
├── ralph.log                    # Consolidated log across all iterations
├── summary.txt                  # Run summary with stats and configuration
├── iteration_01/
│   ├── log.txt                  # Formatted log resembling Claude CLI output
│   ├── metadata.json            # Structured data (tokens, duration, status)
│   ├── prompt.txt               # Full wrapped prompt sent to Claude
│   ├── output.txt               # Raw output from Claude
│   └── stderr.txt               # Error output (if any)
├── iteration_02/
│   ├── log.txt
│   ├── metadata.json
│   ├── prompt.txt
│   ├── output.txt
│   └── stderr.txt
└── iteration_03/
    └── ...
```

## File Descriptions

### Run-Level Files

**`ralph.log`** - Main consolidated log file
- Contains all console output
- Includes full details of each iteration
- Useful for viewing the complete run in one file

**`summary.txt`** - High-level summary
- Task description
- Start/end times and total duration
- Number of iterations completed
- Token usage statistics
- Configuration settings

### Iteration-Level Files

Each `iteration_XX/` directory contains:

**`log.txt`** - Primary iteration log
- Header with timestamp, duration, status
- Command executed
- Token usage statistics and tool summary
- **Full Claude output with line-by-line timestamps**
- Detailed tool use section showing inputs (first 1024 chars) and outputs (first 1024 chars)
- Error messages if any
- Formatted to resemble Claude CLI interactive output

**`metadata.json`** - Structured metadata
```json
{
  "success": true,
  "iteration_num": 1,
  "max_turns_reached": false,
  "timeout_occurred": false,
  "input_tokens": 5234,
  "output_tokens": 1823,
  "duration_seconds": 45.32,
  "timestamp": "2026-01-26 14:30:22",
  "has_error": false,
  "output_length": 12453,
  "command": "claude --print --dangerously-skip-permissions ...",
  "tool_uses_count": 3
}
```

**`prompt.txt`** - Full prompt
- Contains the complete wrapped prompt sent to Claude
- Includes outer prompt template, user task, and feedback from previous iteration

**`output.txt`** - Raw output
- Unformatted stdout from Claude CLI
- Useful for programmatic parsing or diffing

**`stderr.txt`** - Error output (if present)
- Only created if there were errors
- Contains stderr from Claude CLI

## Enhanced Log Format

The `log.txt` file uses an enhanced format with detailed timestamps and tool information:

```
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

### Debugging a Failed Iteration

1. Check `iteration_XX/log.txt` for the formatted output
2. Look at `metadata.json` for quick stats (timeout? max turns?)
3. Review `stderr.txt` if it exists for error messages
4. Compare `prompt.txt` to see what was actually sent

### Understanding Agent Behavior

1. Read through `log.txt` to see Claude's thinking and tool use
2. Look for patterns in tool usage across iterations
3. Check if timeouts or max turns are hit repeatedly
4. Review feedback passed between iterations

### Performance Analysis

1. Check `metadata.json` files for duration and token counts
2. Look at `summary.txt` for overall statistics
3. Compare iteration durations to identify slow operations
4. Review token usage to estimate costs

### Comparing Iterations

```bash
# Compare prompts across iterations
diff /tmp/ralph_TIMESTAMP/iteration_01/prompt.txt \
     /tmp/ralph_TIMESTAMP/iteration_02/prompt.txt

# Compare outputs
diff /tmp/ralph_TIMESTAMP/iteration_01/output.txt \
     /tmp/ralph_TIMESTAMP/iteration_02/output.txt

# View metadata for all iterations
jq '.' /tmp/ralph_TIMESTAMP/iteration_*/metadata.json

# Count tool uses per iteration
jq '.tool_uses_count' /tmp/ralph_TIMESTAMP/iteration_*/metadata.json
```

### Analyzing Tool Performance

The timestamped output lets you measure tool execution times:

```bash
# Extract timestamps from log.txt to see tool latency
grep -A 50 "invoke name=" /tmp/ralph_TIMESTAMP/iteration_01/log.txt | grep "^\[" | head -20

# View all tool uses across iterations
grep -h "Tool #" /tmp/ralph_TIMESTAMP/iteration_*/log.txt
```

You can calculate time between tool invocation and result:
- Find the timestamp when `<invoke>` appears
- Find the timestamp when `<function_results>` appears
- The difference shows how long the tool took to execute

## Log Rotation

Ralph does not automatically clean up old log directories. You may want to periodically remove old logs:

```bash
# Remove logs older than 7 days
find /tmp -name "ralph_*" -type d -mtime +7 -exec rm -rf {} +
```

## Custom Log Locations

You can specify a custom log file location:

```bash
./ralph.py "task" --log-file /path/to/custom.log
```

This will create the run directory at `/path/to/custom_[timestamp]/` instead of in `/tmp/`.
