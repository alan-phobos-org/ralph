"""
Ralph Loop: Iterative AI agent execution with progress persistence.

Feeds the same prompt repeatedly to an AI agent until task complete.
Progress persists in files and git, not context.
"""

import argparse
import difflib
import json
import os
import re
import subprocess
import sys
import threading
import time
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, TextIO

# Get package version
try:
    from importlib.metadata import version, PackageNotFoundError
    __version__ = version("ralph-loop")
except (ImportError, PackageNotFoundError):
    __version__ = "0.1.0"  # fallback for development

# ============================================================================
# CONSTANTS
# ============================================================================

# Display and formatting
SECTION_WIDTH = 80
TRUNCATE_RESULT_PREVIEW = 500
TRUNCATE_TOOL_INPUT = 1024
TRUNCATE_TOOL_RESULT = 1024
TRUNCATE_ERROR_MSG = 512
TRUNCATE_JSON_LOG = 200
BASH_CMD_PREVIEW = 60
BASH_OUTPUT_PREVIEW = 64
PATTERN_PREVIEW = 50

# Threading and timing
HEARTBEAT_INTERVAL = 30
POLL_INTERVAL = 0.1
THREAD_JOIN_TIMEOUT = 2

# Tool emoji mappings
TOOL_EMOJIS = {
    'Read': '📖',
    'Edit': '✏️',
    'Write': '📝',
    'Bash': '⚡',
    'Glob': '🔍',
    'Grep': '🔎',
    'Task': '🤖',
    'WebFetch': '🌐',
    'WebSearch': '🔍',
    'AskUserQuestion': '❓',
    'TodoWrite': '📋',
}
DEFAULT_TOOL_EMOJI = '🔧'

# Completion and error signals
COMPLETION_SIGNAL_TEXT = 'RALPH_LOOP_COMPLETE'
COMPLETION_SIGNAL_EMOJI = '🎯'
EXIT_CODE_PATTERN = re.compile(r'Exit code[:\s]+(\d+)', re.IGNORECASE)
ERROR_INDICATORS = ['<error>']  # Only check for structured error tags to avoid false positives

# Compaction detection patterns
COMPACTION_PATTERNS = [
    'conversation has been automatically summarized',
    'conversation has unlimited context through automatic summarization',
    'the conversation has been compacted',
    'compacting the conversation',
    'summarizing previous messages',
    'context window is nearly full'
]

# Box-drawing characters for hierarchical logging
BOX_TOP_LEFT = '╔'
BOX_TOP_RIGHT = '╗'
BOX_BOTTOM_LEFT = '╚'
BOX_BOTTOM_RIGHT = '╝'
BOX_HORIZONTAL_HEAVY = '═'
BOX_VERTICAL_HEAVY = '║'
BOX_LEFT_TEE_HEAVY = '╠'
BOX_RIGHT_TEE_HEAVY = '╣'
BOX_LEFT_TEE_LIGHT = '╟'
BOX_RIGHT_TEE_LIGHT = '╢'
BOX_HORIZONTAL_LIGHT = '─'
BOX_VERTICAL_LIGHT = '│'
BOX_TOP_LEFT_LIGHT = '┌'
BOX_TOP_RIGHT_LIGHT = '┐'
BOX_BOTTOM_LEFT_LIGHT = '└'
BOX_BOTTOM_RIGHT_LIGHT = '┘'
BOX_LEFT_TEE_LIGHT_HEAVY = '├'
BOX_RIGHT_TEE_LIGHT_HEAVY = '┤'


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def console_print(message: str) -> None:
    """Print to console only (not to log file), bypassing TeeLogger."""
    sys.__stdout__.write(message + '\n')
    sys.__stdout__.flush()


def get_tool_emoji(tool_name: str) -> str:
    """Get emoji for tool name."""
    return TOOL_EMOJIS.get(tool_name, DEFAULT_TOOL_EMOJI)


def truncate_text(text: str, max_len: int, smart: bool = True, indicator: str = '...') -> str:
    """
    Truncate text to max_len with optional smart word boundary detection.

    Args:
        text: Text to truncate
        max_len: Maximum length
        smart: If True, prefer whole words
        indicator: Truncation indicator string

    Returns:
        Truncated string with indicator if needed
    """
    if len(text) <= max_len:
        return text

    if smart and ' ' in text[:max_len]:
        truncated = text[:max_len].rsplit(' ', 1)[0]
    else:
        truncated = text[:max_len]

    return truncated + indicator


def estimate_tokens(text: str) -> int:
    """
    Estimate token count from text using characters / 4 heuristic.
    For accurate counting, use tiktoken or anthropic SDK.
    """
    return len(text) // 4


def compute_prompt_diff(old_prompt: str, new_prompt: str) -> tuple[list[str], int]:
    """
    Compute unified diff between old and new prompt.

    Returns:
        Tuple of (diff_lines, unchanged_char_count)
    """
    old_lines = old_prompt.splitlines(keepends=True)
    new_lines = new_prompt.splitlines(keepends=True)

    diff = difflib.unified_diff(
        old_lines,
        new_lines,
        fromfile='Previous Iteration',
        tofile='Current Iteration',
        lineterm=''
    )

    diff_lines = list(diff)

    # Calculate unchanged character count
    unchanged_chars = 0
    if diff_lines:
        # Skip diff header (first 3 lines: ---, +++, @@)
        for line in old_lines:
            # Check if this line is in the diff (appears with + or -)
            is_changed = any(line.strip() in d[1:].strip() for d in diff_lines if d.startswith(('+', '-')))
            if not is_changed:
                unchanged_chars += len(line)

    return diff_lines, unchanged_chars


def get_work_dir_basename() -> str:
    """Get the basename of the current working directory."""
    return Path.cwd().name


def create_log_file_path() -> str:
    """Create log file path with work directory basename and timestamp."""
    work_dir = get_work_dir_basename()
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    return f'/tmp/ralph_{work_dir}_{timestamp}_iteration.log'


# ============================================================================
# LOG WRITING HELPERS
# ============================================================================

def write_to_log(log_file: TextIO, text: str, flush: bool = True) -> None:
    """Write text to log file and optionally flush."""
    log_file.write(text)
    if flush:
        log_file.flush()


def write_log_box_header(log_file: TextIO, title: str, width: int = SECTION_WIDTH) -> None:
    """Write a box header with heavy borders."""
    line = BOX_HORIZONTAL_HEAVY * (width - 2)
    write_to_log(log_file, f"{BOX_TOP_LEFT}{line}{BOX_TOP_RIGHT}\n")
    write_to_log(log_file, f"{BOX_VERTICAL_HEAVY} {title}\n")
    write_to_log(log_file, f"{BOX_LEFT_TEE_HEAVY}{line}{BOX_RIGHT_TEE_HEAVY}\n")


def write_log_box_footer(log_file: TextIO, width: int = SECTION_WIDTH) -> None:
    """Write a box footer with heavy borders."""
    line = BOX_HORIZONTAL_HEAVY * (width - 2)
    write_to_log(log_file, f"{BOX_BOTTOM_LEFT}{line}{BOX_BOTTOM_RIGHT}\n")


def write_log_box_divider(log_file: TextIO, width: int = SECTION_WIDTH, heavy: bool = True) -> None:
    """Write a box divider line."""
    if heavy:
        line = BOX_HORIZONTAL_HEAVY * (width - 2)
        write_to_log(log_file, f"{BOX_LEFT_TEE_HEAVY}{line}{BOX_RIGHT_TEE_HEAVY}\n")
    else:
        line = BOX_HORIZONTAL_LIGHT * (width - 2)
        write_to_log(log_file, f"{BOX_LEFT_TEE_LIGHT}{line}{BOX_RIGHT_TEE_LIGHT}\n")


def write_log_box_line(log_file: TextIO, text: str) -> None:
    """Write a line inside a box with vertical border."""
    write_to_log(log_file, f"{BOX_VERTICAL_HEAVY} {text}\n")


def write_log_section(log_file: TextIO, title: str, width: int = SECTION_WIDTH) -> None:
    """Write a section header to log file (legacy compatibility)."""
    write_log_box_header(log_file, title, width)


def write_log_separator(log_file: TextIO, width: int = SECTION_WIDTH) -> None:
    """Write a separator line to log file (legacy compatibility)."""
    write_log_box_divider(log_file, width, heavy=True)


def format_token_usage(input_tokens: int, output_tokens: int) -> str:
    """Format token usage as a multi-line string."""
    total = input_tokens + output_tokens
    return (
        f"Token Usage (estimated):\n"
        f"  Input:  {input_tokens:,} tokens\n"
        f"  Output: {output_tokens:,} tokens\n"
        f"  Total:  {total:,} tokens"
    )


# ============================================================================
# BASH OUTPUT PARSING
# ============================================================================

def parse_bash_result(result_content: str) -> tuple[int, str]:
    """
    Parse Bash tool result to extract exit code and output preview.

    Returns:
        Tuple of (exit_code, output_preview)
    """
    # Extract exit code
    exit_match = EXIT_CODE_PATTERN.search(result_content)
    exit_code = int(exit_match.group(1)) if exit_match else 0

    # Extract output (before "Exit code" line)
    output_lines = []
    for line in result_content.split('\n'):
        if 'exit code' in line.lower():
            break
        output_lines.append(line)

    output_preview = '\n'.join(output_lines).strip()
    return exit_code, output_preview


def format_tool_result(result_content: str, is_error: bool, tool_summary: str) -> str:
    """
    Format tool result for console output.

    Args:
        result_content: Result content from tool
        is_error: Whether this is an error result
        tool_summary: Summary line for the tool

    Returns:
        Formatted string for console output
    """
    # Check for errors
    has_error = is_error or any(indicator in result_content for indicator in ERROR_INDICATORS)

    if has_error:
        # Try to extract clean error message from <error> tags
        error_match = re.search(r'<error>(.*?)</error>', result_content, re.DOTALL)
        if error_match:
            error_msg = truncate_text(error_match.group(1).strip(), 200)
        else:
            error_msg = truncate_text(result_content, 200)
        return f"  ✗ Error: {error_msg}"

    # Handle Bash tool specially to show exit code
    if tool_summary.startswith('⚡ Bash'):
        exit_code, output_preview = parse_bash_result(result_content)

        # Show ✗ for non-zero exit codes, ✓ for success
        status_icon = '✗' if exit_code != 0 else '✓'

        if output_preview:
            preview = truncate_text(output_preview, BASH_OUTPUT_PREVIEW)
            return f"  {status_icon} Exit {exit_code}: {preview}"
        else:
            return f"  {status_icon} Exit {exit_code}"

    # For other tools, show completion status
    result_len = len(result_content)
    if result_len > 1000:
        return f"  ✓ Completed ({result_len:,} chars)"
    else:
        return f"  ✓ Completed"


# ============================================================================
# TOOL SUMMARY BUILDING
# ============================================================================

def build_tool_summary(tool_name: str, tool_input: dict) -> str:
    """
    Build a console-friendly summary for a tool invocation.

    Args:
        tool_name: Name of the tool being invoked
        tool_input: Input parameters for the tool

    Returns:
        Formatted summary string with emoji and relevant details
    """
    emoji = get_tool_emoji(tool_name)
    summary = f"{emoji} {tool_name}"

    # Add verbose details based on tool type
    if tool_name == 'Read':
        file_path = tool_input.get('file_path', '')
        if file_path:
            summary += f": {file_path}"
            offset = tool_input.get('offset')
            limit = tool_input.get('limit')
            if offset or limit:
                start = offset or 1
                end = start + (limit or 100)
                summary += f" (lines {start}-{end})"

    elif tool_name in ['Edit', 'Write']:
        file_path = tool_input.get('file_path', '')
        if file_path:
            summary += f": {file_path}"

    elif tool_name == 'Bash':
        command = tool_input.get('command', '')
        if command:
            summary += f": {truncate_text(command, BASH_CMD_PREVIEW)}"

    elif tool_name == 'Glob':
        pattern = tool_input.get('pattern', '')
        if pattern:
            summary += f": {pattern}"

    elif tool_name == 'Grep':
        pattern = tool_input.get('pattern', '')
        if pattern:
            summary += f": {truncate_text(pattern, PATTERN_PREVIEW)}"

    elif tool_name == 'Task':
        desc = tool_input.get('description', '')
        if desc:
            summary += f": {truncate_text(desc, PATTERN_PREVIEW)}"

    elif tool_name == 'TodoWrite':
        todos = tool_input.get('todos', [])
        if todos:
            # Use Counter for status breakdown
            status_counts = Counter(todo.get('status', 'unknown') for todo in todos)
            status_str = ', '.join(f"{count} {status}" for status, count in status_counts.items())
            summary += f": {len(todos)} tasks ({status_str})"

    return summary


# ============================================================================
# TOOL INVOCATION AND RESULT HANDLERS
# ============================================================================

def handle_tool_invocation(
    tool_name: str,
    tool_id: str,
    tool_input: dict,
    timestamp: str,
    log_file: TextIO,
    tool_map: dict
) -> None:
    """
    Handle a tool invocation message - log to file and store summary for later.

    Args:
        tool_name: Name of the tool
        tool_id: Unique ID for this tool invocation
        tool_input: Tool input parameters
        timestamp: Timestamp string
        log_file: File to write logs to
        tool_map: Dictionary mapping tool IDs to summaries
    """
    tool_input_json = json.dumps(tool_input, indent=2)

    # Write to log file with box-drawing formatting
    write_to_log(log_file, f"\n[{timestamp}] TOOL INVOKED: {tool_name}\n")
    write_to_log(log_file, f"{BOX_TOP_LEFT_LIGHT}{BOX_HORIZONTAL_LIGHT} Input {BOX_HORIZONTAL_LIGHT * 40}\n")

    # Indent the JSON input
    for line in tool_input_json.split('\n'):
        write_to_log(log_file, f"{BOX_VERTICAL_LIGHT} {line}\n")

    # Store invocation time for duration calculation
    tool_map[tool_id] = {
        'summary': build_tool_summary(tool_name, tool_input),
        'timestamp': timestamp
    }


def handle_tool_result(
    tool_id: str,
    result_content: str,
    is_error: bool,
    timestamp: str,
    log_file: TextIO,
    tool_map: dict
) -> None:
    """
    Handle a tool result message - log to file and print to console.

    Args:
        tool_id: Tool use ID
        result_content: Result content string
        is_error: Whether this is an error result
        timestamp: Timestamp string
        log_file: File to write logs to
        tool_map: Dictionary mapping tool IDs to summaries
    """
    # Get tool info
    tool_info = tool_map.get(tool_id)

    if tool_info:
        # Calculate duration
        start_timestamp = tool_info.get('timestamp', timestamp)
        # Simple duration calculation (could be improved with proper time parsing)
        duration_str = '+0.00s'  # Placeholder - real calculation would require parsing timestamps

        # Truncate for log preview
        if len(result_content) > TRUNCATE_RESULT_PREVIEW:
            chars_omitted = len(result_content) - TRUNCATE_RESULT_PREVIEW
            result_preview = f"{result_content[:TRUNCATE_RESULT_PREVIEW]}... [{chars_omitted} more chars]"
        else:
            result_preview = result_content

        # Write to log file with box completion
        write_to_log(log_file, f"{BOX_LEFT_TEE_LIGHT_HEAVY}{BOX_HORIZONTAL_LIGHT} Result [{duration_str}] {BOX_HORIZONTAL_LIGHT * 20}\n")

        # Write result content
        if is_error:
            write_to_log(log_file, f"{BOX_VERTICAL_LIGHT} {chr(10006)} ERROR: {result_preview}\n")
        else:
            # Write result lines
            for line in result_preview.split('\n')[:10]:  # Show first 10 lines
                write_to_log(log_file, f"{BOX_VERTICAL_LIGHT} {line}\n")
            if result_preview.count('\n') > 10:
                remaining_lines = result_preview.count('\n') - 10
                write_to_log(log_file, f"{BOX_VERTICAL_LIGHT}   [... {remaining_lines} more lines ...]\n")

        write_to_log(log_file, f"{BOX_BOTTOM_LEFT_LIGHT}{BOX_HORIZONTAL_LIGHT * 44}{BOX_BOTTOM_RIGHT_LIGHT}\n")

        # Print result paired with original tool invocation
        tool_summary = tool_info.get('summary', '')
        console_print(tool_summary)
        formatted_result = format_tool_result(result_content, is_error, tool_summary)
        console_print(formatted_result)

        # Remove from map to avoid duplicate printing
        del tool_map[tool_id]
    else:
        # Fallback if tool_id not found
        write_to_log(log_file, f"[{timestamp}] [RESULT] {result_content[:200]}\n")
        formatted_result = format_tool_result(result_content, is_error, '')
        console_print(formatted_result)


def handle_final_result(json_obj: dict, timestamp: str, log_file: TextIO) -> None:
    """
    Handle a final result message - log to file and print to console.

    Args:
        json_obj: Parsed JSON object containing result
        timestamp: Timestamp string
        log_file: File to write logs to
    """
    subtype = json_obj.get('subtype', '')
    result = json_obj.get('result', '')
    duration_ms = json_obj.get('duration_ms', 0)
    num_turns = json_obj.get('num_turns', 0)

    # Write to log file
    write_to_log(log_file,
        f"[{timestamp}] [FINAL_RESULT] Status: {subtype}\n"
        f"[{timestamp}]   Duration: {duration_ms}ms\n"
        f"[{timestamp}]   Turns: {num_turns}\n"
        f"[{timestamp}]   Result: {result}\n"
    )

    # Print to console
    duration_sec = duration_ms / 1000
    console_print(f"\n--- Iteration Complete: {subtype} ---")
    console_print(f"Duration: {duration_sec:.1f}s | Turns: {num_turns}")


# ============================================================================
# LOGGING CLASSES
# ============================================================================

class TeeLogger:
    """Tee output to both console and log file."""

    def __init__(self, log_file: TextIO):
        self.log_file = log_file
        self.stdout = sys.stdout
        self.stderr = sys.stderr
        sys.stdout = self
        sys.stderr = self

    def write(self, message: str) -> None:
        """Write to both console and log file."""
        self.stdout.write(message)
        self.log_file.write(message)
        self.log_file.flush()

    def flush(self) -> None:
        """Flush both outputs."""
        self.stdout.flush()
        self.log_file.flush()

    def restore(self) -> None:
        """Restore original stdout/stderr."""
        sys.stdout = self.stdout
        sys.stderr = self.stderr


class DetailedLogger:
    """Enhanced logger with timestamps and structured logging."""

    def __init__(self, log_file: TextIO):
        self.log_file = log_file
        self.start_time: Optional[datetime] = None

    def log_event(self, event_type: str, message: str, **kwargs) -> None:
        """Log an event with timestamp and structured data."""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        elapsed = ""

        if self.start_time:
            elapsed_sec = (datetime.now() - self.start_time).total_seconds()
            elapsed = f" [+{elapsed_sec:.2f}s]"

        log_line = f"[{timestamp}]{elapsed} [{event_type}] {message}"

        if kwargs:
            log_line += " | " + " | ".join(f"{k}={v}" for k, v in kwargs.items())

        write_to_log(self.log_file, log_line + "\n")

    def start_timing(self) -> None:
        """Start timing for elapsed time calculations."""
        self.start_time = datetime.now()


# ============================================================================
# JSON STREAM PROCESSING
# ============================================================================

def process_json_line(
    line: str,
    timestamp: str,
    log_file: TextIO,
    tool_map: dict
) -> None:
    """
    Process a single JSON line from the output stream.

    Args:
        line: JSON line to process
        timestamp: Timestamp for logging
        log_file: Log file handle
        tool_map: Tool ID to summary mapping
    """
    try:
        json_obj = json.loads(line)
        msg_type = json_obj.get('type', '')

        if msg_type == 'assistant':
            # Handle tool invocations
            message = json_obj.get('message', {})
            content = message.get('content', [])

            for item in content:
                if item.get('type') == 'tool_use':
                    tool_name = item.get('name', 'unknown')
                    tool_id = item.get('id', '')
                    tool_input = item.get('input', {})
                    handle_tool_invocation(tool_name, tool_id, tool_input, timestamp, log_file, tool_map)

                elif item.get('type') == 'text':
                    text = item.get('text', '')
                    write_to_log(log_file, f"[{timestamp}] [TEXT] {text}\n")

        elif msg_type == 'user':
            # Handle tool results
            message = json_obj.get('message', {})
            content = message.get('content', [])

            for item in content:
                if item.get('type') == 'tool_result':
                    tool_id = item.get('tool_use_id', '')
                    result_content = item.get('content', '')
                    is_error = item.get('is_error', False)
                    handle_tool_result(tool_id, result_content, is_error, timestamp, log_file, tool_map)

        elif msg_type == 'result':
            handle_final_result(json_obj, timestamp, log_file)

        elif msg_type not in ['system']:
            # Log other types (truncated)
            if len(line) > TRUNCATE_JSON_LOG:
                write_to_log(log_file, f"[{timestamp}] [{msg_type.upper()}] {line[:TRUNCATE_JSON_LOG]}...\n")
            else:
                write_to_log(log_file, f"[{timestamp}] [{msg_type.upper()}] {line}\n")

    except (json.JSONDecodeError, KeyError, TypeError):
        # Not JSON or malformed, log as-is
        write_to_log(log_file, f"[{timestamp}] {line}\n")


def check_compaction_signal(line: str, logger: DetailedLogger) -> bool:
    """
    Check if line contains compaction signal.

    Args:
        line: Line to check
        logger: Logger for event logging

    Returns:
        True if compaction detected, False otherwise
    """
    line_lower = line.lower()
    for pattern in COMPACTION_PATTERNS:
        if pattern in line_lower:
            logger.log_event("COMPACTION_DETECTED", f"Detected compaction signal: {pattern}")
            return True
    return False


def stream_output_reader(
    pipe,
    output_list: list,
    stream_name: str,
    logger: DetailedLogger,
    timestamped_list: Optional[list] = None,
    compaction_event: Optional[threading.Event] = None,
    log_file: Optional[TextIO] = None
) -> None:
    """
    Read from pipe and append to output_list, logging with timestamps.

    Args:
        pipe: Pipe to read from
        output_list: List to append output lines
        stream_name: Name of stream (stdout/stderr)
        logger: Logger instance
        timestamped_list: Optional list for timestamped tuples
        compaction_event: Optional event to signal compaction
        log_file: Optional log file for real-time streaming
    """
    # Track tool_use_id -> summary mapping
    tool_map = {}

    try:
        while True:
            line = pipe.readline()
            if not line:
                break

            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
            output_list.append(line)

            if timestamped_list is not None:
                timestamped_list.append((timestamp, line))

            # Stream to log file in real-time (only for stdout)
            if log_file and stream_name == 'stdout':
                line_stripped = line.rstrip('\n')
                process_json_line(line_stripped, timestamp, log_file, tool_map)

            # Check for compaction signals
            if compaction_event and check_compaction_signal(line, logger):
                compaction_event.set()
                return

    except Exception as e:
        logger.log_event("ERROR", f"STREAM_READ_ERROR - Error reading {stream_name}: {e}")


def heartbeat_monitor(
    process,
    logger: DetailedLogger,
    interval: int = HEARTBEAT_INTERVAL,
    stop_event: Optional[threading.Event] = None
) -> None:
    """
    Monitor subprocess and log heartbeat to detect hangs.

    Args:
        process: Process to monitor
        logger: Logger instance
        interval: Heartbeat interval in seconds
        stop_event: Event to signal stop
    """
    iteration = 0
    while not stop_event.is_set():
        iteration += 1
        if process.poll() is None:
            logger.log_event("HEARTBEAT", f"Process still running (check #{iteration})")
        else:
            logger.log_event("HEARTBEAT", "Process completed, stopping heartbeat")
            break

        stop_event.wait(interval)


# ============================================================================
# SUBPROCESS MANAGEMENT
# ============================================================================

class StreamingSubprocess:
    """Context manager for subprocess with streaming output capture and heartbeat monitoring."""

    def __init__(
        self,
        cmd: list,
        env: dict,
        logger: Optional[DetailedLogger],
        timeout: int,
        log_file: Optional[TextIO] = None
    ):
        self.cmd = cmd
        self.env = env
        self.logger = logger or DetailedLogger(open('/dev/null', 'w'))
        self.timeout = timeout
        self.log_file = log_file
        self.process = None
        self.stdout_lines: list = []
        self.stderr_lines: list = []
        self.timestamped_stdout: list = []
        self.stop_event = threading.Event()
        self.compaction_event = threading.Event()
        self.threads: list = []

    def __enter__(self):
        """Start subprocess and monitoring threads."""
        self.process = subprocess.Popen(
            self.cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=self.env,
            bufsize=1  # Line buffered
        )

        # Start reader and heartbeat threads
        stdout_thread = threading.Thread(
            target=stream_output_reader,
            args=(
                self.process.stdout,
                self.stdout_lines,
                'stdout',
                self.logger,
                self.timestamped_stdout,
                self.compaction_event,
                self.log_file
            )
        )
        stderr_thread = threading.Thread(
            target=stream_output_reader,
            args=(
                self.process.stderr,
                self.stderr_lines,
                'stderr',
                self.logger,
                None,
                self.compaction_event,
                None
            )
        )
        heartbeat_thread = threading.Thread(
            target=heartbeat_monitor,
            args=(self.process, self.logger, HEARTBEAT_INTERVAL, self.stop_event)
        )

        for t in [stdout_thread, stderr_thread, heartbeat_thread]:
            t.daemon = True
            t.start()

        self.threads = [stdout_thread, stderr_thread, heartbeat_thread]
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Clean up threads."""
        self.stop_event.set()
        for t in self.threads:
            t.join(timeout=THREAD_JOIN_TIMEOUT)
        return False

    def wait_with_timeout(self) -> tuple[int, str, str, list, bool]:
        """
        Wait for process to complete with timeout.

        Returns:
            Tuple of (returncode, stdout_text, stderr_text, timestamped_stdout, compaction_detected)

        Raises:
            subprocess.TimeoutExpired: If timeout is exceeded
        """
        elapsed = 0.0

        while elapsed < self.timeout:
            # Check if compaction was detected
            if self.compaction_event.is_set():
                self.logger.log_event("COMPACTION_KILL", "Killing process due to compaction detection")
                self.process.terminate()

                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait()

                stdout_text = ''.join(self.stdout_lines)
                stderr_text = ''.join(self.stderr_lines)
                return 0, stdout_text, stderr_text, self.timestamped_stdout, True

            # Check if process completed naturally
            returncode = self.process.poll()
            if returncode is not None:
                stdout_text = ''.join(self.stdout_lines)
                stderr_text = ''.join(self.stderr_lines)
                return returncode, stdout_text, stderr_text, self.timestamped_stdout, False

            time.sleep(POLL_INTERVAL)
            elapsed += POLL_INTERVAL

        # Timeout reached
        raise subprocess.TimeoutExpired(self.cmd, self.timeout)

    def kill(self) -> tuple[str, str, list, bool]:
        """
        Kill the process and return captured output.

        Returns:
            Tuple of (stdout_text, stderr_text, timestamped_stdout, compaction_detected)
        """
        self.process.kill()
        self.process.wait()
        stdout_text = ''.join(self.stdout_lines)
        stderr_text = ''.join(self.stderr_lines)
        compaction_detected = self.compaction_event.is_set()
        return stdout_text, stderr_text, self.timestamped_stdout, compaction_detected


# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class IterationResult:
    """Result from a single agent iteration."""
    success: bool
    output: str
    error: Optional[str] = None
    iteration_num: int = 0
    max_turns_reached: bool = False
    timeout_occurred: bool = False
    compaction_detected: bool = False
    feedback_summary: Optional[str] = None
    input_tokens: int = 0
    output_tokens: int = 0
    duration_seconds: float = 0.0
    timestamp: str = ""
    timestamped_lines: Optional[list] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        # Use dataclasses.asdict but customize some fields
        base_dict = asdict(self)
        base_dict['has_error'] = self.error is not None
        base_dict['output_length'] = len(self.output)
        base_dict['error_length'] = len(self.error) if self.error else 0
        # Remove large fields from dict
        del base_dict['output']
        del base_dict['error']
        del base_dict['timestamped_lines']
        return base_dict


# ============================================================================
# TOOL PARSING
# ============================================================================

def parse_tool_use_from_output(output: str) -> list:
    """
    Parse tool use and results from Claude CLI JSON output.
    Returns list of dicts with tool information including errors and return codes.
    """
    tools = []
    tool_map = {}

    for line in output.split('\n'):
        line = line.strip()
        if not line:
            continue

        try:
            json_obj = json.loads(line)
            msg_type = json_obj.get('type', '')

            if msg_type == 'assistant':
                # Extract tool invocations
                message = json_obj.get('message', {})
                content = message.get('content', [])

                for item in content:
                    if item.get('type') == 'tool_use':
                        tool_id = item.get('id', '')
                        tool_name = item.get('name', '')
                        tool_input = item.get('input', {})

                        tool_info = {
                            'type': 'tool_use',
                            'name': tool_name,
                            'input': truncate_text(
                                json.dumps(tool_input, indent=2),
                                TRUNCATE_TOOL_INPUT,
                                smart=False,
                                indicator=f"\n... [truncated, {len(json.dumps(tool_input)) - TRUNCATE_TOOL_INPUT} more chars]"
                            ),
                            'result': '',
                            'has_error': False,
                            'return_code': None,
                            'error_message': ''
                        }

                        tool_map[tool_id] = tool_info
                        tools.append(tool_info)

            elif msg_type == 'user':
                # Extract tool results
                message = json_obj.get('message', {})
                content = message.get('content', [])

                for item in content:
                    if item.get('type') == 'tool_result':
                        tool_id = item.get('tool_use_id', '')
                        result_content = item.get('content', '')

                        if tool_id in tool_map:
                            tool_info = tool_map[tool_id]

                            # Check for errors
                            if any(indicator in result_content for indicator in ERROR_INDICATORS):
                                tool_info['has_error'] = True
                                error_match = re.search(r'<error>(.*?)</error>', result_content, re.DOTALL)
                                if error_match:
                                    tool_info['error_message'] = truncate_text(
                                        error_match.group(1).strip(),
                                        TRUNCATE_ERROR_MSG
                                    )

                            # For Bash tool, extract exit code
                            if tool_info['name'] == 'Bash':
                                exit_match = EXIT_CODE_PATTERN.search(result_content)
                                if exit_match:
                                    tool_info['return_code'] = int(exit_match.group(1))
                                    if tool_info['return_code'] != 0:
                                        tool_info['has_error'] = True

                            tool_info['result'] = truncate_text(
                                result_content,
                                TRUNCATE_TOOL_RESULT,
                                smart=False,
                                indicator=f"\n... [truncated, {len(result_content) - TRUNCATE_TOOL_RESULT} more chars]"
                            )

        except (json.JSONDecodeError, KeyError, TypeError):
            continue

    return tools


# ============================================================================
# CLI EXECUTION
# ============================================================================

def run_cli_iteration(
    cmd: list,
    cli_name: str,
    prompt: str,
    timeout: int,
    log_file: Optional[TextIO]
) -> IterationResult:
    """
    Run CLI iteration with streaming output.

    Args:
        cmd: Command and arguments to execute
        cli_name: Name of CLI being run (for error messages)
        prompt: The prompt being sent
        timeout: Timeout in seconds
        log_file: Optional log file handle

    Returns:
        IterationResult with execution details
    """
    # Set YOLO mode environment
    env = os.environ.copy()
    env['CLAUDE_CODE_YOLO'] = '1'

    # Initialize logger
    logger = DetailedLogger(log_file) if log_file else None

    # Log command to file
    if log_file:
        write_log_box_divider(log_file, 67, heavy=False)
        cmd_str = ' '.join(cmd)
        if len(cmd_str) > 60:
            cmd_str = cmd_str[:60] + '...'
        write_log_box_line(log_file, f"Command: {cmd_str}")
        write_log_box_line(log_file, f"Environment: CLAUDE_CODE_YOLO={env.get('CLAUDE_CODE_YOLO')}")
        write_log_box_line(log_file, f"Timeout: {timeout}s | Prompt: {len(prompt)} chars")
        write_log_box_divider(log_file, 67, heavy=False)
        write_log_box_line(log_file, "Streaming Output (real-time)")
        write_log_box_divider(log_file, 67, heavy=False)

    if logger:
        logger.start_timing()
        logger.log_event("SUBPROCESS_START", "Starting subprocess", cmd=" ".join(cmd))

    execution_start = datetime.now()
    timestamp_str = execution_start.strftime('%Y-%m-%d %H:%M:%S')

    try:
        with StreamingSubprocess(cmd, env, logger, timeout, log_file) as proc:
            try:
                returncode, stdout_text, stderr_text, timestamped_stdout, compaction_detected = proc.wait_with_timeout()
                duration = (datetime.now() - execution_start).total_seconds()

                if logger:
                    logger.log_event("SUBPROCESS_END", "Subprocess completed",
                                   returncode=returncode, duration_sec=f"{duration:.2f}")

                # Log completion metadata
                if log_file:
                    write_to_log(log_file, "\n")
                    write_log_box_divider(log_file, 67, heavy=False)
                    write_log_box_line(log_file, f"Streaming Complete | Return code: {returncode} | Duration: {duration:.2f}s")

                    if compaction_detected:
                        write_log_box_line(log_file, f"{chr(9888)} COMPACTION DETECTED - Iteration terminated early")

                    if stderr_text.strip():
                        write_log_box_line(log_file, f"STDERR: {len(stderr_text)} chars logged")
                        write_to_log(log_file, f"\n{stderr_text}\n")

                    write_log_box_divider(log_file, 67, heavy=False)

                # Check for max turns error
                combined_output = stdout_text + stderr_text
                max_turns_reached = 'max turns' in combined_output.lower() or 'reached max turns' in combined_output.lower()

                if max_turns_reached and logger:
                    logger.log_event("MAX_TURNS", "Max turns limit reached")

                return IterationResult(
                    success=returncode == 0 and not compaction_detected,
                    output=stdout_text,
                    error=stderr_text if returncode != 0 else None,
                    max_turns_reached=max_turns_reached,
                    compaction_detected=compaction_detected,
                    input_tokens=estimate_tokens(prompt),
                    output_tokens=estimate_tokens(stdout_text),
                    duration_seconds=duration,
                    timestamp=timestamp_str,
                    timestamped_lines=timestamped_stdout
                )

            except subprocess.TimeoutExpired:
                duration = (datetime.now() - execution_start).total_seconds()
                if logger:
                    logger.log_event("TIMEOUT", f"Subprocess exceeded timeout of {timeout}s")

                # Kill process and get partial output
                stdout_text, stderr_text, timestamped_stdout, compaction_detected = proc.kill()

                error_msg = f'Iteration timed out after {timeout} seconds'

                if log_file:
                    write_to_log(log_file, "\n")
                    write_log_box_divider(log_file, 67, heavy=False)
                    write_log_box_line(log_file, f"{chr(10060)} TIMEOUT ERROR: {error_msg}")
                    write_log_box_line(log_file, f"Duration: {duration:.2f}s")

                    if compaction_detected:
                        write_log_box_line(log_file, f"{chr(9888)} COMPACTION DETECTED during timeout")

                    if stderr_text.strip():
                        write_log_box_line(log_file, f"Partial STDERR: {len(stderr_text)} chars")
                        write_to_log(log_file, f"\n{stderr_text}\n")

                    write_log_box_divider(log_file, 67, heavy=False)

                return IterationResult(
                    success=False,
                    output=stdout_text,
                    error=error_msg,
                    timeout_occurred=True,
                    compaction_detected=compaction_detected,
                    input_tokens=estimate_tokens(prompt),
                    output_tokens=estimate_tokens(stdout_text),
                    duration_seconds=duration,
                    timestamp=timestamp_str,
                    timestamped_lines=timestamped_stdout
                )

    except Exception as e:
        duration = (datetime.now() - execution_start).total_seconds()
        error_msg = f'Failed to run {cli_name}: {type(e).__name__}: {e}'

        if logger:
            logger.log_event("ERROR", f"EXCEPTION - {error_msg}")

        if log_file:
            import traceback
            write_to_log(log_file, "\n")
            write_log_box_divider(log_file, 67, heavy=False)
            write_log_box_line(log_file, f"{chr(10060)} EXCEPTION: {error_msg}")
            write_log_box_line(log_file, f"Duration: {duration:.2f}s")
            write_log_box_divider(log_file, 67, heavy=False)
            write_to_log(log_file, f"\n{traceback.format_exc()}\n")

        return IterationResult(
            success=False,
            output='',
            error=error_msg,
            input_tokens=estimate_tokens(prompt),
            output_tokens=0,
            duration_seconds=duration,
            timestamp=timestamp_str,
            timestamped_lines=[]
        )


def run_claude_iteration(
    prompt: str,
    model: str = 'opus',
    max_turns: int = 50,
    timeout: int = 600,
    log_file: Optional[TextIO] = None,
    system_prompt: Optional[str] = None
) -> IterationResult:
    """Run one iteration using Claude Code CLI."""
    cmd = [
        'claude',
        '--print',
        '--dangerously-skip-permissions',
        '--max-turns', str(max_turns),
        '--model', model,
        '--output-format', 'stream-json',
        '--verbose'
    ]

    if system_prompt:
        cmd.extend(['--system-prompt', system_prompt])

    cmd.extend(['-p', prompt])

    return run_cli_iteration(cmd, 'claude', prompt, timeout, log_file)


def run_codex_iteration(
    prompt: str,
    timeout: int = 600,
    log_file: Optional[TextIO] = None
) -> IterationResult:
    """Run one iteration using Codex CLI."""
    cmd = ['codex', 'exec', '-s', 'danger-full-access', prompt]
    return run_cli_iteration(cmd, 'codex', prompt, timeout, log_file)


# ============================================================================
# ITERATION LOGGING
# ============================================================================

def write_iteration_to_log(log_file: TextIO, result: IterationResult, command: list, max_iterations: int, model: str = None) -> None:
    """Write iteration summary with consolidated metadata block."""
    write_to_log(log_file, "\n")

    # Top border
    line = BOX_HORIZONTAL_HEAVY * 65
    write_to_log(log_file, f"{BOX_TOP_LEFT}{line}{BOX_TOP_RIGHT}\n")

    # Title line
    write_log_box_line(log_file, f"Iteration {result.iteration_num}/{max_iterations} | Started: {result.timestamp}")

    # Divider
    write_log_box_divider(log_file, 67, heavy=True)

    # Configuration section
    write_log_box_line(log_file, "Configuration:")
    cmd_str = ' '.join(command)
    if len(cmd_str) > 60:
        cmd_str = cmd_str[:60] + '...'
    write_log_box_line(log_file, f"  CLI: {cmd_str}")
    if model:
        write_log_box_line(log_file, f"  Model: {model}")
    write_log_box_line(log_file, f"  Prompt size: {result.input_tokens * 4} chars ({result.input_tokens:,} tokens est.)")

    # Divider
    write_log_box_divider(log_file, 67, heavy=True)

    # Result section
    status_icon = chr(9989) if result.success else chr(10060)  # ✅ or ❌
    status_text = 'Success' if result.success else 'Failed'
    write_log_box_line(log_file, f"Result: {status_icon} {status_text} | Duration: {result.duration_seconds:.2f}s")

    # Token usage
    total_tokens = result.input_tokens + result.output_tokens
    write_log_box_line(log_file, f"Tokens: {result.input_tokens:,} in {chr(8594)} {result.output_tokens:,} out {chr(8594)} {total_tokens:,} total")

    # Exit reason / warnings
    if result.compaction_detected:
        write_log_box_line(log_file, "Exit reason: Compaction detected")
    elif result.max_turns_reached:
        write_log_box_line(log_file, "Exit reason: Max turns reached")
    elif result.timeout_occurred:
        write_log_box_line(log_file, "Exit reason: Timeout")
    elif not result.success:
        write_log_box_line(log_file, "Exit reason: Error")
    else:
        write_log_box_line(log_file, "Exit reason: Natural completion")

    # Bottom border
    write_to_log(log_file, f"{BOX_BOTTOM_LEFT}{line}{BOX_BOTTOM_RIGHT}\n")

    # Errors if any
    if result.error:
        write_to_log(log_file, f"\n{chr(10060)} ERROR DETAILS:\n")
        write_to_log(log_file, f"{result.error}\n")


# ============================================================================
# FEEDBACK AND STATUS CHECKING
# ============================================================================

def extract_iteration_feedback(result: IterationResult) -> str:
    """Extract feedback from iteration result to pass to next iteration."""
    feedback_parts = []

    if result.compaction_detected:
        feedback_parts.append(
            "⚠️ PREVIOUS ITERATION DETECTED CONVERSATION COMPACTION\n"
            "The last iteration was stopped early because Claude was about to compact the conversation.\n"
            "This indicates the context window was getting full.\n"
            "GUIDANCE: The iteration was terminated to preserve context. Continue with the next task."
        )

    if result.max_turns_reached:
        feedback_parts.append(
            "⚠️ PREVIOUS ITERATION HIT MAX TURNS LIMIT\n"
            "The last iteration was stopped because it reached the maximum turn limit.\n"
            "This usually means the plan has tasks that are too large or complex.\n"
            "GUIDANCE: Break down the current task into smaller, more focused steps."
        )

    if result.timeout_occurred:
        feedback_parts.append(
            "⚠️ PREVIOUS ITERATION TIMED OUT\n"
            "The last iteration exceeded the time limit.\n"
            "GUIDANCE: Simplify the current task or break it into smaller pieces."
        )

    if result.error and not (result.max_turns_reached or result.timeout_occurred or result.compaction_detected):
        feedback_parts.append(
            f"⚠️ PREVIOUS ITERATION ENCOUNTERED AN ERROR\n"
            f"Error: {result.error[:500]}\n"
            f"GUIDANCE: Address this error before proceeding."
        )

    if not feedback_parts and result.success:
        return "✅ Previous iteration completed successfully."

    return "\n\n".join(feedback_parts) if feedback_parts else "No feedback from previous iteration."


def check_for_commit(result: IterationResult) -> bool:
    """Check if a commit was made during this iteration."""
    if 'git commit' in result.output.lower():
        return True

    try:
        log_result = subprocess.run(
            ['git', 'log', '-1', '--pretty=%H', '--since=30 seconds ago'],
            capture_output=True,
            text=True,
            timeout=3
        )
        return bool(log_result.stdout.strip())
    except Exception:
        return False


def check_completion(result: IterationResult) -> bool:
    """Check if the agent emitted the completion signal."""
    return COMPLETION_SIGNAL_TEXT in result.output and COMPLETION_SIGNAL_EMOJI in result.output


# ============================================================================
# PROMPT MANAGEMENT
# ============================================================================

def load_outer_prompt(outer_prompt_path: str) -> str:
    """Load outer prompt template from file."""
    try:
        return Path(outer_prompt_path).read_text(encoding='utf-8')
    except FileNotFoundError:
        print(f"❌ Error: Outer prompt file not found: {outer_prompt_path}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error reading outer prompt file: {e}", file=sys.stderr)
        sys.exit(1)


def create_wrapped_prompt(
    user_prompt: str,
    iteration_num: int,
    outer_prompt_template: str,
    feedback: Optional[str] = None
) -> str:
    """Wrap user prompt with Ralph Loop instructions from template."""
    feedback_section = ""
    if feedback and iteration_num > 1:
        separator = "=" * 60
        feedback_section = f"\n\n{separator}\nFEEDBACK FROM PREVIOUS ITERATION:\n{separator}\n{feedback}\n{separator}\n"

    return outer_prompt_template.format(
        iteration_num=iteration_num,
        user_prompt=user_prompt,
        feedback=feedback_section
    )


def install_user_prompts(force: bool = False) -> None:
    """Copy default prompts from package to ~/.ralph/prompts/."""
    user_prompts_dir = Path.home() / '.ralph' / 'prompts'
    package_prompts_dir = Path(__file__).parent / 'prompts'

    if user_prompts_dir.exists() and not force:
        return  # Already installed

    user_prompts_dir.mkdir(parents=True, exist_ok=True)

    for prompt_file in package_prompts_dir.glob('*.md'):
        dest = user_prompts_dir / prompt_file.name
        dest.write_text(prompt_file.read_text(encoding='utf-8'))

    print(f"✓ Initialized prompts to {user_prompts_dir}")


def ensure_prompts_installed() -> None:
    """Auto-install prompts to ~/.ralph/prompts/ if not already present."""
    user_prompts_dir = Path.home() / '.ralph' / 'prompts'
    if not user_prompts_dir.exists():
        install_user_prompts(force=True)


def get_default_outer_prompt_path() -> Path:
    """Get default outer prompt, ensuring it's installed to ~/.ralph/prompts/."""
    ensure_prompts_installed()
    user_prompts = Path.home() / '.ralph' / 'prompts' / 'outer-prompt-default.md'

    if not user_prompts.exists():
        raise FileNotFoundError(
            f"Could not find outer-prompt-default.md at {user_prompts}. "
            "Run 'ralph --init' to reinstall default prompts."
        )

    return user_prompts


# ============================================================================
# HUMAN IN THE LOOP
# ============================================================================

def human_in_the_loop() -> bool:
    """Pause for human review. Returns True to continue, False to stop."""
    separator = "=" * 60
    print(f"\n{separator}")
    print("🤚 HUMAN IN THE LOOP - Pausing for review")
    print(separator)
    print("Options:")
    print("  [c] Continue to next iteration")
    print("  [s] Stop the loop")
    print("  [g] Show git status")
    print("  [l] Show git log (last 5 commits)")

    while True:
        choice = input("\nYour choice: ").strip().lower()

        if choice == 'c':
            return True
        elif choice == 's':
            print("🛑 Stopping loop at user request")
            return False
        elif choice == 'g':
            subprocess.run(['git', 'status'])
        elif choice == 'l':
            subprocess.run(['git', 'log', '-5', '--oneline'])
        else:
            print("Invalid choice. Please enter c, s, g, or l")


# ============================================================================
# MAIN LOOP EXECUTION
# ============================================================================

def setup_argument_parser() -> argparse.ArgumentParser:
    """Create and configure argument parser."""
    parser = argparse.ArgumentParser(
        description='Ralph Loop: Iterative AI agent execution',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s "Fix all type errors" --max-iterations 15
  %(prog)s -f prompt.md --max-iterations 20
  %(prog)s "Implement auth" --max-iterations 20 --max-turns 20 --human-in-the-loop
  %(prog)s "Complete all tasks in PRD.md" --max-iterations 40 --max-turns 25 --model sonnet
  %(prog)s "Run tests" --max-iterations 5 --model haiku
  %(prog)s "Build feature" --system-prompt "You are an expert Python developer"
        """
    )

    parser.add_argument('prompt', nargs='?', help='The task prompt to feed to the agent')
    parser.add_argument('-f', '--prompt-file', type=str, help='Read the prompt from a file')
    parser.add_argument('--max-iterations', type=int, default=10, help='Maximum number of iterations (default: 10)')
    parser.add_argument('--max-turns', type=int, default=50, help='Maximum turns per iteration for Claude CLI (default: 50)')
    parser.add_argument('--human-in-the-loop', action='store_true', help='Pause after each iteration for human review')
    parser.add_argument('--model', choices=['opus', 'sonnet', 'haiku'], default='opus', help='Model to use for Claude CLI (default: opus)')
    parser.add_argument('--cli-type', choices=['claude', 'codex'], default='claude', help='Which CLI to use (default: claude)')
    parser.add_argument('--timeout', type=int, default=600, help='Timeout in seconds for each iteration (default: 600 = 10 minutes)')
    parser.add_argument('--log-file', type=str, default=None, help='Path to log file (default: /tmp/ralph_[work-dir-basename]_[timestamp]_iteration.log)')
    parser.add_argument('--outer-prompt', type=str, default=None, help='Path to outer prompt template file (default: ~/.ralph/prompts/outer-prompt-default.md)')
    parser.add_argument('--system-prompt', type=str, default=None, help='System prompt to pass to Claude CLI')
    parser.add_argument('--init', action='store_true', help='Install default prompts to ~/.ralph/prompts/ for customization')
    parser.add_argument('--version', action='version', version=f'%(prog)s {__version__}')

    return parser


def validate_git_repository() -> bool:
    """Check if we're in a git repository."""
    try:
        subprocess.run(
            ['git', 'rev-parse', '--git-dir'],
            check=True,
            capture_output=True
        )
        return True
    except subprocess.CalledProcessError:
        print("❌ Error: Not in a git repository", file=sys.stderr)
        return False


def print_iteration_stats(iteration: int, result: IterationResult) -> None:
    """Print token usage statistics for iteration."""
    print(f"\n📊 Iteration {iteration} tokens:")
    print(f"   Input:  {result.input_tokens:,} tokens")
    print(f"   Output: {result.output_tokens:,} tokens")
    print(f"   Total:  {result.input_tokens + result.output_tokens:,} tokens")


def print_final_summary(
    start_time: datetime,
    iteration: int,
    max_iterations: int,
    cumulative_input_tokens: int,
    cumulative_output_tokens: int,
    log_file_path: str
) -> None:
    """Print final summary statistics."""
    elapsed = datetime.now() - start_time
    total_tokens = cumulative_input_tokens + cumulative_output_tokens

    print(f"\n⏱️  Total time: {elapsed}")
    print(f"🔢 Iterations completed: {iteration}")
    print(f"\n📊 Total token usage (estimated):")
    print(f"   Input:  {cumulative_input_tokens:,} tokens")
    print(f"   Output: {cumulative_output_tokens:,} tokens")
    print(f"   Total:  {total_tokens:,} tokens")

    # Show final git status
    print("\n📊 Final git status:")
    subprocess.run(['git', 'status', '--short'])

    # Show progress.md if it exists
    progress_file = Path('progress.md')
    if progress_file.exists():
        print("\n📝 Current progress.md:")
        print("-" * 60)
        print(progress_file.read_text())


def write_run_summary(
    log_file: TextIO,
    args: argparse.Namespace,
    start_time: datetime,
    iteration: int,
    cumulative_input_tokens: int,
    cumulative_output_tokens: int
) -> None:
    """Write run summary to log file."""
    total_tokens = cumulative_input_tokens + cumulative_output_tokens
    elapsed = datetime.now() - start_time

    write_to_log(log_file, "\n\n")
    line = BOX_HORIZONTAL_HEAVY * 65
    write_to_log(log_file, f"{BOX_TOP_LEFT}{line}{BOX_TOP_RIGHT}\n")
    write_log_box_line(log_file, "RALPH LOOP RUN SUMMARY")
    write_log_box_divider(log_file, 67, heavy=True)

    write_log_box_line(log_file, f"Task: {args.prompt[:55]}{'...' if len(args.prompt) > 55 else ''}")
    write_log_box_line(log_file, f"Start: {start_time.strftime('%Y-%m-%d %H:%M:%S')} | End: {datetime.now().strftime('%H:%M:%S')}")
    write_log_box_line(log_file, f"Total elapsed: {elapsed}")
    write_log_box_line(log_file, f"Iterations: {iteration}/{args.max_iterations}")

    write_log_box_divider(log_file, 67, heavy=False)
    write_log_box_line(log_file, "Token Usage (estimated):")
    write_log_box_line(log_file, f"  Input:  {cumulative_input_tokens:,} tokens")
    write_log_box_line(log_file, f"  Output: {cumulative_output_tokens:,} tokens")
    write_log_box_line(log_file, f"  Total:  {total_tokens:,} tokens")

    write_log_box_divider(log_file, 67, heavy=False)
    write_log_box_line(log_file, "Configuration:")
    write_log_box_line(log_file, f"  CLI: {args.cli_type}")

    if args.cli_type == 'claude':
        write_log_box_line(log_file, f"  Model: {args.model}")
        if args.system_prompt:
            prompt_preview = args.system_prompt[:50] + ('...' if len(args.system_prompt) > 50 else '')
            write_log_box_line(log_file, f"  System prompt: {prompt_preview}")

    write_log_box_line(log_file, f"  Max turns: {args.max_turns} | Timeout: {args.timeout}s")

    write_to_log(log_file, f"{BOX_BOTTOM_LEFT}{line}{BOX_BOTTOM_RIGHT}\n")


def main() -> int:
    """Main entry point for Ralph Loop."""
    parser = setup_argument_parser()
    args = parser.parse_args()

    # Handle init command
    if args.init:
        install_user_prompts(force=True)
        return 0

    # Set default outer prompt path
    if args.outer_prompt is None:
        args.outer_prompt = str(get_default_outer_prompt_path())

    # Load outer prompt template
    outer_prompt_template = load_outer_prompt(args.outer_prompt)

    # Handle prompt from file or command line
    if args.prompt_file:
        try:
            args.prompt = Path(args.prompt_file).read_text(encoding='utf-8').strip()
        except FileNotFoundError:
            print(f"❌ Error: Prompt file not found: {args.prompt_file}", file=sys.stderr)
            return 1
        except Exception as e:
            print(f"❌ Error reading prompt file: {e}", file=sys.stderr)
            return 1
    elif not args.prompt:
        parser.error("Either provide a prompt argument or use --prompt-file/-f")

    # Validate git repository
    if not validate_git_repository():
        return 1

    # Set up log file
    if args.log_file is None:
        args.log_file = create_log_file_path()

    log_file = open(args.log_file, 'w', encoding='utf-8')
    logger = TeeLogger(log_file)

    try:
        separator = "=" * 60
        print("🚀 Ralph Loop Starting")
        print(f"📝 Log file: {args.log_file}")
        print(f"Task: {args.prompt}")
        print(f"Max iterations: {args.max_iterations}")
        print(f"Max turns per iteration: {args.max_turns}")
        print(f"Timeout per iteration: {args.timeout} seconds")
        print(f"CLI: {args.cli_type}")

        if args.cli_type == 'claude':
            print(f"Model: {args.model}")
            if args.system_prompt:
                print(f"System prompt: {args.system_prompt}")

        print(f"Human-in-the-loop: {args.human_in_the_loop}")
        print(separator)

        # Calculate and display initial token count
        initial_prompt = create_wrapped_prompt(args.prompt, 1, outer_prompt_template, None)
        initial_tokens = estimate_tokens(initial_prompt)
        print(f"\n📊 Initial prompt size: {initial_tokens:,} tokens (estimated)")
        print(separator)

        # Print initial prompt once
        print(f"\n{separator}")
        print("INITIAL WRAPPED PROMPT")
        print(separator)
        print(initial_prompt)
        print(separator)

        # Write initial configuration to log with box formatting
        line = BOX_HORIZONTAL_HEAVY * 65
        write_to_log(log_file, f"{BOX_TOP_LEFT}{line}{BOX_TOP_RIGHT}\n")
        write_log_box_line(log_file, "RALPH LOOP EXECUTION")
        write_log_box_divider(log_file, 67, heavy=True)
        write_log_box_line(log_file, "Initial Configuration")
        write_log_box_divider(log_file, 67, heavy=False)

        write_log_box_line(log_file, f"Task: {args.prompt[:55]}{'...' if len(args.prompt) > 55 else ''}")
        write_log_box_line(log_file, f"Start time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        write_log_box_line(log_file, f"Max iterations: {args.max_iterations} | Max turns: {args.max_turns} | Timeout: {args.timeout}s")
        write_log_box_line(log_file, f"CLI: {args.cli_type}")

        if args.cli_type == 'claude':
            write_log_box_line(log_file, f"Model: {args.model}")
            if args.system_prompt:
                write_log_box_line(log_file, f"System prompt: {args.system_prompt[:50]}{'...' if len(args.system_prompt) > 50 else ''}")

        write_log_box_line(log_file, f"Prompt size: {len(initial_prompt)} chars ({initial_tokens:,} tokens est.)")

        write_log_box_divider(log_file, 67, heavy=False)
        write_log_box_line(log_file, "Streaming Output (real-time)")
        write_log_box_divider(log_file, 67, heavy=True)
        write_to_log(log_file, "\n")

        # Main loop
        start_time = datetime.now()
        previous_result: Optional[IterationResult] = None
        previous_prompt: Optional[str] = None
        cumulative_input_tokens = 0
        cumulative_output_tokens = 0

        for iteration in range(1, args.max_iterations + 1):
            print(f"\n🔄 Iteration {iteration}/{args.max_iterations}")
            print(f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print("-" * 60)

            # Extract feedback and create wrapped prompt
            feedback = extract_iteration_feedback(previous_result) if previous_result else None
            wrapped_prompt = create_wrapped_prompt(args.prompt, iteration, outer_prompt_template, feedback)

            # Log prompt with diff for iterations > 1
            if iteration == 1:
                # First iteration - log full prompt
                write_to_log(log_file, "\n")
                line = BOX_HORIZONTAL_HEAVY * 65
                write_to_log(log_file, f"{BOX_TOP_LEFT}{line}{BOX_TOP_RIGHT}\n")
                write_log_box_line(log_file, f"Iteration 1 Prompt ({len(wrapped_prompt)} chars)")
                write_to_log(log_file, f"{BOX_LEFT_TEE_HEAVY}{line}{BOX_RIGHT_TEE_HEAVY}\n")
                write_to_log(log_file, wrapped_prompt + "\n")
                write_to_log(log_file, f"{BOX_BOTTOM_LEFT}{line}{BOX_BOTTOM_RIGHT}\n")
            elif iteration > 1 and previous_prompt:
                # Subsequent iterations - show diff
                diff_lines, unchanged_chars = compute_prompt_diff(previous_prompt, wrapped_prompt)
                char_delta = len(wrapped_prompt) - len(previous_prompt)
                delta_str = f"+{char_delta}" if char_delta >= 0 else str(char_delta)

                write_to_log(log_file, "\n")
                line = BOX_HORIZONTAL_HEAVY * 65
                write_to_log(log_file, f"{BOX_TOP_LEFT}{line}{BOX_TOP_RIGHT}\n")
                write_log_box_line(log_file, f"Iteration {iteration} Prompt ({len(wrapped_prompt)} chars, {delta_str} chars)")
                write_to_log(log_file, f"{BOX_LEFT_TEE_HEAVY}{line}{BOX_RIGHT_TEE_HEAVY}\n")

                if diff_lines:
                    write_log_box_line(log_file, "[CHANGES FROM PREVIOUS ITERATION]")
                    for line_content in diff_lines[:20]:  # Show first 20 diff lines
                        write_to_log(log_file, f"{BOX_VERTICAL_HEAVY} {line_content}\n")
                    if len(diff_lines) > 20:
                        write_log_box_line(log_file, f"... [{len(diff_lines) - 20} more diff lines]")

                    if unchanged_chars > 0:
                        write_log_box_line(log_file, "")
                        write_log_box_line(log_file, f"[UNCHANGED SECTIONS - {unchanged_chars:,} chars omitted, see Iteration 1]")
                else:
                    write_log_box_line(log_file, "[NO CHANGES FROM PREVIOUS ITERATION]")

                write_to_log(log_file, f"{BOX_BOTTOM_LEFT}{line}{BOX_BOTTOM_RIGHT}\n")

            # Save current prompt for next iteration
            previous_prompt = wrapped_prompt

            # Run iteration
            if args.cli_type == 'claude':
                result = run_claude_iteration(wrapped_prompt, args.model, args.max_turns, args.timeout, log_file, args.system_prompt)
            else:
                result = run_codex_iteration(wrapped_prompt, args.timeout, log_file)

            result.iteration_num = iteration

            # Build command for logging
            if args.cli_type == 'claude':
                cmd_used = ['claude', '--print', '--dangerously-skip-permissions',
                           '--max-turns', str(args.max_turns), '--model', args.model]
                if args.system_prompt:
                    cmd_used.extend(['--system-prompt', args.system_prompt])
                cmd_used.extend(['-p', '[prompt]'])
            else:
                cmd_used = ['codex', 'exec', '-s', 'danger-full-access', '[prompt]']

            write_iteration_to_log(log_file, result, cmd_used, args.max_iterations, args.model if args.cli_type == 'claude' else None)

            # Update cumulative tokens
            cumulative_input_tokens += result.input_tokens
            cumulative_output_tokens += result.output_tokens

            print_iteration_stats(iteration, result)
            previous_result = result

            # Handle compaction
            if result.compaction_detected:
                print(f"\n{separator}")
                print("⚠️  COMPACTION DETECTED")
                print(separator)
                print("Claude was about to compact the conversation.")
                print("Iteration terminated early to preserve context.")
                print("Moving to next iteration...")
                print(separator)

                if args.human_in_the_loop and not human_in_the_loop():
                    break
                continue

            # Handle errors
            if not result.success:
                print(f"❌ Iteration {iteration} failed", file=sys.stderr)

                if result.error:
                    print(f"\nError message:", file=sys.stderr)
                    print(result.error, file=sys.stderr)

                print(f"\n💡 See full details in log file: {args.log_file}", file=sys.stderr)

                if args.human_in_the_loop and not human_in_the_loop():
                    break
                continue

            # Log success
            write_to_log(log_file, f"\n✅ Iteration {iteration} completed successfully\n")

            # Check for completion signal
            if check_completion(result):
                print(f"\n{separator}")
                print("✅ TASK COMPLETE - Agent emitted completion signal")
                print(separator)
                break

            # Check for commit
            if check_for_commit(result):
                print("✅ Commit detected - forcing exit to prevent overwork")

            # Human review
            if args.human_in_the_loop and not human_in_the_loop():
                break
        else:
            print(f"\n{separator}")
            print(f"⚠️  Max iterations ({args.max_iterations}) reached")
            print("Task may not be complete")
            print(separator)

        # Print and write summaries
        print_final_summary(start_time, iteration, args.max_iterations,
                          cumulative_input_tokens, cumulative_output_tokens, args.log_file)

        write_run_summary(log_file, args, start_time, iteration,
                         cumulative_input_tokens, cumulative_output_tokens)

        return 0

    finally:
        logger.restore()
        log_file.close()
        print(f"\n📄 Log file: {args.log_file}", file=sys.stdout)


if __name__ == '__main__':
    sys.exit(main())
