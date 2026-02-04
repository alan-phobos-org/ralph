"""Tests for prompt loading from package."""
import pytest
from pathlib import Path
from ralph.core import get_concise_outer_prompt_path


def test_package_prompts_bundled():
    """Verify prompts are bundled in package."""
    from ralph import core
    prompt_path = Path(core.__file__).parent / 'prompts' / 'outer-prompt-concise.md'
    assert prompt_path.exists()
    assert prompt_path.read_text()


def test_get_concise_prompt_from_package():
    """Test loading concise prompt from package."""
    prompt_path = get_concise_outer_prompt_path()
    assert prompt_path.exists()
    assert prompt_path.is_file()

    # Verify it's the package prompt, not a user-installed one
    from ralph import core
    expected_path = Path(core.__file__).parent / 'prompts' / 'outer-prompt-concise.md'
    assert prompt_path == expected_path

    # Verify content is readable
    content = prompt_path.read_text()
    assert len(content) > 0
    assert 'RALPH' in content or 'ralph' in content  # Should contain reference to Ralph
