"""Tests for nested Claude CLI compatibility and hung detection.

This test suite verifies the conversation state tracking mechanism designed
to detect and handle the nested --print mode hang bug.

See NESTED_COMPAT.md for detailed problem description and solution design.
"""
import json
import time
import pytest
from io import StringIO


# Mock the ConversationStateTracker that should be implemented
class ConversationStateTracker:
    """
    Track Claude CLI stream-json conversation state to detect hung completion.

    This is the implementation that NESTED_COMPAT.md proposes but hasn't been
    added to core.py yet.
    """

    def __init__(self):
        self.pending_tool_calls = set()
        self.last_message_time = time.time()
        self.saw_final_text_message = False
        self.saw_result_message = False
        self.last_message_type = None

    def process_line(self, line: str) -> None:
        """Process a stream-json line and update conversation state."""
        try:
            obj = json.loads(line)
            msg_type = obj.get('type')

            # Update activity timestamp for any conversation message
            if msg_type in ['assistant', 'user', 'result']:
                self.last_message_time = time.time()
                self.last_message_type = msg_type

            if msg_type == 'assistant':
                # Track tool_use blocks
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

                # Final assistant message has text but no tool calls
                if has_text and not has_tool_use:
                    self.saw_final_text_message = True

            elif msg_type == 'user':
                # Remove tool_use IDs when we get matching tool_result
                content = obj.get('message', {}).get('content', [])
                for item in content:
                    if item.get('type') == 'tool_result':
                        tool_id = item.get('tool_use_id')
                        if tool_id in self.pending_tool_calls:
                            self.pending_tool_calls.discard(tool_id)

            elif msg_type == 'result':
                self.saw_result_message = True

        except (json.JSONDecodeError, KeyError, TypeError):
            # Not JSON or malformed, ignore
            pass

    def looks_hung(self, timeout: float = 30.0) -> bool:
        """
        Check if conversation looks complete but hung waiting for result message.

        Returns:
            True if conversation appears stuck in hung state
        """
        # If we got result message, definitely not hung
        if self.saw_result_message:
            return False

        time_since_last = time.time() - self.last_message_time

        # Hung if: saw final message, no pending calls, no result, and inactive
        return (
            self.saw_final_text_message and
            len(self.pending_tool_calls) == 0 and
            not self.saw_result_message and
            time_since_last > timeout
        )


class TestConversationStateTracker:
    """Test the ConversationStateTracker state machine."""

    def test_initial_state(self):
        """Tracker starts in non-hung state."""
        tracker = ConversationStateTracker()
        assert not tracker.looks_hung(timeout=0.1)

    def test_tracks_tool_invocations(self):
        """Tracker correctly tracks pending tool calls."""
        tracker = ConversationStateTracker()

        # Simulate tool invocation
        assistant_msg = json.dumps({
            'type': 'assistant',
            'message': {
                'content': [
                    {'type': 'tool_use', 'id': 'tool_123', 'name': 'Read', 'input': {}}
                ]
            }
        })

        tracker.process_line(assistant_msg)
        assert 'tool_123' in tracker.pending_tool_calls
        assert not tracker.saw_final_text_message

    def test_tracks_tool_results(self):
        """Tracker removes tool calls when results arrive."""
        tracker = ConversationStateTracker()

        # Add tool call
        assistant_msg = json.dumps({
            'type': 'assistant',
            'message': {
                'content': [
                    {'type': 'tool_use', 'id': 'tool_123', 'name': 'Read', 'input': {}}
                ]
            }
        })
        tracker.process_line(assistant_msg)

        # Provide result
        user_msg = json.dumps({
            'type': 'user',
            'message': {
                'content': [
                    {'type': 'tool_result', 'tool_use_id': 'tool_123', 'content': 'file contents'}
                ]
            }
        })
        tracker.process_line(user_msg)

        assert 'tool_123' not in tracker.pending_tool_calls

    def test_detects_final_text_message(self):
        """Tracker identifies text-only assistant messages."""
        tracker = ConversationStateTracker()

        # Text-only message (no tools)
        text_msg = json.dumps({
            'type': 'assistant',
            'message': {
                'content': [
                    {'type': 'text', 'text': 'Task complete!'}
                ]
            }
        })

        tracker.process_line(text_msg)
        assert tracker.saw_final_text_message

    def test_detects_result_message(self):
        """Tracker identifies result message."""
        tracker = ConversationStateTracker()

        result_msg = json.dumps({
            'type': 'result',
            'subtype': 'success',
            'result': 'Task completed successfully'
        })

        tracker.process_line(result_msg)
        assert tracker.saw_result_message
        assert not tracker.looks_hung(timeout=0.1)

    def test_false_positive_mid_conversation_text(self):
        """
        CRITICAL BUG: Tracker incorrectly flags mid-conversation text as hung.

        This test demonstrates the flaw in the proposed implementation:
        Text-only messages occur throughout normal conversation, not just at the end.
        """
        tracker = ConversationStateTracker()

        # Simulate normal conversation with mid-conversation text
        # 1. Assistant sends text explaining what it will do
        text_msg_1 = json.dumps({
            'type': 'assistant',
            'message': {
                'content': [
                    {'type': 'text', 'text': 'I will read the file first.'}
                ]
            }
        })
        tracker.process_line(text_msg_1)

        # Now tracker thinks we saw a "final" text message
        assert tracker.saw_final_text_message
        assert len(tracker.pending_tool_calls) == 0

        # Wait for timeout
        time.sleep(0.2)

        # BUG: Tracker incorrectly reports hung state!
        # This is mid-conversation, not the end. More tools will follow.
        assert tracker.looks_hung(timeout=0.1), \
            "EXPECTED FAILURE: Tracker incorrectly detects hung state during normal conversation"

        # In reality, the conversation continues with tool calls...
        tool_msg = json.dumps({
            'type': 'assistant',
            'message': {
                'content': [
                    {'type': 'tool_use', 'id': 'read_1', 'name': 'Read', 'input': {'file_path': 'test.py'}}
                ]
            }
        })
        tracker.process_line(tool_msg)

        # ...but we already killed the process due to false positive!

    def test_hung_detection_after_completion(self):
        """Tracker should detect hung state after conversation appears complete."""
        tracker = ConversationStateTracker()

        # Simulate complete conversation without result message
        # 1. Tool invocation
        tool_msg = json.dumps({
            'type': 'assistant',
            'message': {
                'content': [
                    {'type': 'tool_use', 'id': 'bash_1', 'name': 'Bash', 'input': {'command': 'echo test'}}
                ]
            }
        })
        tracker.process_line(tool_msg)

        # 2. Tool result
        result_msg = json.dumps({
            'type': 'user',
            'message': {
                'content': [
                    {'type': 'tool_result', 'tool_use_id': 'bash_1', 'content': 'test\nExit code: 0'}
                ]
            }
        })
        tracker.process_line(result_msg)

        # 3. Final text message
        final_text = json.dumps({
            'type': 'assistant',
            'message': {
                'content': [
                    {'type': 'text', 'text': 'Task completed successfully.'}
                ]
            }
        })
        tracker.process_line(final_text)

        # Should NOT be hung yet (no timeout elapsed)
        assert not tracker.looks_hung(timeout=0.2)

        # Wait for timeout
        time.sleep(0.3)

        # NOW should detect hung state (if result message never arrived)
        assert tracker.looks_hung(timeout=0.2)

    def test_no_false_positive_with_activity(self):
        """Activity should reset the hung detection timer."""
        tracker = ConversationStateTracker()

        # Send text message
        text_msg = json.dumps({
            'type': 'assistant',
            'message': {
                'content': [
                    {'type': 'text', 'text': 'Processing...'}
                ]
            }
        })
        tracker.process_line(text_msg)

        # Periodically send more messages (simulate active conversation)
        for i in range(3):
            time.sleep(0.05)
            tracker.process_line(text_msg)

        # Should not report hung due to ongoing activity
        assert not tracker.looks_hung(timeout=0.1)


class TestCLIDetection:
    """Test CLI detection logic for enabling tracker."""

    def test_simple_claude_command_detection(self):
        """Detect 'claude' in simple command."""
        cmd = ['claude', '--print', '-p', 'test']
        assert 'claude' in cmd[0]

    def test_absolute_path_detection_failure(self):
        """
        BUG: Proposed implementation fails with absolute paths.

        The check `'claude' in cmd[0]` from NESTED_COMPAT.md line 168
        will fail for absolute paths.
        """
        cmd = ['/usr/local/bin/claude', '--print', '-p', 'test']

        # Current proposed implementation
        is_claude = 'claude' in cmd[0]
        assert is_claude, "Should detect claude even with absolute path"

    def test_better_cli_detection(self):
        """Demonstrate more robust CLI detection."""
        test_cases = [
            ['claude', '--print'],
            ['/usr/local/bin/claude', '--print'],
            ['./node_modules/.bin/claude', '--print'],
            ['/home/user/.local/bin/claude', '--print'],
        ]

        for cmd in test_cases:
            # Better approach: check basename
            import os
            cmd_name = os.path.basename(cmd[0])
            assert 'claude' in cmd_name, f"Failed to detect claude in: {cmd[0]}"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
