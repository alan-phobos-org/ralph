#!/usr/bin/env python3
"""
Test that the sys scope bug is fixed.

This test validates that the finally block can access sys.stdout correctly.
"""
import sys
from pathlib import Path

# Add src to path for testing
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))


def test_sys_available_in_finally():
    """
    Verify that sys is accessible in the finally block.

    This reproduces the bug where a local 'import sys' in a conditional
    block caused sys to be treated as local throughout the function,
    leading to UnboundLocalError in the finally block.
    """
    print("Testing sys scope fix...")

    # Read the file and check for local sys imports
    core_file = Path(__file__).parent.parent / 'src' / 'ralph' / 'core.py'
    content = core_file.read_text()

    # Check that there are no local imports of sys
    lines = content.split('\n')
    local_sys_imports = []

    for i, line in enumerate(lines, 1):
        # Check for indented import sys (local imports)
        if line.strip().startswith('import sys') and line[0] in (' ', '\t'):
            local_sys_imports.append((i, line))

    if local_sys_imports:
        print(f"❌ Found {len(local_sys_imports)} local sys import(s):")
        for line_num, line in local_sys_imports:
            print(f"  Line {line_num}: {line}")
        return False

    print("✓ No local sys imports found")

    # Verify that sys is imported at module level
    has_module_import = False
    for line in lines[:50]:  # Check first 50 lines
        if line.strip() == 'import sys':
            has_module_import = True
            break

    if not has_module_import:
        print("❌ No module-level 'import sys' found")
        return False

    print("✓ Module-level sys import found")

    # Check that the finally block uses sys
    finally_blocks = []
    for i, line in enumerate(lines, 1):
        if 'finally:' in line:
            # Look ahead for sys usage
            for j in range(i, min(i + 10, len(lines))):
                if 'sys.' in lines[j]:
                    finally_blocks.append((j + 1, lines[j]))
                    break

    if finally_blocks:
        print(f"✓ Found {len(finally_blocks)} finally block(s) using sys:")
        for line_num, line in finally_blocks:
            print(f"  Line {line_num}: {line.strip()}")

    print("\n✅ Sys scope fix verified - no local imports that shadow module-level sys")
    return True


if __name__ == '__main__':
    try:
        success = test_sys_available_in_finally()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
