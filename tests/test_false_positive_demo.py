#!/usr/bin/env python3
"""
Minimal demonstration of the false positive bug in NESTED_COMPAT.md.

This script simulates a normal Claude CLI conversation and shows how the
proposed ConversationStateTracker would incorrectly kill the process.

Run with: python3 tests/test_false_positive_demo.py
"""

import json
import time
from typing import List


class ConversationStateTracker:
    """Exact implementation from NESTED_COMPAT.md (lines 59-156)."""

    def __init__(self):
        self.pending_tool_calls = set()
        self.last_message_time = time.time()
        self.saw_final_text_message = False
        self.saw_result_message = False
        self.last_message_type = None

    def process_line(self, line: str) -> None:
        try:
            obj = json.loads(line)
            msg_type = obj.get('type')

            if msg_type in ['assistant', 'user', 'result']:
                self.last_message_time = time.time()
                self.last_message_type = msg_type

            if msg_type == 'assistant':
                content = obj.get('message', {}).get('content', [])
                has_tool_use = False
                has_text = False

                for item in content:
                    if item.get('type') == 'tool_use':
                        tool_id = item.get('id')
                        if tool_id:
                            self.pending_tool_calls.add(tool_id)
                        has_tool_use = True
                    elif item.get('type') == 'text':
                        has_text = True

                if has_text and not has_tool_use:
                    self.saw_final_text_message = True

            elif msg_type == 'user':
                content = obj.get('message', {}).get('content', [])
                for item in content:
                    if item.get('type') == 'tool_result':
                        tool_id = item.get('tool_use_id')
                        if tool_id in self.pending_tool_calls:
                            self.pending_tool_calls.discard(tool_id)

            elif msg_type == 'result':
                self.saw_result_message = True

        except (json.JSONDecodeError, KeyError, TypeError):
            pass

    def looks_hung(self, timeout: float = 30.0) -> bool:
        if self.saw_result_message:
            return False

        time_since_last = time.time() - self.last_message_time

        return (
            self.saw_final_text_message and
            len(self.pending_tool_calls) == 0 and
            not self.saw_result_message and
            time_since_last > timeout
        )


def simulate_conversation(messages: List[dict], delays: List[float]) -> None:
    """
    Simulate a conversation with the tracker, showing when it would kill the process.

    Args:
        messages: List of message dicts (will be converted to JSON)
        delays: List of delays (seconds) after each message
    """
    tracker = ConversationStateTracker()

    print("=" * 80)
    print("SIMULATING CLAUDE CLI CONVERSATION")
    print("=" * 80)

    for i, (msg, delay) in enumerate(zip(messages, delays)):
        # Show message
        msg_type = msg.get('type', 'unknown')
        content_summary = ""

        if msg_type == 'assistant':
            for item in msg.get('message', {}).get('content', []):
                if item.get('type') == 'text':
                    text = item.get('text', '')[:60]
                    content_summary = f'Text: "{text}..."'
                elif item.get('type') == 'tool_use':
                    tool_name = item.get('name', '')
                    content_summary = f'Tool: {tool_name}'

        print(f"\n[Message {i+1}] Type: {msg_type:10} | {content_summary}")

        # Process message
        line = json.dumps(msg)
        tracker.process_line(line)

        # Show tracker state
        print(f"  Tracker state:")
        print(f"    - Saw final text: {tracker.saw_final_text_message}")
        print(f"    - Pending tools:  {len(tracker.pending_tool_calls)}")
        print(f"    - Saw result:     {tracker.saw_result_message}")

        # Check if hung (with 1 second timeout for demo)
        if tracker.looks_hung(timeout=1.0):
            print("\n" + "!" * 80)
            print("! 🚨 TRACKER WOULD KILL PROCESS (false positive!)")
            print("!" * 80)
            return

        # Wait (simulating processing/thinking time)
        if delay > 0:
            print(f"  Waiting {delay}s (simulating Claude thinking/processing)...")
            time.sleep(delay)

            # Check again after delay
            if tracker.looks_hung(timeout=1.0):
                print("\n" + "!" * 80)
                print("! 🚨 TRACKER WOULD KILL PROCESS (false positive!)")
                print("!" * 80)
                return

    print("\n" + "=" * 80)
    print("Conversation completed successfully (no false positive)")
    print("=" * 80)


def main():
    print("\n" + "=" * 80)
    print("FALSE POSITIVE DEMONSTRATION")
    print("=" * 80)
    print("\nThis demonstrates how NESTED_COMPAT.md's ConversationStateTracker")
    print("would incorrectly kill healthy Claude CLI processes.\n")

    # Scenario 1: Normal conversation start
    print("\n" + "▶" * 40)
    print("SCENARIO 1: Normal conversation with thinking pause")
    print("▶" * 40)

    messages = [
        # Claude starts by explaining what it will do (VERY COMMON)
        {
            'type': 'assistant',
            'message': {
                'content': [
                    {
                        'type': 'text',
                        'text': 'I will read the configuration file to understand the current setup.'
                    }
                ]
            }
        },
    ]

    delays = [
        1.5,  # Wait 1.5 seconds (tracker will detect "hung" after 1s timeout)
    ]

    simulate_conversation(messages, delays)

    # Scenario 2: After completing one task, explaining next steps
    print("\n" + "▶" * 40)
    print("SCENARIO 2: Between tasks with explanation")
    print("▶" * 40)

    messages = [
        # Tool invocation
        {
            'type': 'assistant',
            'message': {
                'content': [
                    {
                        'type': 'tool_use',
                        'id': 'read_1',
                        'name': 'Read',
                        'input': {'file_path': 'config.py'}
                    }
                ]
            }
        },
        # Tool result
        {
            'type': 'user',
            'message': {
                'content': [
                    {
                        'type': 'tool_result',
                        'tool_use_id': 'read_1',
                        'content': 'config = {...}'
                    }
                ]
            }
        },
        # Claude explains what it learned (text-only message)
        {
            'type': 'assistant',
            'message': {
                'content': [
                    {
                        'type': 'text',
                        'text': 'I can see the config uses SQLite. I will now check the database schema.'
                    }
                ]
            }
        },
    ]

    delays = [
        0.1,  # After tool invocation
        0.1,  # After tool result
        1.5,  # After explanation (tracker will detect "hung")
    ]

    simulate_conversation(messages, delays)

    # Scenario 3: What SHOULD trigger hung detection
    print("\n" + "▶" * 40)
    print("SCENARIO 3: Actual hung state (correct detection)")
    print("▶" * 40)

    messages = [
        # Complete work cycle
        {
            'type': 'assistant',
            'message': {
                'content': [
                    {
                        'type': 'tool_use',
                        'id': 'bash_1',
                        'name': 'Bash',
                        'input': {'command': 'echo done'}
                    }
                ]
            }
        },
        {
            'type': 'user',
            'message': {
                'content': [
                    {
                        'type': 'tool_result',
                        'tool_use_id': 'bash_1',
                        'content': 'done\nExit code: 0'
                    }
                ]
            }
        },
        # Final completion message
        {
            'type': 'assistant',
            'message': {
                'content': [
                    {
                        'type': 'text',
                        'text': 'Task completed successfully! All tests pass.'
                    }
                ]
            }
        },
        # NOTE: result message should appear here but doesn't (this is the bug!)
    ]

    delays = [
        0.1,
        0.1,
        1.5,  # After final message, waiting for result message that never comes
    ]

    print("This scenario demonstrates a TRUE hung state:")
    print("- Work was completed")
    print("- Final message was sent")
    print("- Result message expected but never arrives")
    print("- Process hangs in ep_poll")
    print()

    simulate_conversation(messages, delays)

    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print("""
The current implementation in NESTED_COMPAT.md would:

✗ SCENARIO 1: Kill process during normal startup (FALSE POSITIVE)
✗ SCENARIO 2: Kill process between tasks (FALSE POSITIVE)
✓ SCENARIO 3: Correctly detect hung state (TRUE POSITIVE)

The problem: 2 out of 3 scenarios result in killing healthy processes!

WHY THIS HAPPENS:
- Text-only messages occur throughout normal conversation
- The tracker can't distinguish between:
  a) Mid-conversation explanations (normal)
  b) Final completion messages (actual end)

WHAT'S NEEDED:
- Track conversation PHASE (startup, working, completion)
- Only flag as hung during completion phase
- Require evidence of actual work being done first
- Use shorter timeout only after final message pattern detected
""")


if __name__ == '__main__':
    main()
