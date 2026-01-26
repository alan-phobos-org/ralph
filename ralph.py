#!/usr/bin/env python3
"""
Ralph Loop: Iterative AI agent execution with progress persistence.

Feeds the same prompt repeatedly to an AI agent until task complete.
Progress persists in files and git, not context.
"""

import argparse
import os
import subprocess
import sys
import time
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, TextIO


class TeeLogger:
    """Tee output to both console and log file."""

    def __init__(self, log_file: TextIO):
        self.log_file = log_file
        self.stdout = sys.stdout
        self.stderr = sys.stderr
        sys.stdout = self
        sys.stderr = self

    def write(self, message: str):
        """Write to both console and log file."""
        self.stdout.write(message)
        self.log_file.write(message)
        self.log_file.flush()

    def flush(self):
        """Flush both outputs."""
        self.stdout.flush()
        self.log_file.flush()

    def restore(self):
        """Restore original stdout/stderr."""
        sys.stdout = self.stdout
        sys.stderr = self.stderr


class DetailedLogger:
    """Enhanced logger with timestamps and structured logging."""

    def __init__(self, log_file: TextIO):
        self.log_file = log_file
        self.start_time = None

    def log_event(self, event_type: str, message: str, **kwargs):
        """Log an event with timestamp and structured data."""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        elapsed = ""
        if self.start_time:
            elapsed_sec = (datetime.now() - self.start_time).total_seconds()
            elapsed = f" [+{elapsed_sec:.2f}s]"

        log_line = f"[{timestamp}]{elapsed} [{event_type}] {message}"

        if kwargs:
            log_line += " | " + " | ".join(f"{k}={v}" for k, v in kwargs.items())

        self.log_file.write(log_line + "\n")
        self.log_file.flush()

    def start_timing(self):
        """Start timing for elapsed time calculations."""
        self.start_time = datetime.now()

    def log_subprocess_start(self, cmd: list, env_vars: dict = None):
        """Log subprocess start with full details."""
        self.log_event("SUBPROCESS_START", "Starting subprocess",
                      cmd=" ".join(cmd))
        if env_vars:
            for key, value in env_vars.items():
                self.log_event("ENV_VAR", f"{key}={value}")

    def log_subprocess_end(self, returncode: int, duration: float):
        """Log subprocess completion."""
        self.log_event("SUBPROCESS_END", "Subprocess completed",
                      returncode=returncode, duration_sec=f"{duration:.2f}")

    def log_output_chunk(self, stream: str, chunk: str, length: int):
        """Log a chunk of output being received."""
        self.log_event("OUTPUT_CHUNK", f"Received {length} bytes from {stream}")

    def log_error(self, error_type: str, error_msg: str):
        """Log an error with details."""
        self.log_event("ERROR", f"{error_type}: {error_msg}")

    def log_timeout(self, timeout_seconds: int):
        """Log a timeout event."""
        self.log_event("TIMEOUT", f"Subprocess exceeded timeout of {timeout_seconds}s")


def stream_output_reader(pipe, output_list: list, stream_name: str, logger: DetailedLogger):
    """Read from a pipe and append to output_list, logging chunks."""
    try:
        for line in iter(pipe.readline, ''):
            if line:
                output_list.append(line)
                logger.log_output_chunk(stream_name, line, len(line))
    except Exception as e:
        logger.log_error("STREAM_READ_ERROR", f"Error reading {stream_name}: {e}")


def heartbeat_monitor(process, logger: DetailedLogger, interval: int = 30, stop_event: threading.Event = None):
    """Monitor subprocess and log heartbeat to detect hangs."""
    iteration = 0
    while not stop_event.is_set():
        iteration += 1
        if process.poll() is None:
            # Process still running
            logger.log_event("HEARTBEAT", f"Process still running (check #{iteration})")
        else:
            # Process finished
            logger.log_event("HEARTBEAT", "Process completed, stopping heartbeat")
            break

        # Wait for interval or until stop event
        stop_event.wait(interval)


class StreamingSubprocess:
    """Context manager for subprocess with streaming output capture and heartbeat monitoring."""

    def __init__(self, cmd: list, env: dict, logger: Optional[DetailedLogger], timeout: int):
        self.cmd = cmd
        self.env = env
        self.logger = logger or DetailedLogger(open('/dev/null', 'w'))
        self.timeout = timeout
        self.process = None
        self.stdout_lines = []
        self.stderr_lines = []
        self.stop_event = threading.Event()
        self.threads = []

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
            args=(self.process.stdout, self.stdout_lines, 'stdout', self.logger)
        )
        stderr_thread = threading.Thread(
            target=stream_output_reader,
            args=(self.process.stderr, self.stderr_lines, 'stderr', self.logger)
        )
        heartbeat_thread = threading.Thread(
            target=heartbeat_monitor,
            args=(self.process, self.logger, 30, self.stop_event)
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
            t.join(timeout=2)
        return False

    def wait_with_timeout(self) -> tuple[int, str, str]:
        """
        Wait for process to complete with timeout.

        Returns:
            Tuple of (returncode, stdout_text, stderr_text)

        Raises:
            subprocess.TimeoutExpired: If timeout is exceeded
        """
        returncode = self.process.wait(timeout=self.timeout)
        stdout_text = ''.join(self.stdout_lines)
        stderr_text = ''.join(self.stderr_lines)
        return returncode, stdout_text, stderr_text

    def kill(self) -> tuple[str, str]:
        """
        Kill the process and return captured output.

        Returns:
            Tuple of (stdout_text, stderr_text)
        """
        self.process.kill()
        self.process.wait()
        stdout_text = ''.join(self.stdout_lines)
        stderr_text = ''.join(self.stderr_lines)
        return stdout_text, stderr_text


@dataclass
class IterationResult:
    """Result from a single agent iteration."""
    success: bool
    output: str
    error: Optional[str] = None
    iteration_num: int = 0
    max_turns_reached: bool = False
    timeout_occurred: bool = False
    feedback_summary: Optional[str] = None
    input_tokens: int = 0
    output_tokens: int = 0


def _run_cli_iteration_impl(
    cmd: list,
    cli_name: str,
    prompt: str,
    timeout: int,
    log_file: Optional[TextIO]
) -> IterationResult:
    """
    Shared implementation for running CLI iterations with streaming output.

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

    # Initialize detailed logger
    logger = DetailedLogger(log_file) if log_file else None

    # Log command and environment to file
    if log_file:
        log_file.write(f"\n{'='*80}\n")
        log_file.write(f"COMMAND: {' '.join(cmd)}\n")
        log_file.write(f"ENV: CLAUDE_CODE_YOLO={env.get('CLAUDE_CODE_YOLO')}\n")
        log_file.write(f"TIMEOUT: {timeout}s\n")
        log_file.write(f"PROMPT LENGTH: {len(prompt)} chars\n")
        log_file.write(f"{'='*80}\n")
        log_file.flush()

    if logger:
        logger.start_timing()
        logger.log_subprocess_start(cmd, {'CLAUDE_CODE_YOLO': '1'})

    execution_start = datetime.now()

    try:
        # Use context manager for subprocess with streaming output
        with StreamingSubprocess(cmd, env, logger, timeout) as proc:
            try:
                returncode, stdout_text, stderr_text = proc.wait_with_timeout()
                duration = (datetime.now() - execution_start).total_seconds()

                if logger:
                    logger.log_subprocess_end(returncode, duration)

                # Log full output to file
                if log_file:
                    log_file.write(f"\nRETURN CODE: {returncode}\n")
                    log_file.write(f"DURATION: {duration:.2f}s\n")
                    log_file.write(f"\n--- STDOUT ({len(stdout_text)} chars) ---\n")
                    log_file.write(stdout_text)
                    log_file.write(f"\n--- STDERR ({len(stderr_text)} chars) ---\n")
                    log_file.write(stderr_text)
                    log_file.write(f"\n{'='*80}\n")
                    log_file.flush()

                # Check for max turns error
                max_turns_reached = False
                combined_output = stdout_text + stderr_text
                if 'max turns' in combined_output.lower() or 'reached max turns' in combined_output.lower():
                    max_turns_reached = True
                    if logger:
                        logger.log_event("MAX_TURNS", "Max turns limit reached")

                # Estimate token usage
                input_tokens = estimate_tokens(prompt)
                output_tokens = estimate_tokens(stdout_text)

                return IterationResult(
                    success=returncode == 0,
                    output=stdout_text,
                    error=stderr_text if returncode != 0 else None,
                    max_turns_reached=max_turns_reached,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens
                )

            except subprocess.TimeoutExpired:
                duration = (datetime.now() - execution_start).total_seconds()
                if logger:
                    logger.log_timeout(timeout)

                # Kill the process and get partial output
                stdout_text, stderr_text = proc.kill()

                error_msg = f'Iteration timed out after {timeout} seconds'
                if log_file:
                    log_file.write(f"\n❌ TIMEOUT ERROR: {error_msg}\n")
                    log_file.write(f"DURATION: {duration:.2f}s\n")
                    log_file.write(f"\nPartial STDOUT ({len(stdout_text)} chars):\n{stdout_text}\n")
                    log_file.write(f"\nPartial STDERR ({len(stderr_text)} chars):\n{stderr_text}\n")
                    log_file.flush()

                # Estimate token usage even for timeout
                input_tokens = estimate_tokens(prompt)
                output_tokens = estimate_tokens(stdout_text)

                return IterationResult(
                    success=False,
                    output=stdout_text,
                    error=error_msg,
                    timeout_occurred=True,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens
                )

    except Exception as e:
        duration = (datetime.now() - execution_start).total_seconds()
        error_msg = f'Failed to run {cli_name}: {type(e).__name__}: {e}'

        if logger:
            logger.log_error("EXCEPTION", error_msg)

        if log_file:
            log_file.write(f"\n❌ EXCEPTION: {error_msg}\n")
            log_file.write(f"DURATION: {duration:.2f}s\n")
            import traceback
            log_file.write(traceback.format_exc())
            log_file.flush()

        # Estimate token usage even for exceptions
        input_tokens = estimate_tokens(prompt)

        return IterationResult(
            success=False,
            output='',
            error=error_msg,
            input_tokens=input_tokens,
            output_tokens=0
        )


def estimate_tokens(text: str) -> int:
    """
    Estimate token count from text.

    Uses a simple heuristic: characters / 4 (rough approximation).
    For more accurate counting, would need tiktoken or anthropic SDK.
    """
    return len(text) // 4


def extract_iteration_feedback(result: IterationResult) -> str:
    """Extract feedback from iteration result to pass to next iteration."""
    feedback_parts = []

    # Check for max turns
    if result.max_turns_reached:
        feedback_parts.append(
            "⚠️ PREVIOUS ITERATION HIT MAX TURNS LIMIT\n"
            "The last iteration was stopped because it reached the maximum turn limit.\n"
            "This usually means the plan has tasks that are too large or complex.\n"
            "GUIDANCE: Break down the current task into smaller, more focused steps."
        )

    # Check for timeout
    if result.timeout_occurred:
        feedback_parts.append(
            "⚠️ PREVIOUS ITERATION TIMED OUT\n"
            "The last iteration exceeded the time limit.\n"
            "GUIDANCE: Simplify the current task or break it into smaller pieces."
        )

    # Check for general errors
    if result.error and not result.max_turns_reached and not result.timeout_occurred:
        feedback_parts.append(
            f"⚠️ PREVIOUS ITERATION ENCOUNTERED AN ERROR\n"
            f"Error: {result.error[:500]}\n"
            f"GUIDANCE: Address this error before proceeding."
        )

    # If no specific feedback, indicate success
    if not feedback_parts and result.success:
        return "✅ Previous iteration completed successfully."

    return "\n\n".join(feedback_parts) if feedback_parts else "No feedback from previous iteration."


def check_for_commit(result: IterationResult) -> bool:
    """Check if a commit was made during this iteration."""
    # Check output for commit confirmation
    if 'git commit' in result.output.lower():
        return True

    # Verify with git log (commits in last 30 seconds)
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
    # Check for signal with or without markdown formatting
    return 'RALPH_LOOP_COMPLETE' in result.output and '🎯' in result.output


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


def create_wrapped_prompt(user_prompt: str, iteration_num: int, outer_prompt_template: str, feedback: Optional[str] = None) -> str:
    """Wrap user prompt with Ralph Loop instructions from template."""
    # Include feedback in the template if provided
    feedback_section = ""
    if feedback and iteration_num > 1:
        feedback_section = f"\n\n{'='*60}\nFEEDBACK FROM PREVIOUS ITERATION:\n{'='*60}\n{feedback}\n{'='*60}\n"

    return outer_prompt_template.format(
        iteration_num=iteration_num,
        user_prompt=user_prompt,
        feedback=feedback_section
    )


def run_claude_iteration(prompt: str, model: str = 'opus', max_turns: int = 50, timeout: int = 600, log_file: Optional[TextIO] = None) -> IterationResult:
    """Run one iteration using Claude Code CLI with detailed logging and streaming output."""
    cmd = [
        'claude',
        '--print',
        '--dangerously-skip-permissions',
        '--max-turns', str(max_turns),
        '--model', model,
        '-p', prompt
    ]
    return _run_cli_iteration_impl(cmd, 'claude', prompt, timeout, log_file)


def run_codex_iteration(prompt: str, timeout: int = 600, log_file: Optional[TextIO] = None) -> IterationResult:
    """Run one iteration using Codex CLI with detailed logging and streaming output."""
    cmd = [
        'codex', 'exec',
        '-s', 'danger-full-access',
        prompt
    ]
    return _run_cli_iteration_impl(cmd, 'codex', prompt, timeout, log_file)


def human_in_the_loop() -> bool:
    """Pause for human review. Returns True to continue, False to stop."""
    print("\n" + "="*60)
    print("🤚 HUMAN IN THE LOOP - Pausing for review")
    print("="*60)
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


def main():
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
        """
    )

    parser.add_argument(
        'prompt',
        nargs='?',
        help='The task prompt to feed to the agent'
    )
    parser.add_argument(
        '-f', '--prompt-file',
        type=str,
        help='Read the prompt from a file'
    )
    parser.add_argument(
        '--max-iterations',
        type=int,
        default=10,
        help='Maximum number of iterations (default: 10)'
    )
    parser.add_argument(
        '--max-turns',
        type=int,
        default=50,
        help='Maximum turns per iteration for Claude CLI (default: 50)'
    )
    parser.add_argument(
        '--human-in-the-loop',
        action='store_true',
        help='Pause after each iteration for human review'
    )
    parser.add_argument(
        '--model',
        choices=['opus', 'sonnet', 'haiku'],
        default='opus',
        help='Model to use for Claude CLI (default: opus)'
    )
    parser.add_argument(
        '--cli-type',
        choices=['claude', 'codex'],
        default='claude',
        help='Which CLI to use (default: claude)'
    )
    parser.add_argument(
        '--timeout',
        type=int,
        default=600,
        help='Timeout in seconds for each iteration (default: 600 = 10 minutes)'
    )
    parser.add_argument(
        '--log-file',
        type=str,
        default=None,
        help='Path to log file (default: /tmp/ralph_[timestamp].log)'
    )
    parser.add_argument(
        '--outer-prompt',
        type=str,
        default=None,
        help='Path to outer prompt template file (default: prompts/outer-prompt-default.md)'
    )

    args = parser.parse_args()

    # Set default outer prompt path if not specified
    if args.outer_prompt is None:
        # Try to find prompts directory relative to script location
        script_dir = Path(__file__).parent
        args.outer_prompt = str(script_dir / 'prompts' / 'outer-prompt-default.md')

    # Load outer prompt template
    outer_prompt_template = load_outer_prompt(args.outer_prompt)

    # Handle prompt from file or command line
    if args.prompt_file:
        try:
            prompt_path = Path(args.prompt_file)
            args.prompt = prompt_path.read_text(encoding='utf-8').strip()
        except FileNotFoundError:
            print(f"❌ Error: Prompt file not found: {args.prompt_file}", file=sys.stderr)
            return 1
        except Exception as e:
            print(f"❌ Error reading prompt file: {e}", file=sys.stderr)
            return 1
    elif not args.prompt:
        parser.error("Either provide a prompt argument or use --prompt-file/-f")

    # Set up log file
    if args.log_file is None:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        args.log_file = f'/tmp/ralph_{timestamp}.log'

    # Create log file and set up tee logger
    log_file = open(args.log_file, 'w', encoding='utf-8')
    logger = TeeLogger(log_file)

    try:
        # Check if we're in a git repo
        try:
            subprocess.run(
                ['git', 'rev-parse', '--git-dir'],
                check=True,
                capture_output=True
            )
        except subprocess.CalledProcessError:
            print("❌ Error: Not in a git repository", file=sys.stderr)
            return 1

        print("🚀 Ralph Loop Starting")
        print(f"📝 Logging to: {args.log_file}")
        print(f"Task: {args.prompt}")
        print(f"Max iterations: {args.max_iterations}")
        print(f"Max turns per iteration: {args.max_turns}")
        print(f"Timeout per iteration: {args.timeout} seconds")
        print(f"CLI: {args.cli_type}")
        if args.cli_type == 'claude':
            print(f"Model: {args.model}")
        print(f"Human-in-the-loop: {args.human_in_the_loop}")
        print("="*60)

        # Calculate initial token count
        initial_prompt = create_wrapped_prompt(args.prompt, 1, outer_prompt_template, None)
        initial_tokens = estimate_tokens(initial_prompt)
        print(f"\n📊 Initial prompt size: {initial_tokens:,} tokens (estimated)")
        print("="*60)

        start_time = datetime.now()
        previous_result: Optional[IterationResult] = None
        cumulative_input_tokens = 0
        cumulative_output_tokens = 0

        for iteration in range(1, args.max_iterations + 1):
            print(f"\n🔄 Iteration {iteration}/{args.max_iterations}")
            print(f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print("-"*60)

            # Extract feedback from previous iteration
            feedback = None
            if previous_result:
                feedback = extract_iteration_feedback(previous_result)

            # Create wrapped prompt with feedback
            wrapped_prompt = create_wrapped_prompt(args.prompt, iteration, outer_prompt_template, feedback)

            # Log the wrapped prompt to file
            log_file.write(f"\n\n{'#'*80}\n")
            log_file.write(f"# ITERATION {iteration}/{args.max_iterations}\n")
            log_file.write(f"# {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            log_file.write(f"{'#'*80}\n")
            log_file.write(f"\n--- WRAPPED PROMPT ---\n")
            log_file.write(wrapped_prompt)
            log_file.write(f"\n--- END WRAPPED PROMPT ---\n")
            log_file.flush()

            # Run iteration
            if args.cli_type == 'claude':
                result = run_claude_iteration(wrapped_prompt, args.model, args.max_turns, args.timeout, log_file)
            else:
                result = run_codex_iteration(wrapped_prompt, args.timeout, log_file)

            result.iteration_num = iteration

            # Track cumulative tokens
            cumulative_input_tokens += result.input_tokens
            cumulative_output_tokens += result.output_tokens

            # Display iteration stats
            print(f"\n📊 Iteration {iteration} tokens:")
            print(f"   Input:  {result.input_tokens:,} tokens")
            print(f"   Output: {result.output_tokens:,} tokens")
            print(f"   Total:  {result.input_tokens + result.output_tokens:,} tokens")

            # Store result for next iteration's feedback
            previous_result = result

            # Check for errors
            if not result.success:
                print(f"❌ Iteration {iteration} failed", file=sys.stderr)
                print(f"Return code: non-zero", file=sys.stderr)

                if result.error:
                    print(f"\nError message:", file=sys.stderr)
                    print(result.error, file=sys.stderr)

                # Show stderr if available
                if result.error and result.error.strip():
                    print(f"\nStderr output:", file=sys.stderr)
                    # Truncate very long stderr
                    stderr_lines = result.error.split('\n')
                    if len(stderr_lines) > 50:
                        print('\n'.join(stderr_lines[:25]), file=sys.stderr)
                        print(f"\n... ({len(stderr_lines) - 50} lines omitted) ...\n", file=sys.stderr)
                        print('\n'.join(stderr_lines[-25:]), file=sys.stderr)
                    else:
                        print(result.error, file=sys.stderr)

                # Show stdout if available (might contain useful context)
                if result.output and result.output.strip():
                    print(f"\nStdout output (may contain clues):", file=sys.stderr)
                    stdout_lines = result.output.split('\n')
                    if len(stdout_lines) > 30:
                        print('\n'.join(stdout_lines[:15]), file=sys.stderr)
                        print(f"\n... ({len(stdout_lines) - 30} lines omitted) ...\n", file=sys.stderr)
                        print('\n'.join(stdout_lines[-15:]), file=sys.stderr)
                    else:
                        print(result.output, file=sys.stderr)

                print(f"\n💡 See full details in log file: {args.log_file}", file=sys.stderr)

                if args.human_in_the_loop:
                    if not human_in_the_loop():
                        break
                continue

            # Show truncated output to console (full output already in log file)
            output_lines = result.output.split('\n')
            if len(output_lines) > 20:
                print('\n'.join(output_lines[:10]))
                print(f"\n... ({len(output_lines) - 20} lines omitted, see log file) ...\n")
                print('\n'.join(output_lines[-10:]))
            else:
                print(result.output)

            # Log success to file
            log_file.write(f"\n✅ Iteration {iteration} completed successfully\n")
            log_file.flush()

            # Check for completion signal
            if check_completion(result):
                print("\n" + "="*60)
                print("✅ TASK COMPLETE - Agent emitted completion signal")
                print("="*60)
                break

            # Check for commit
            if check_for_commit(result):
                print("✅ Commit detected - forcing exit to prevent overwork")

            # Human in the loop pause
            if args.human_in_the_loop:
                if not human_in_the_loop():
                    break
        else:
            print("\n" + "="*60)
            print(f"⚠️  Max iterations ({args.max_iterations}) reached")
            print("Task may not be complete")
            print("="*60)

        # Summary
        elapsed = datetime.now() - start_time
        print(f"\n⏱️  Total time: {elapsed}")
        print(f"🔢 Iterations completed: {iteration}")

        # Display cumulative token usage
        total_tokens = cumulative_input_tokens + cumulative_output_tokens
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
            print("-"*60)
            print(progress_file.read_text())

        return 0

    finally:
        # Always clean up logger and close log file
        logger.restore()
        log_file.close()
        print(f"\n📄 Full log saved to: {args.log_file}", file=sys.stdout)


if __name__ == '__main__':
    sys.exit(main())
