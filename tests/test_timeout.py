"""Tests for total timeout functionality."""
import subprocess
import sys
import tempfile
from pathlib import Path
import pytest


@pytest.fixture
def mock_git_repo(tmp_path):
    """Create a mock git repository for testing."""
    # Initialize git repo
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=tmp_path, check=True, capture_output=True)

    # Create initial commit
    (tmp_path / "README.md").write_text("# Test repo")
    subprocess.run(["git", "add", "README.md"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=tmp_path, check=True, capture_output=True)

    return tmp_path


@pytest.fixture
def mock_outer_prompt(tmp_path):
    """Create a minimal outer prompt template."""
    prompt_dir = tmp_path / ".ralph" / "prompts"
    prompt_dir.mkdir(parents=True, exist_ok=True)

    prompt_file = prompt_dir / "outer-prompt-test.md"
    prompt_file.write_text("""
# Test Prompt

Iteration: {iteration_num}

User Task: {user_prompt}

{feedback}
""")

    return prompt_file


def test_total_timeout_exits_with_error_code(mock_git_repo, mock_outer_prompt):
    """Verify that total timeout causes ralph to exit with non-zero code."""
    # Create a simple test prompt
    prompt = "Echo 'test' and sleep for 60 seconds"

    # Run ralph with a very short total timeout (1 second)
    # This should trigger the timeout before any real work is done
    result = subprocess.run(
        [
            sys.executable, "-m", "ralph.core",
            prompt,
            "--max-iterations", "10",
            "--timeout-total", "1",
            "--timeout", "30",
            "--max-turns", "5",
            "--model", "haiku",
            "--outer-prompt", str(mock_outer_prompt)
        ],
        cwd=mock_git_repo,
        capture_output=True,
        text=True,
        timeout=10  # Hard timeout for the test itself
    )

    # Should return exit code 2 for timeout
    assert result.returncode == 2, f"Expected exit code 2, got {result.returncode}. Stdout: {result.stdout}, Stderr: {result.stderr}"

    # Check for timeout message in output
    combined_output = result.stdout + result.stderr
    assert "TOTAL TIMEOUT REACHED" in combined_output or "total timeout" in combined_output.lower(), \
        f"Timeout message not found. Output: {combined_output}"


def test_total_timeout_message_contains_elapsed_time(mock_git_repo, mock_outer_prompt):
    """Verify timeout message includes elapsed time information."""
    prompt = "Simple test task"

    result = subprocess.run(
        [
            sys.executable, "-m", "ralph.core",
            prompt,
            "--max-iterations", "5",
            "--timeout-total", "1",
            "--timeout", "30",
            "--max-turns", "3",
            "--model", "haiku",
            "--outer-prompt", str(mock_outer_prompt)
        ],
        cwd=mock_git_repo,
        capture_output=True,
        text=True,
        timeout=10
    )

    combined_output = result.stdout + result.stderr

    # Should mention elapsed time
    assert "elapsed" in combined_output.lower() or "seconds" in combined_output.lower(), \
        f"Elapsed time info not found. Output: {combined_output}"


def test_no_timeout_when_total_timeout_not_set(mock_git_repo, mock_outer_prompt):
    """Verify ralph works normally when total timeout is not set."""
    prompt = "Echo 'hello world'"

    # Run without total timeout - should work normally (though may fail for other reasons)
    # We're just checking that it doesn't fail due to timeout logic
    result = subprocess.run(
        [
            sys.executable, "-m", "ralph.core",
            prompt,
            "--max-iterations", "1",
            "--timeout", "30",
            "--max-turns", "3",
            "--model", "haiku",
            "--outer-prompt", str(mock_outer_prompt)
        ],
        cwd=mock_git_repo,
        capture_output=True,
        text=True,
        timeout=45
    )

    # Should not exit with timeout error code (2)
    # Note: May fail for other reasons (no API key, etc), but not with code 2
    assert result.returncode != 2, \
        f"Should not timeout when --timeout-total not set. Exit code: {result.returncode}"


def test_timeout_shows_in_initial_configuration(mock_git_repo, mock_outer_prompt):
    """Verify total timeout is displayed in initial configuration."""
    prompt = "Test task"

    result = subprocess.run(
        [
            sys.executable, "-m", "ralph.core",
            prompt,
            "--max-iterations", "1",
            "--timeout-total", "60",
            "--timeout", "30",
            "--max-turns", "3",
            "--model", "haiku",
            "--outer-prompt", str(mock_outer_prompt)
        ],
        cwd=mock_git_repo,
        capture_output=True,
        text=True,
        timeout=10
    )

    combined_output = result.stdout + result.stderr

    # Should show total timeout in configuration
    assert "Total timeout" in combined_output or "timeout-total" in combined_output.lower(), \
        f"Total timeout not shown in config. Output: {combined_output}"
