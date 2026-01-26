#!/usr/bin/env python3
"""
Test enhanced logging with timestamps and tool use parsing.
"""

import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))
from ralph import (
    create_run_directory,
    create_iteration_directory,
    write_iteration_logs,
    IterationResult,
    parse_tool_use_from_output
)


def test_enhanced_logging():
    """Test the enhanced logging features."""
    print("Testing enhanced Ralph logging...")

    # Create run and iteration directories
    run_dir = create_run_directory()
    iter_dir = create_iteration_directory(run_dir, 1)
    print(f"\n✓ Created test directory: {iter_dir}")

    # Simulate Claude output with tool use
    sample_output = """Let me help you with that task.

<function_calls>
<invoke name="Read">
<parameter name="file_path">/path/to/file.txt