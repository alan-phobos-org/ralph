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
    IterationResult
)


def test_prompt_size_reasonable():
    """Test that concise template is reasonably sized."""
    print("Testing prompt template size...")

    concise_path = get_concise_outer_prompt_path()
    concise_template = concise_path.read_text()
    concise_tokens = estimate_tokens(concise_template)

    print(f"  Concise template: {len(concise_template)} chars, ~{concise_tokens} tokens")

    # Verify template is not too large (should be under 2000 tokens)
    assert concise_tokens < 2000, f"Template should be <2000 tokens, got {concise_tokens}"

    print("  ✓ Template size verified\n")


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


def test_cache_mode_efficiency():
    """Verify that system prompt cache mode is efficient over 10 iterations."""
    print("Calculating efficiency for 10-iteration run with caching...")

    concise_template = get_concise_outer_prompt_path().read_text()
    user_task = "Implement complete feature with tests and documentation"

    # System prompt cache mode (10 iterations)
    # First iteration: template + user prompt (template cached)
    # Iterations 2-10: user prompt only (cache hit)
    template_tokens = estimate_tokens(concise_template)
    cache_total = template_tokens  # Sent once, cached

    for i in range(1, 11):
        feedback = "✅ Success" if i > 1 else None
        prompt = create_wrapped_prompt(user_task, i, concise_template, feedback, use_system_prompt=True)
        cache_total += estimate_tokens(prompt)

    avg_per_iteration = cache_total / 10

    print(f"  Template (cached once):      ~{template_tokens:,} tokens")
    print(f"  Total (10 iterations):       ~{cache_total:,} input tokens")
    print(f"  Average per iteration:       ~{avg_per_iteration:,.0f} tokens")

    # Verify efficiency: average per iteration should be reasonable
    assert avg_per_iteration < 500, f"Average per iteration too high: {avg_per_iteration:.0f} tokens"

    print("  ✓ Cache mode efficiency verified\n")


if __name__ == '__main__':
    print("=" * 60)
    print("Token Optimization Test Suite")
    print("=" * 60)
    print()

    try:
        test_prompt_size_reasonable()
        test_feedback_compression()
        test_system_prompt_mode()
        test_iteration_token_stability()
        test_cache_mode_efficiency()

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
