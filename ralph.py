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


@dataclass
class IterationResult:
    """Result from a single agent iteration."""
    success: bool
    output: str
    error: Optional[str] = None
    iteration_num: int = 0


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


def create_wrapped_prompt(user_prompt: str, iteration_num: int) -> str:
    """Wrap user prompt with Ralph Loop instructions."""
    return f"""RALPH LOOP ITERATION {iteration_num} - CRITICAL INSTRUCTIONS:

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
═══════════════════════════════════════════════════════════════"""


def run_claude_iteration(prompt: str, model: str = 'opus', max_turns: int = 50, timeout: int = 600) -> IterationResult:
    """Run one iteration using Claude Code CLI."""
    cmd = [
        'claude',
        '--print',
        '--dangerously-skip-permissions',
        '--max-turns', str(max_turns),
        '--model', model,
        '-p', prompt
    ]

    # Set YOLO mode environment
    env = os.environ.copy()
    env['CLAUDE_CODE_YOLO'] = '1'

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env
        )
        return IterationResult(
            success=result.returncode == 0,
            output=result.stdout,
            error=result.stderr if result.returncode != 0 else None
        )
    except subprocess.TimeoutExpired:
        return IterationResult(
            success=False,
            output='',
            error=f'Iteration timed out after {timeout} seconds'
        )
    except Exception as e:
        return IterationResult(
            success=False,
            output='',
            error=f'Failed to run claude: {e}'
        )


def run_codex_iteration(prompt: str, timeout: int = 600) -> IterationResult:
    """Run one iteration using Codex CLI."""
    cmd = [
        'codex', 'exec',
        '-s', 'danger-full-access',
        prompt
    ]

    # Set YOLO mode environment
    env = os.environ.copy()
    env['CLAUDE_CODE_YOLO'] = '1'

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env
        )
        return IterationResult(
            success=result.returncode == 0,
            output=result.stdout,
            error=result.stderr if result.returncode != 0 else None
        )
    except subprocess.TimeoutExpired:
        return IterationResult(
            success=False,
            output='',
            error=f'Iteration timed out after {timeout} seconds'
        )
    except Exception as e:
        return IterationResult(
            success=False,
            output='',
            error=f'Failed to run codex: {e}'
        )


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

    args = parser.parse_args()

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

        start_time = datetime.now()

        for iteration in range(1, args.max_iterations + 1):
            print(f"\n🔄 Iteration {iteration}/{args.max_iterations}")
            print(f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print("-"*60)

            # Create wrapped prompt
            wrapped_prompt = create_wrapped_prompt(args.prompt, iteration)

            # Run iteration
            if args.cli_type == 'claude':
                result = run_claude_iteration(wrapped_prompt, args.model, args.max_turns, args.timeout)
            else:
                result = run_codex_iteration(wrapped_prompt, args.timeout)

            result.iteration_num = iteration

            # Check for errors
            if not result.success:
                print(f"❌ Iteration {iteration} failed:", file=sys.stderr)
                if result.error:
                    print(result.error, file=sys.stderr)

                if args.human_in_the_loop:
                    if not human_in_the_loop():
                        break
                continue

            # Show truncated output
            output_lines = result.output.split('\n')
            if len(output_lines) > 20:
                print('\n'.join(output_lines[:10]))
                print(f"\n... ({len(output_lines) - 20} lines omitted) ...\n")
                print('\n'.join(output_lines[-10:]))
            else:
                print(result.output)

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
