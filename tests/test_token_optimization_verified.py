"""Test to verify token optimization changes are in place."""
from pathlib import Path


def test_concise_prompt_has_optimization_rules():
    """Verify outer-prompt-concise.md contains token optimization rules."""
    concise_prompt = Path.home() / '.ralph' / 'prompts' / 'outer-prompt-concise.md'
    
    assert concise_prompt.exists(), "Concise prompt not installed"
    
    content = concise_prompt.read_text()
    
    # Check for key optimization directives
    assert "TOKEN OPTIMIZATION" in content
    assert "BATCH file reads" in content
    assert "PARALLEL" in content
    assert "DO NOT narrate" in content or "narrate actions" in content.lower()
    assert "concise" in content.lower()


def test_default_prompt_has_optimization_rules():
    """Verify outer-prompt-default.md contains token optimization rules."""
    default_prompt = Path.home() / '.ralph' / 'prompts' / 'outer-prompt-default.md'
    
    assert default_prompt.exists(), "Default prompt not installed"
    
    content = default_prompt.read_text()
    
    # Check for key optimization directives
    assert "TOKEN OPTIMIZATION" in content
    assert "BATCH file reads" in content or "batch" in content.lower()
    assert "PARALLEL" in content
    assert "concise" in content.lower()


def test_agents_md_documents_optimization():
    """Verify AGENTS.md documents token optimization strategy."""
    agents_md = Path(__file__).parent.parent / 'AGENTS.md'
    
    assert agents_md.exists()
    
    content = agents_md.read_text()
    
    # Check for token optimization documentation
    assert "Token Optimization" in content
    assert "output tokens" in content.lower()
    assert "parallel" in content.lower() or "batch" in content.lower()
