#!/usr/bin/env python3
"""
Test enhanced logging with tool use parsing.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from ralph.core import parse_tool_use_from_output


def test_tool_use_parsing():
    """Test the tool use parsing functionality."""
    print("="*80)
    print("Testing Tool Use Parsing")
    print("="*80)

    # Simulate Claude CLI JSON output with tool use
    # This is the format that parse_tool_use_from_output expects (JSON lines)
    sample_output = """{"type": "assistant", "message": {"content": [{"type": "text", "text": "Let me help you with that task."}, {"type": "tool_use", "id": "tool_1", "name": "Read", "input": {"file_path": "/path/to/file.txt"}}]}}
{"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "tool_1", "content": "File contents here with 42 lines"}]}}
{"type": "assistant", "message": {"content": [{"type": "text", "text": "I've read the file successfully. It has 42 lines."}, {"type": "tool_use", "id": "tool_2", "name": "Bash", "input": {"command": "echo \\"Test successful\\""}}]}}
{"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "tool_2", "content": "Test successful"}]}}
{"type": "assistant", "message": {"content": [{"type": "text", "text": "Done!"}]}}"""

    print("\n📝 Parsing sample Claude CLI JSON output with tool invocations...")

    # Test tool use parsing
    tool_uses = parse_tool_use_from_output(sample_output)
    print(f"\n✓ Parsed {len(tool_uses)} tool uses")

    all_passed = True

    # Verify we found the expected number of tools
    if len(tool_uses) != 2:
        print(f"❌ Expected 2 tool uses, found {len(tool_uses)}")
        all_passed = False
    else:
        print("✓ Correct number of tool uses found")

    # Check first tool (Read)
    if len(tool_uses) > 0:
        tool = tool_uses[0]
        print(f"\n🔧 Tool 1:")
        print(f"   Name: {tool['name']}")
        print(f"   Has error: {tool['has_error']}")
        print(f"   Input: {tool['input'][:50]}..." if tool['input'] else "   Input: None")
        print(f"   Result: {tool['result'][:50]}..." if tool['result'] else "   Result: None")

        if tool['name'] != 'Read':
            print(f"   ❌ Expected 'Read', got '{tool['name']}'")
            all_passed = False
        else:
            print("   ✓ Tool name is correct")

        if '/path/to/file.txt' not in (tool['input'] or ''):
            print("   ❌ Expected file path in input")
            all_passed = False
        else:
            print("   ✓ Tool input contains file path")

    # Check second tool (Bash)
    if len(tool_uses) > 1:
        tool = tool_uses[1]
        print(f"\n🔧 Tool 2:")
        print(f"   Name: {tool['name']}")
        print(f"   Has error: {tool['has_error']}")
        print(f"   Input: {tool['input'][:50]}..." if tool['input'] else "   Input: None")
        print(f"   Result: {tool['result'][:50]}..." if tool['result'] else "   Result: None")

        if tool['name'] != 'Bash':
            print(f"   ❌ Expected 'Bash', got '{tool['name']}'")
            all_passed = False
        else:
            print("   ✓ Tool name is correct")

        if 'echo' not in (tool['input'] or '').lower():
            print("   ❌ Expected 'echo' command in input")
            all_passed = False
        else:
            print("   ✓ Tool input contains echo command")

    # Final result
    print(f"\n{'='*80}")
    if all_passed:
        print("✅ TEST PASSED: Tool use parsing works correctly!")
    else:
        print("❌ TEST FAILED: Some checks did not pass")
    print("="*80)

    return all_passed


if __name__ == '__main__':
    try:
        success = test_tool_use_parsing()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Test failed with exception: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
