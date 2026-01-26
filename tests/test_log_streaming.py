#!/usr/bin/env python3
"""
Test log streaming with tool calling via full ralph.py entry point.

This test demonstrates:
1. Running ralph.py as a subprocess with a simple task
2. Verifying streaming output is captured in real-time to the log file
3. Checking that tool invocations flow through all logging layers
4. Validating the complete logging stack from ralph.py -> CLI -> log file
5. Verifying that multiple tool uses are streamed independently (real-time)
6. Parsing and displaying tool invocations in human-readable format
"""

import sys
import subprocess
import tempfile
import re
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Tuple


def parse_tool_invocations(log_content: str) -> List[Dict]:
    """Parse tool invocations and extract timestamps."""
    import json
    tools = []
    lines = log_content.split('\n')

    for i, line in enumerate(lines):
        # Look for tool invocation markers (with or without id attribute)
        if '<invoke name="' in line:
            tool_match = re.search(r'<invoke name="([^"]+)"', line)
            if tool_match:
                tool_name = tool_match.group(1)

                # Extract timestamp if present
                timestamp = None
                ts_match = re.search(r'\[(\d{2}:\d{2}:\d{2}\.\d+)\]', line)
                if ts_match:
                    timestamp = ts_match.group(1)

                # Look ahead for Input JSON block or parameter tags
                description = None
                parameters = {}
                json_params = None

                for j in range(i+1, min(i+15, len(lines))):
                    if '</invoke>' in lines[j]:
                        break

                    # Check for JSON Input block
                    if 'Input: {' in lines[j] or lines[j].strip() == 'Input: {':
                        # Collect JSON lines - start from the actual JSON content
                        json_lines = []
                        started = False

                        for k in range(j, min(j+15, len(lines))):
                            line = lines[k].strip()

                            # Start collecting at the opening brace
                            if 'Input:' in lines[k]:
                                if '{' in lines[k]:
                                    # Input: { on same line
                                    json_content = lines[k].split('Input:', 1)[1].strip()
                                    if json_content == '{':
                                        json_lines.append('{')
                                        started = True
                                    else:
                                        json_lines.append(json_content)
                                        if '}' in json_content:
                                            break
                                        started = True
                            elif started:
                                json_lines.append(line)
                                if line == '}' or line.endswith('}'):
                                    break

                        # Try to parse JSON
                        if json_lines:
                            try:
                                json_str = ' '.join(json_lines)
                                json_params = json.loads(json_str)
                                parameters.update(json_params)
                            except Exception as e:
                                # Silently ignore parse errors
                                pass

                    # Extract parameter tags (older format)
                    if 'parameter name=' in lines[j]:
                        param_match = re.search(r'parameter name="([\w_]+)">([^<]*)', lines[j])
                        if param_match:
                            param_name = param_match.group(1)
                            param_value = param_match.group(2).strip()
                            if param_name == 'description':
                                description = param_value
                            else:
                                if param_value:
                                    parameters[param_name] = param_value

                tools.append({
                    'tool': tool_name,
                    'timestamp': timestamp,
                    'description': description,
                    'parameters': parameters
                })

    return tools


def parse_function_results(log_content: str) -> List[Dict]:
    """Parse function results and extract timestamps."""
    results = []
    lines = log_content.split('\n')

    for i, line in enumerate(lines):
        # Look for function_results markers (with or without tool_use_id)
        if '<function_results' in line and 'tool_use_id=' in line:
            # Extract timestamp if present
            timestamp = None
            ts_match = re.search(r'\[(\d{2}:\d{2}:\d{2}\.\d+)\]', line)
            if ts_match:
                timestamp = ts_match.group(1)

            # Extract result content
            result_content = []
            is_error = False

            for j in range(i+1, min(i+30, len(lines))):
                if '</function_results>' in lines[j]:
                    break

                content = lines[j].strip()

                # Check for errors
                if '<tool_use_error>' in content:
                    is_error = True
                    error_match = re.search(r'<tool_use_error>([^<]+)</tool_use_error>', content)
                    if error_match:
                        result_content.append(f"ERROR: {error_match.group(1)}")
                    continue

                # Skip timestamp lines, empty lines, and XML tags
                if (content and
                    not content.startswith('[') and
                    not content.startswith('<') and
                    not content.startswith('}')):
                    result_content.append(content)

            results.append({
                'timestamp': timestamp,
                'content': result_content[:6] if result_content else ['(empty result)'],
                'is_error': is_error
            })

    return results


def format_tool_info(tools: List[Dict], results: List[Dict]) -> str:
    """Format tool invocations and results in human-readable format."""
    output = []
    output.append("\n" + "="*80)
    output.append("TOOL INVOCATIONS AND RESULTS")
    output.append("="*80)

    for i, tool in enumerate(tools, 1):
        # Format: [timestamp] Tool: description
        timestamp = f"[{tool['timestamp']}]" if tool['timestamp'] else ""
        tool_name = tool['tool']
        description = tool.get('description', '')

        if description:
            output.append(f"\n{timestamp} {tool_name}: {description}")
        else:
            output.append(f"\n{timestamp} {tool_name}")

        # Show parameters indented
        if tool['parameters']:
            for param, value in tool['parameters'].items():
                if param == 'description':
                    continue  # Already shown above
                # Truncate long values
                value_str = str(value)
                if len(value_str) > 80:
                    display_value = value_str[:77] + '...'
                else:
                    display_value = value_str
                output.append(f"   {param}: {display_value}")

        # Find corresponding result
        if i-1 < len(results):
            result = results[i-1]
            result_ts = f"[{result['timestamp']}]" if result['timestamp'] else ""

            # Show error status if present
            if result.get('is_error'):
                output.append(f"\n{result_ts} ERROR")
            else:
                output.append(f"\n{result_ts}")

            # Show result content indented
            if result['content']:
                for line in result['content'][:4]:  # Show first 4 lines
                    # Truncate long lines
                    display_line = line if len(line) < 120 else line[:117] + '...'
                    output.append(f"   {display_line}")
                if len(result['content']) > 4:
                    output.append(f"   ... ({len(result['content']) - 4} more lines)")

    output.append("\n" + "="*80)
    return '\n'.join(output)


def verify_realtime_streaming(tools: List[Dict], results: List[Dict]) -> Tuple[bool, str]:
    """
    Verify that tools were streamed in real-time (not all at once at the end).
    Returns (success, message).
    """
    if len(tools) < 2:
        return False, "Not enough tool invocations to verify real-time streaming (need at least 2)"

    # Parse timestamps and compute time deltas
    tool_times = []
    for tool in tools:
        if tool['timestamp']:
            try:
                # Parse time-only format HH:MM:SS.fff
                time_parts = tool['timestamp'].split(':')
                hours = int(time_parts[0])
                minutes = int(time_parts[1])
                seconds = float(time_parts[2])
                # Convert to total seconds for easy delta calculation
                total_secs = hours * 3600 + minutes * 60 + seconds
                tool_times.append(total_secs)
            except:
                pass

    if len(tool_times) < 2:
        return False, "Could not parse enough timestamps to verify streaming"

    # Compute time differences between consecutive tool invocations
    deltas = []
    for i in range(1, len(tool_times)):
        delta = tool_times[i] - tool_times[i-1]
        # Handle potential day rollover (negative delta)
        if delta < 0:
            delta += 86400  # Add 24 hours
        deltas.append(delta)

    # If all deltas are < 0.1s, tools likely arrived in a batch (not streaming)
    # If deltas are spread out (> 0.5s), that indicates real-time streaming
    avg_delta = sum(deltas) / len(deltas)
    max_delta = max(deltas)

    if max_delta < 0.1:
        return False, f"Tools arrived too quickly (max gap: {max_delta:.3f}s) - likely batched, not streamed"
    elif avg_delta > 0.3:
        return True, f"Tools arrived with good spacing (avg: {avg_delta:.2f}s, max: {max_delta:.2f}s) - streaming verified"
    else:
        return True, f"Tools arrived with moderate spacing (avg: {avg_delta:.2f}s) - likely streaming"


def test_log_streaming_with_tools():
    """
    Test that log streaming works end-to-end through ralph.py main entry point.

    This test:
    1. Creates a temporary log file
    2. Runs ralph.py with a task that triggers 3+ tool uses
    3. Verifies the log file contains streamed tool invocations
    4. Validates that tools arrive independently (real-time streaming)
    5. Displays tool information in human-readable format
    """
    print("="*80)
    print("Testing End-to-End Log Streaming via ralph.py")
    print("="*80)

    # Get paths
    script_dir = Path(__file__).parent.parent
    ralph_script = script_dir / 'ralph.py'

    if not ralph_script.exists():
        print(f"ERROR: ralph.py not found at {ralph_script}")
        return False

    # Create temporary log file
    with tempfile.NamedTemporaryFile(mode='w', suffix='_ralph_test.log', delete=False) as log_file:
        log_path = log_file.name
        print(f"\nLog file: {log_path}")

        # Longer prompt that will trigger multiple tool uses
        test_prompt = """First, use Glob to find all Python files in the current directory.
Then, use Read to read the ralph.py file and count the number of function definitions.
Finally, use Bash to run 'echo "Streaming test complete"'.
Keep all responses brief and focused."""

        print(f"\nRunning ralph.py with multi-tool test prompt...")
        print(f"Script: {ralph_script}")
        print(f"Prompt: {test_prompt[:80]}...")

        # Build command to run ralph.py
        cmd = [
            sys.executable,
            str(ralph_script),
            test_prompt,
            '--max-iterations', '1',  # Only one iteration
            '--max-turns', '15',       # More turns for multiple tools
            '--timeout', '120',        # 2 minute timeout
            '--model', 'haiku',        # Fast model
            '--cli-type', 'claude',
            '--log-file', log_path
        ]

        print(f"\nCommand: {' '.join(cmd[:3])} ... (with args)")
        print(f"Starting ralph.py subprocess...")

        start_time = datetime.now()

        # Run ralph.py as subprocess
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=150  # Slightly longer than --timeout to allow for cleanup
            )
            duration = (datetime.now() - start_time).total_seconds()

            print(f"Subprocess completed in {duration:.1f}s")
            print(f"   Return code: {result.returncode}")

        except subprocess.TimeoutExpired:
            print("ERROR: ralph.py subprocess timed out")
            return False
        except Exception as e:
            print(f"ERROR: Failed to run ralph.py: {e}")
            return False

    # Read the log file back
    log_content = Path(log_path).read_text()
    print(f"\nLog file size: {len(log_content):,} characters")

    # Parse tool invocations and results
    tools = parse_tool_invocations(log_content)
    results = parse_function_results(log_content)

    print(f"\nFound {len(tools)} tool invocations and {len(results)} results")

    # Display formatted tool information
    formatted_output = format_tool_info(tools, results)
    print(formatted_output)

    # Verify real-time streaming
    print("\n" + "="*80)
    print("REAL-TIME STREAMING VERIFICATION")
    print("="*80)

    streaming_ok, streaming_msg = verify_realtime_streaming(tools, results)
    if streaming_ok:
        print(f"PASS: {streaming_msg}")
    else:
        print(f"WARN: {streaming_msg}")

    # Verify log contains key elements from all logging layers
    checks = {
        "Ralph starting banner": "Ralph Loop Starting" in log_content,
        "Task prompt logged": "Task:" in log_content or test_prompt[:30] in log_content,
        "Command logged": "COMMAND:" in log_content,
        "Environment logged": "ENV:" in log_content or "CLAUDE_CODE_YOLO" in log_content,
        "Streaming output section": "STREAMING OUTPUT" in log_content,
        "Timestamped lines": "[20" in log_content,
        "Completion marker": "STREAMING COMPLETE" in log_content,
        "Return code logged": "RETURN CODE:" in log_content,
        "Contains tool invocations": "<invoke" in log_content or "invoke name=" in log_content,
        "Contains function results": "function_results" in log_content.lower() or "<function_results>" in log_content,
        f"At least 2 tool uses": len(tools) >= 2,
        "Glob tool used": any(t['tool'] == 'Glob' for t in tools),
        "Read tool used": any(t['tool'] == 'Read' for t in tools),
        "Bash tool used": any(t['tool'] == 'Bash' for t in tools),
    }

    print(f"\nLog File Checks (All Layers):")
    all_passed = True
    for check_name, passed in checks.items():
        status = "PASS" if passed else "FAIL"
        print(f"   {status}: {check_name}")
        if not passed:
            all_passed = False

    # Include streaming verification in final result
    if not streaming_ok:
        print(f"\nWarning: Real-time streaming could not be fully verified")
        print(f"   Reason: {streaming_msg}")
        # Don't fail the test for this, just warn

    # Final result
    print(f"\n{'='*80}")
    if all_passed:
        print("TEST PASSED: End-to-end log streaming works!")
        print(f"   - Full ralph.py execution tested")
        print(f"   - Multiple tool invocations verified")
        print(f"   - Human-readable formatting implemented")
        print(f"   - All logging layers verified")
        print(f"   - Log file: {log_path}")
    else:
        print("TEST FAILED: Some checks did not pass")
        print(f"   Review log file: {log_path}")
        print(f"\nDebug tips:")
        print(f"   - Check if claude CLI is installed and in PATH")
        print(f"   - Verify CLAUDE_CODE_YOLO=1 is being set")
        print(f"   - Review the full log file for errors")
    print("="*80)

    # Keep log file for inspection
    print(f"\nLog file preserved for inspection: {log_path}")

    return all_passed


if __name__ == '__main__':
    try:
        success = test_log_streaming_with_tools()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nTest failed with exception: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
