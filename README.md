# Ralph Loop

Iterative AI agent execution with progress persistence.

Ralph Loop feeds the same prompt repeatedly to an AI agent until the task is complete. Progress persists in files and git, not in context. When context fills, a fresh agent continues from the file state.

## Installation

### From PyPI (when published)

```bash
pip install ralph-loop
```

### From Source

```bash
git clone https://github.com/yourusername/ralph.git
cd ralph
pip install -e .
```

### From Wheel

```bash
python -m build
pip install dist/ralph_loop-0.1.0-py3-none-any.whl
```

## Quick Start

1. Install ralph-loop
2. Navigate to a git repository
3. Run ralph with a task:

```bash
ralph "Fix all type errors" --max-iterations 15
```

On first run, Ralph will automatically install default prompts to `~/.ralph/prompts/`. You can customize these prompts for your workflow.

## Usage

### Basic Commands

```bash
# Run a task
ralph "Implement user authentication" --max-iterations 20

# Read prompt from file
ralph -f task.md --max-iterations 10

# Use different Claude models
ralph "Run tests" --model haiku --max-iterations 5
ralph "Build feature" --model sonnet --max-iterations 15

# Use Codex CLI (defaults: gpt-5.3-codex + xhigh reasoning)
ralph "Fix failing tests" --cli-type codex --max-iterations 10

# Human-in-the-loop mode (pause after each iteration)
ralph "Complex refactor" --human-in-the-loop --max-iterations 30

# Custom stable instructions (Claude: system prompt; Codex: developer instructions)
ralph "Task" --system-prompt "You are an expert Python developer"
```

### Prompt Management

```bash
# Reinstall/reset default prompts
ralph --init

# Use custom outer prompt
ralph "Task" --outer-prompt ./custom-prompt.md
```

Default prompts are installed to `~/.ralph/prompts/` and can be customized.

### Configuration Options

- `--max-iterations N`: Maximum number of iterations (default: 10)
- `--max-turns N`: Maximum turns per iteration (default: 50)
- `--timeout N`: Timeout in seconds per iteration (default: 600)
- `--cli-type {claude,codex}`: Which CLI backend to use (default: claude)
- `--model {opus,sonnet,haiku}`: Claude model to use (default: opus)
- `--codex-model MODEL`: Codex model to use (default: gpt-5.3-codex)
- `--codex-reasoning-effort {low,medium,high,xhigh}`: Codex reasoning effort (default: xhigh)
- `--codex-sandbox {read-only,workspace-write,danger-full-access}`: Codex sandbox policy (default: danger-full-access)
- `--codex-approval-policy {untrusted,on-failure,on-request,never}`: Codex approval policy (default: never)
- `--human-in-the-loop`: Pause after each iteration for review
- `--log-file PATH`: Custom log file path
- `--outer-prompt PATH`: Custom outer prompt template
- `--system-prompt TEXT`: Extra stable instructions appended to the outer prompt + task

## How It Works

Ralph Loop implements a simple but powerful pattern:

1. **External verification** - Agent reviews its own work each iteration
2. **Self-correcting** - Each iteration sees previous changes via git/files
3. **Fresh context** - When context fills, fresh agent continues from file state
4. **File system = truth** - Git history + files persist; LLM memory does not

The agent receives a wrapped prompt with mandatory workflow:
1. Read progress.md (ground truth)
2. Do ONE task only
3. Run quality gates (tests/types/lint)
4. Update progress.md
5. Commit work + progress.md
6. STOP (loop re-invokes for next task)

## Requirements

- Python 3.9+
- Git repository (must be in a git repo to use ralph)
- Claude CLI or Codex CLI

## Development

### Install Development Dependencies

```bash
pip install -e ".[dev]"
```

### Run Tests

```bash
# All tests
pytest -v

# Just installation tests
pytest -m installation -v

# Just prompt loading tests
pytest tests/test_prompt_loading.py -v
```

### Build Wheel

```bash
python -m build
```

## License

MIT

## Documentation

- [RALPH.md](RALPH.md) - Comprehensive documentation and patterns
- [AGENTS.md](AGENTS.md) - Agent instructions and implementation details
