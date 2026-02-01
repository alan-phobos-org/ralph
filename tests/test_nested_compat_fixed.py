"""Tests for the FIXED nested Claude CLI compatibility solution.

This test suite verifies that the phase-aware ConversationStateTracker
correctly handles all scenarios without false positives.

See NESTED_COMPAT_FIXED.md for the improved solution design.
"""
import json
import time
import pytest
from typing import Optional


class ConversationStateTracker:
    """
    Phase-aware conversation state tracker - FIXED VERSION.

    This implementation addresses the false positive issues in the original design.
    """

    def __init__(self):
        # Tool tracking
        self.pending_tool_calls = set()
        self.tool_invocation_count = 0
        self.last_tool_invocation_time: Optional[float] = None

        # Message tracking
        self.last_message_time = time.time()
        self.last_text_only_message_time: Optional[float] = None
        self.consecutive_text_only_messages = 0

        # Completion signals
        self.saw_result_message = False

        # Phase tracking
        self._conversation_start_time = time.time()

    @property
    def has_done_work(self) -> bool:
        """True if any tools have been invoked."""
        return self.tool_invocation_count > 0

    @property
    def in_completion_phase(self) -> bool:
        """True if conversation appears to be in completion phase."""
        if not self.has_done_work:
            return False

        if len(self.pending_tool_calls) > 0:
            return False

        if self.last_text_only_message_time is None:
            return False

        # Require multiple consecutive text messages
        if self.consecutive_text_only_messages < 2:
            return False

        return True

    @property
    def time_since_last_activity(self) -> float:
        """Seconds since last message."""
        return time.time() - self.last_message_time

    @property
    def time_since_last_tool(self) -> Optional[float]:
        """Seconds since last tool invocation."""
        if self.last_tool_invocation_time is None:
            return None
        return time.time() - self.last_tool_invocation_time

    def process_line(self, line: str) -> None:
        """Process a stream-json line and update conversation state."""
        try:
            obj = json.loads(line)
            msg_type = obj.get('type')

            if msg_type in ['assistant', 'user', 'result']:
                self.last_message_time = time.time()

            if msg_type == 'assistant':
                content = obj.get('message', {}).get('content', [])
                has_tool_use = False
                has_text = False

                for item in content:
                    if item.get('type') == 'tool_use':
                        tool_id = item.get('id')
                        if tool_id:
                            self.pending_tool_calls.add(tool_id)
                            self.tool_invocation_count += 1
                            self.last_tool_invocation_time = time.time()
                        has_tool_use = True
                    elif item.get('type') == 'text':
                        has_text = True

                # Track text-only messages
                if has_text and not has_tool_use:
                    self.last_text_only_message_time = time.time()
                    self.consecutive_text_only_messages += 1
                elif has_tool_use:
                    self.consecutive_text_only_messages = 0

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

    def looks_hung(self,
                   completion_timeout: float = 20.0,
                   initialization_timeout: float = 90.0) -> bool:
        """Check if conversation appears hung."""
        # Never hung if we got result message
        if self.saw_result_message:
            return False

        # Phase 1: Initialization
        if not self.has_done_work:
            return self.time_since_last_activity > initialization_timeout

        # Phase 2: Active work
        if len(self.pending_tool_calls) > 0:
            return False

        # Phase 3: Completion
        # If clearly in completion phase (2+ consecutive texts), apply completion timeout
        if self.in_completion_phase:
            return self.time_since_last_activity > completion_timeout

        # Still in active phase if tools invoked recently (and not in completion phase)
        if self.time_since_last_tool is not None and self.time_since_last_tool < 30.0:
            return False

        # Default: Use longer timeout
        return self.time_since_last_activity > initialization_timeout

    def get_state_summary(self) -> dict:
        """Get current state for debugging."""
        return {
            'has_done_work': self.has_done_work,
            'tool_invocations': self.tool_invocation_count,
            'pending_tools': len(self.pending_tool_calls),
            'consecutive_text_messages': self.consecutive_text_only_messages,
            'in_completion_phase': self.in_completion_phase,
            'saw_result': self.saw_result_message,
            'time_since_activity': f"{self.time_since_last_activity:.1f}s",
        }


class TestPhaseAwareTracker:
    """Test the improved phase-aware tracker."""

    def test_initial_state(self):
        """Tracker starts in initialization phase."""
        tracker = ConversationStateTracker()
        assert not tracker.has_done_work
        assert not tracker.in_completion_phase
        assert not tracker.looks_hung(completion_timeout=0.1, initialization_timeout=0.2)

    def test_initialization_phase_long_timeout(self):
        """Initialization phase uses longer timeout."""
        tracker = ConversationStateTracker()

        # Send text message (no tools yet)
        text_msg = json.dumps({
            'type': 'assistant',
            'message': {
                'content': [
                    {'type': 'text', 'text': 'Analyzing the task...'}
                ]
            }
        })
        tracker.process_line(text_msg)

        # Short pause - not hung (using initialization timeout)
        time.sleep(0.15)
        assert not tracker.looks_hung(completion_timeout=0.1, initialization_timeout=0.2)

        # Longer pause - would be hung with short timeout, but not in initialization
        time.sleep(0.1)
        assert not tracker.looks_hung(completion_timeout=0.1, initialization_timeout=0.5)

    def test_no_false_positive_single_text_message(self):
        """
        CRITICAL FIX: Single text message should NOT trigger hung detection.

        This was the main bug in the original implementation.
        """
        tracker = ConversationStateTracker()

        # Simulate: Tool → Result → Single Text (planning next step)
        tool_msg = json.dumps({
            'type': 'assistant',
            'message': {
                'content': [
                    {'type': 'tool_use', 'id': 'read_1', 'name': 'Read', 'input': {}}
                ]
            }
        })
        tracker.process_line(tool_msg)

        result_msg = json.dumps({
            'type': 'user',
            'message': {
                'content': [
                    {'type': 'tool_result', 'tool_use_id': 'read_1', 'content': 'file contents'}
                ]
            }
        })
        tracker.process_line(result_msg)

        # Single text message (mid-conversation)
        text_msg = json.dumps({
            'type': 'assistant',
            'message': {
                'content': [
                    {'type': 'text', 'text': 'I can see the configuration uses SQLite. Let me check the schema...'}
                ]
            }
        })
        tracker.process_line(text_msg)

        # Wait beyond completion timeout
        time.sleep(0.25)

        # Should NOT be hung - only 1 consecutive text message
        assert tracker.consecutive_text_only_messages == 1
        assert not tracker.in_completion_phase
        assert not tracker.looks_hung(completion_timeout=0.2)

        # More work follows...
        tool_msg_2 = json.dumps({
            'type': 'assistant',
            'message': {
                'content': [
                    {'type': 'tool_use', 'id': 'grep_1', 'name': 'Grep', 'input': {}}
                ]
            }
        })
        tracker.process_line(tool_msg_2)

        # Consecutive text counter resets on tool invocation
        assert tracker.consecutive_text_only_messages == 0

    def test_completion_phase_requires_multiple_texts(self):
        """Completion phase requires 2+ consecutive text messages."""
        tracker = ConversationStateTracker()

        # Do some work
        tool_msg = json.dumps({
            'type': 'assistant',
            'message': {
                'content': [
                    {'type': 'tool_use', 'id': 'bash_1', 'name': 'Bash', 'input': {}}
                ]
            }
        })
        tracker.process_line(tool_msg)

        result_msg = json.dumps({
            'type': 'user',
            'message': {
                'content': [
                    {'type': 'tool_result', 'tool_use_id': 'bash_1', 'content': 'done'}
                ]
            }
        })
        tracker.process_line(result_msg)

        # First text message
        text_1 = json.dumps({
            'type': 'assistant',
            'message': {
                'content': [
                    {'type': 'text', 'text': 'Task completed!'}
                ]
            }
        })
        tracker.process_line(text_1)

        # Not in completion phase yet (only 1 text message)
        assert tracker.consecutive_text_only_messages == 1
        assert not tracker.in_completion_phase

        # Second consecutive text message
        text_2 = json.dumps({
            'type': 'assistant',
            'message': {
                'content': [
                    {'type': 'text', 'text': 'All tests pass.'}
                ]
            }
        })
        tracker.process_line(text_2)

        # NOW in completion phase (2+ consecutive texts)
        assert tracker.consecutive_text_only_messages == 2
        assert tracker.in_completion_phase

    def test_detects_hung_in_completion_phase(self):
        """Correctly detects hung state in completion phase."""
        tracker = ConversationStateTracker()

        # Complete work cycle
        tool_msg = json.dumps({
            'type': 'assistant',
            'message': {
                'content': [
                    {'type': 'tool_use', 'id': 'bash_1', 'name': 'Bash', 'input': {}}
                ]
            }
        })
        tracker.process_line(tool_msg)

        result_msg = json.dumps({
            'type': 'user',
            'message': {
                'content': [
                    {'type': 'tool_result', 'tool_use_id': 'bash_1', 'content': 'done'}
                ]
            }
        })
        tracker.process_line(result_msg)

        # Multiple completion messages
        for text in ['Task complete!', 'All tests pass.']:
            msg = json.dumps({
                'type': 'assistant',
                'message': {
                    'content': [
                        {'type': 'text', 'text': text}
                    ]
                }
            })
            tracker.process_line(msg)

        # In completion phase
        assert tracker.in_completion_phase

        # Wait for timeout
        time.sleep(0.25)

        # Should detect hung (completion phase + timeout)
        assert tracker.looks_hung(completion_timeout=0.2)

    def test_active_work_never_hung(self):
        """Active work (pending tools) never flags as hung."""
        tracker = ConversationStateTracker()

        # Invoke tool
        tool_msg = json.dumps({
            'type': 'assistant',
            'message': {
                'content': [
                    {'type': 'tool_use', 'id': 'slow_1', 'name': 'Bash', 'input': {}}
                ]
            }
        })
        tracker.process_line(tool_msg)

        # Wait a long time (simulating slow command)
        time.sleep(0.3)

        # Should NOT be hung - tool is pending
        assert len(tracker.pending_tool_calls) == 1
        assert not tracker.looks_hung(completion_timeout=0.1, initialization_timeout=0.2)

    def test_single_text_after_recent_tool_not_hung(self):
        """Single text message after recent tool activity is not hung."""
        tracker = ConversationStateTracker()

        # Invoke and complete tool
        tool_msg = json.dumps({
            'type': 'assistant',
            'message': {
                'content': [
                    {'type': 'tool_use', 'id': 'bash_1', 'name': 'Bash', 'input': {}}
                ]
            }
        })
        tracker.process_line(tool_msg)

        result_msg = json.dumps({
            'type': 'user',
            'message': {
                'content': [
                    {'type': 'tool_result', 'tool_use_id': 'bash_1', 'content': 'done'}
                ]
            }
        })
        tracker.process_line(result_msg)

        # Send SINGLE text message (explaining findings, about to do more work)
        msg = json.dumps({
            'type': 'assistant',
            'message': {
                'content': [
                    {'type': 'text', 'text': 'I found the configuration. Let me check the database schema...'}
                ]
            }
        })
        tracker.process_line(msg)

        # Only 1 consecutive text - not in completion phase
        assert tracker.consecutive_text_only_messages == 1
        assert not tracker.in_completion_phase

        # Wait and check - should not be hung (only 1 text, more work coming)
        time.sleep(0.25)
        assert not tracker.looks_hung(completion_timeout=0.2)

    def test_result_message_prevents_hung(self):
        """Result message always prevents hung detection."""
        tracker = ConversationStateTracker()

        # Set up completion phase
        tool_msg = json.dumps({
            'type': 'assistant',
            'message': {
                'content': [
                    {'type': 'tool_use', 'id': 'bash_1', 'name': 'Bash', 'input': {}}
                ]
            }
        })
        tracker.process_line(tool_msg)

        result_msg = json.dumps({
            'type': 'user',
            'message': {
                'content': [
                    {'type': 'tool_result', 'tool_use_id': 'bash_1', 'content': 'done'}
                ]
            }
        })
        tracker.process_line(result_msg)

        # Multiple texts
        for text in ['Done!', 'Success!']:
            msg = json.dumps({
                'type': 'assistant',
                'message': {
                    'content': [
                        {'type': 'text', 'text': text}
                    ]
                }
            })
            tracker.process_line(msg)

        # Result message arrives
        final_result = json.dumps({
            'type': 'result',
            'subtype': 'success',
            'result': 'Task completed'
        })
        tracker.process_line(final_result)

        # Wait beyond timeout
        time.sleep(0.3)

        # Should NOT be hung - got result message
        assert tracker.saw_result_message
        assert not tracker.looks_hung(completion_timeout=0.1)

    def test_state_summary_for_debugging(self):
        """State summary provides useful debugging info."""
        tracker = ConversationStateTracker()

        # Do some work
        tool_msg = json.dumps({
            'type': 'assistant',
            'message': {
                'content': [
                    {'type': 'tool_use', 'id': 'read_1', 'name': 'Read', 'input': {}}
                ]
            }
        })
        tracker.process_line(tool_msg)

        state = tracker.get_state_summary()

        assert state['has_done_work'] is True
        assert state['tool_invocations'] == 1
        assert state['pending_tools'] == 1
        assert state['consecutive_text_messages'] == 0
        assert state['in_completion_phase'] is False
        assert state['saw_result'] is False


class TestScenarioValidation:
    """Test against real-world scenarios."""

    def test_scenario_startup_with_long_pause(self):
        """No false positive during startup with long thinking pause."""
        tracker = ConversationStateTracker()

        # Claude analyzes task (text-only)
        text = json.dumps({
            'type': 'assistant',
            'message': {
                'content': [
                    {'type': 'text', 'text': 'Let me analyze the requirements...'}
                ]
            }
        })
        tracker.process_line(text)

        # Long pause while Claude thinks (60 seconds)
        # Using short timeout for test, but conceptually this is < initialization_timeout
        time.sleep(0.1)

        # Should NOT be hung (initialization phase, no work done yet)
        assert not tracker.has_done_work
        assert not tracker.looks_hung(completion_timeout=0.05, initialization_timeout=0.2)

    def test_scenario_between_tasks(self):
        """No false positive between tasks with explanation."""
        tracker = ConversationStateTracker()

        # Task 1: Read file
        tool_msg = json.dumps({
            'type': 'assistant',
            'message': {
                'content': [
                    {'type': 'tool_use', 'id': 'read_1', 'name': 'Read', 'input': {}}
                ]
            }
        })
        tracker.process_line(tool_msg)

        result_msg = json.dumps({
            'type': 'user',
            'message': {
                'content': [
                    {'type': 'tool_result', 'tool_use_id': 'read_1', 'content': 'config data'}
                ]
            }
        })
        tracker.process_line(result_msg)

        # Explain findings (single text)
        text = json.dumps({
            'type': 'assistant',
            'message': {
                'content': [
                    {'type': 'text', 'text': 'I found the configuration. Now checking dependencies...'}
                ]
            }
        })
        tracker.process_line(text)

        # Pause while planning next action
        time.sleep(0.25)

        # Should NOT be hung (only 1 consecutive text, not in completion phase)
        assert tracker.consecutive_text_only_messages == 1
        assert not tracker.in_completion_phase
        assert not tracker.looks_hung(completion_timeout=0.2)

    def test_scenario_actual_completion_hang(self):
        """Correctly detects actual hung completion."""
        tracker = ConversationStateTracker()

        # Do real work
        tool_msg = json.dumps({
            'type': 'assistant',
            'message': {
                'content': [
                    {'type': 'tool_use', 'id': 'bash_1', 'name': 'Bash', 'input': {}}
                ]
            }
        })
        tracker.process_line(tool_msg)

        result_msg = json.dumps({
            'type': 'user',
            'message': {
                'content': [
                    {'type': 'tool_result', 'tool_use_id': 'bash_1', 'content': 'success'}
                ]
            }
        })
        tracker.process_line(result_msg)

        # Multiple completion messages
        for text in ['Task completed successfully!', 'All requirements met.']:
            msg = json.dumps({
                'type': 'assistant',
                'message': {
                    'content': [
                        {'type': 'text', 'text': text}
                    ]
                }
            })
            tracker.process_line(msg)

        # Now in completion phase, waiting for result message that never comes
        assert tracker.in_completion_phase

        # Hang for 20+ seconds (simulated with 0.25s for test)
        time.sleep(0.25)

        # Should detect hung
        assert tracker.looks_hung(completion_timeout=0.2)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
