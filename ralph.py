#!/usr/bin/env python3
"""
Backwards-compatible wrapper for ralph.py.

This wrapper maintains compatibility with existing scripts/tools that use ralph.py directly.
The main implementation has moved to src/ralph/core.py as part of the package structure.

For new usage, prefer:
  - pip install ralph-loop
  - ralph <command>
  - python -m ralph <command>
"""
import sys
from pathlib import Path

# Try importing from installed package first
try:
    from ralph.core import main
except ImportError:
    # Fall back to local src path for development
    src_path = Path(__file__).parent / 'src'
    if src_path.exists():
        sys.path.insert(0, str(src_path))
        from ralph.core import main
    else:
        print("Error: Cannot find ralph package. Install with: pip install -e .", file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    sys.exit(main())
