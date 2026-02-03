"""Tests for prompt loading and installation."""
import pytest
from pathlib import Path
from ralph.core import get_concise_outer_prompt_path, install_user_prompts


def test_package_prompts_bundled():
    """Verify prompts are bundled in package."""
    from ralph import core
    prompt_path = Path(core.__file__).parent / 'prompts' / 'outer-prompt-concise.md'
    assert prompt_path.exists()
    assert prompt_path.read_text()


def test_install_user_prompts(isolated_home):
    """Test installing prompts to ~/.ralph/prompts/."""
    install_user_prompts(force=True)

    user_prompts = isolated_home / '.ralph' / 'prompts'
    assert user_prompts.exists()
    assert (user_prompts / 'outer-prompt-concise.md').exists()


def test_get_concise_prompt_auto_install(isolated_home):
    """Test auto-installation when ~/.ralph/ doesn't exist."""
    prompt_path = get_concise_outer_prompt_path()
    assert prompt_path.exists()
    assert (isolated_home / '.ralph' / 'prompts').exists()
