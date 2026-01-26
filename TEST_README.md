# Ralph Log Streaming Test

## Overview

[test_log_streaming.py](test_log_streaming.py) demonstrates and verifies that Ralph's log streaming functionality works correctly with tool calling.

## What It Tests

The test verifies:

1. **Log File Creation**: Creates a temporary log file for the test run
2. **Claude Invocation**: Calls Claude with a prompt that triggers tool use
3. **Real-time Streaming**: Verifies output is streamed to log file in real-time
4. **Tool Invocation Capture**: Checks that tool calls (Read, Bash) are logged
5. **Timestamping**: Verifies each line has millisecond-precision timestamps
6. **Tool Parsing**: Uses Ralph's parser to extract and identify tools from logs
7. **Metadata Logging**: Confirms command, environment, and status are logged

## Running the Test

```bash
# Run the test
./test_log_streaming.py

# Or with python
python3 test_log_streaming.py
```

## Expected Behavior

The test will:

1. Create a temporary log file (path shown in output)
2. Send a prompt to Claude (using haiku model for speed)
3. Wait for Claude to complete (should take 10-30 seconds)
4. Parse and verify the log contents
5. Display:
   - Iteration results (success, duration, tokens)
   - Log file checks (8 different validations)
   - Tools detected and their details
   - Sample of timestamped output
6. Print final pass/fail status
7. Preserve the log file for manual inspection

## Example Output

```
================================================================================
Testing Log Streaming with Tool Calling
================================================================================

📝 Log file: /tmp/tmpxyz123_test.log

📤 Sending prompt to Claude...
Prompt: Please do the following:...

📊 Iteration Results:
   Success: True
   Duration: 15.34s
   Input tokens: 1,234
   Output tokens: 567

📄 Log file size: 12,345 characters

✅ Log File Checks:
   ✓ Command logged: True
   ✓ Environment logged: True
   ✓ Streaming output section: True
   ✓ Contains tool invocations: True
   ✓ Contains function results: True
   ✓ Timestamped lines: True
   ✓ Completion marker: True
   ✓ Return code logged: True

🔧 Tools Used: 2

   Tool 1:
      Name: Read
      Has error: False
      Input: /Users/alan/rc/ralph/ralph.py...
      Result: File content...

   Tool 2:
      Name: Bash
      Has error: False
      Return code: 0
      Input: echo "Hello from test"...
      Result: Hello from test...

🎯 Tool Detection:
   ✓ Expected tool 'Read': True
   ✓ Expected tool 'Bash': True

📋 Sample Log Output (first 20 lines after streaming marker):
--------------------------------------------------------------------------------
[14:30:25.123] Let me help you with that.
[14:30:25.456] <invoke name="Read">
[14:30:25.457] <parameter name="file_path">/Users/alan/rc/ralph/ralph.py</parameter>
...
--------------------------------------------------------------------------------

================================================================================
✅ TEST PASSED: Log streaming with tool calling works!
   - Log file created: /tmp/tmpxyz123_test.log
   - Tools detected: 2
   - All checks passed
================================================================================

💡 Log file preserved for inspection: /tmp/tmpxyz123_test.log
```

## What the Test Demonstrates

This test proves that Ralph's logging system:

1. **Captures everything**: All Claude output including tool calls and results
2. **Streams in real-time**: Output is written as it's received, not buffered
3. **Timestamps accurately**: Each line gets millisecond-precision timestamps
4. **Preserves structure**: Tool invocations and results maintain their XML/tag structure
5. **Enables debugging**: You can trace exactly what happened and when
6. **Supports parsing**: The logged output can be parsed to extract tool information

## Use Cases

This test is useful for:

- **Verification**: Confirming logging works after code changes
- **Documentation**: Showing developers how logging works
- **Debugging**: Testing log parsing logic
- **Integration**: Ensuring Claude CLI integration is working

## Technical Details

- Uses `haiku` model for fast execution
- Sets 5 max turns and 60 second timeout
- Keeps log file after test completes
- Tests both successful tool calls and error detection
- Validates log structure and content

## Troubleshooting

If the test fails:

1. Check you have `claude` CLI installed and configured
2. Verify you have network connectivity (for API calls)
3. Check the preserved log file (path printed at end)
4. Look for specific failed checks in the output
5. Ensure you have write access to `/tmp` directory

## Log File Location

Test log files are created in `/tmp/` with names like:
- `/tmp/tmpABC123_test.log`

The test preserves these files so you can inspect them manually after the test completes.
