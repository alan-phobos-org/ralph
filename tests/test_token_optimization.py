#!/usr/bin/env python3
"""
Test token optimization features.

This test validates that the system prompt caching optimizations work correctly.
"""
import sys
from pathlib import Path

# Add src to path for testing
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from ralph.core import (
    create_wrapped_prompt,
    extract_iteration_feedback,
    estimate_tokens,
    get_concise_outer_prompt_path,
    get_default_outer_prompt_path,
    IterationResult
)


def test_prompt_size_reduction():
    """Test that concise template is smaller than default."""
    print("Testing prompt template sizes...")

    default_path = get_default_outer_prompt_path()
    concise_path = get_concise_outer_prompt_path()

    default_template = default_path.read_text()
    concise_template = concise_path.read_text()

    default_tokens = estimate_tokens(default_template)
    concise_tokens = estimate_tokens(concise_template)

    print(f"  Default template: {len(default_template)} chars, ~{default_tokens} tokens")
    print(f"  Concise template: {len(concise_template)} chars, ~{concise_tokens} tokens")

    reduction_pct = ((default_tokens - concise_tokens) / default_tokens) * 100
    print(f"  Reduction: {reduction_pct:.1f}%")

    assert concise_tokens < default_tokens, "Concise template should be smaller"
    assert reduction_pct > 40, f"Should reduce by >40%, got {reduction_pct:.1f}%"

    print("  ✓ Template size reduction verified\n")


def test_feedback_compression():
    """Test that compressed feedback is smaller."""
    print("Testing feedback compression...")

    # Simulate various result types
    test_cases = [
        ("success", IterationResult(success=True, output="test", iteration_num=1)),
        ("max_turns", IterationResult(success=False, output="test", iteration_num=1, max_turns_reached=True)),
        ("timeout", IterationResult(success=False, output="test", iteration_num=1, timeout_occurred=True)),
        ("compaction", IterationResult(success=False, output="test", iteration_num=1, compaction_detected=True)),
        ("error", IterationResult(success=False, output="test", error="Something failed", iteration_num=1)),
    ]

    for name, result in test_cases:
        feedback = extract_iteration_feedback(result)
        tokens = estimate_tokens(feedback)
        print(f"  {name:12s}: {len(feedback):3d} chars, ~{tokens:3d} tokens - {feedback[:60]}")

        # All feedback should be under 100 tokens now
        assert tokens < 100, f"{name} feedback too large: {tokens} tokens"

    print("  ✓ Feedback compression verified\n")


def test_system_prompt_mode():
    """Test that system prompt mode creates minimal user prompts."""
    print("Testing system prompt mode...")

    concise_template = get_concise_outer_prompt_path().read_text()
    user_task = "Implement feature X"

    # Legacy mode (full wrapped prompt)
    legacy_prompt = create_wrapped_prompt(
        user_task,
        iteration_num=1,
        outer_prompt_template=concise_template,
        feedback=None,
        use_system_prompt=False
    )

    # System prompt mode (minimal user prompt)
    system_mode_prompt = create_wrapped_prompt(
        user_task,
        iteration_num=1,
        outer_prompt_template=concise_template,
        feedback=None,
        use_system_prompt=True
    )

    legacy_tokens = estimate_tokens(legacy_prompt)
    system_tokens = estimate_tokens(system_mode_prompt)

    print(f"  Legacy mode: {len(legacy_prompt)} chars, ~{legacy_tokens} tokens")
    print(f"  System mode: {len(system_mode_prompt)} chars, ~{system_tokens} tokens")

    reduction_pct = ((legacy_tokens - system_tokens) / legacy_tokens) * 100
    print(f"  Reduction: {reduction_pct:.1f}%")

    # System mode should be MUCH smaller (should only contain task + metadata)
    assert system_tokens < legacy_tokens * 0.2, "System mode should be <20% of legacy size"

    print("  ✓ System prompt mode verified\n")


def test_iteration_token_stability():
    """Test that tokens don't grow significantly across iterations."""
    print("Testing iteration-to-iteration token stability...")

    concise_template = get_concise_outer_prompt_path().read_text()
    user_task = "Implement feature X"

    # Simulate 5 iterations with system prompt mode
    iteration_tokens = []

    for i in range(1, 6):
        # Simulate feedback (only for iterations > 1)
        feedback = None
        if i > 1:
            result = IterationResult(success=True, output="test", iteration_num=i-1)
            feedback = extract_iteration_feedback(result)

        prompt = create_wrapped_prompt(
            user_task,
            iteration_num=i,
            outer_prompt_template=concise_template,
            feedback=feedback,
            use_system_prompt=True
        )

        tokens = estimate_tokens(prompt)
        iteration_tokens.append(tokens)
        print(f"  Iteration {i}: ~{tokens} tokens")

    # Check that growth is minimal (should be < 50 tokens per iteration)
    max_growth = max(iteration_tokens) - min(iteration_tokens)
    print(f"  Max growth: {max_growth} tokens")

    assert max_growth < 50, f"Token growth too large: {max_growth} tokens"

    print("  ✓ Token stability verified\n")


def test_total_savings():
    """Calculate total savings for a typical 10-iteration run."""
    print("Calculating total savings for 10-iteration run...")

    default_template = get_default_outer_prompt_path().read_text()
    concise_template = get_concise_outer_prompt_path().read_text()
    user_task = "Implement complete feature with tests and documentation"

    # Legacy mode (10 iterations)
    legacy_total = 0
    for i in range(1, 11):
        feedback = "✅ Success" if i > 1 else None
        prompt = create_wrapped_prompt(user_task, i, default_template, feedback, use_system_prompt=False)
        legacy_total += estimate_tokens(prompt)

    # System prompt cache mode (10 iterations)
    # First iteration: template + user prompt (template cached)
    # Iterations 2-10: user prompt only (cache hit)
    template_tokens = estimate_tokens(concise_template)
    cache_total = template_tokens  # Sent once, cached

    for i in range(1, 11):
        feedback = "✅ Success" if i > 1 else None
        prompt = create_wrapped_prompt(user_task, i, concise_template, feedback, use_system_prompt=True)
        cache_total += estimate_tokens(prompt)

    savings = legacy_total - cache_total
    savings_pct = (savings / legacy_total) * 100

    print(f"  Legacy mode (10 iterations): ~{legacy_total:,} input tokens")
    print(f"  Cache mode (10 iterations):  ~{cache_total:,} input tokens")
    print(f"  Savings: ~{savings:,} tokens ({savings_pct:.1f}%)")

    assert savings_pct > 75, f"Should save >75% tokens, got {savings_pct:.1f}%"

    print("  ✓ Total savings verified\n")


if __name__ == '__main__':
    print("=" * 60)
    print("Token Optimization Test Suite")
    print("=" * 60)
    print()

    try:
        test_prompt_size_reduction()
        test_feedback_compression()
        test_system_prompt_mode()
        test_iteration_token_stability()
        test_total_savings()

        print("=" * 60)
        print("✅ ALL TESTS PASSED")
        print("=" * 60)
        sys.exit(0)

    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
