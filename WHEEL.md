# Plan: Productionize ralph.py as Installable Python Wheel

## Overview
Convert ralph.py into a production-ready Python package that builds a wheel installable on macOS and Ubuntu, with a `ralph` CLI command and prompts installed to `~/.ralph/` on first run.

## Key Requirements
- ✅ Clean project structure optimized for packaging
- ✅ Use pyproject.toml with modern best practices
- ✅ Default prompts bundled in wheel, installed to ~/.ralph/ on first use
- ✅ pytest-based tests with .venv fixtures to verify wheel installation
- ✅ Cross-platform support (macOS + Ubuntu)
- ✅ Command name: `ralph` (not `ralph.py`)

## Project Structure

```
ralph/
├── pyproject.toml              # Modern packaging config (to create)
├── README.md                   # Updated with installation docs
├── src/
│   └── ralph/
│       ├── __init__.py        # Package init, version export (to create)
│       ├── __main__.py        # Entry point for python -m ralph (to create)
│       ├── core.py            # Renamed from ralph.py (to modify)
│       ├── _version.py        # Single source of truth for version (to create)
│       └── prompts/           # Default prompts as package data (to move)
│           ├── outer-prompt-default.md
│           ├── prompt-code-review.md
│           ├── prompt-macos-sre-tools.md
│           └── prompt-og-command-line.md
├── tests/
│   ├── conftest.py            # Pytest fixtures for .venv, wheel building (to create)
│   ├── test_prompt_loading.py # Test prompt discovery logic (to create)
│   └── test_installation.py   # Wheel installation smoke tests (to create)
└── docs/                      # Move/symlink existing docs
    ├── AGENTS.md
    ├── RALPH.md
    └── CLAUDE.md
```

## Critical Changes to ralph.py → core.py

### 1. Prompt Loading (lines 1413-1415)
Replace hardcoded path with fallback logic:

```python
def get_default_outer_prompt_path() -> Path:
    """Get default outer prompt with fallback: ~/.ralph/prompts/ → package data."""
    user_prompts = Path.home() / '.ralph' / 'prompts' / 'outer-prompt-default.md'
    if user_prompts.exists():
        return user_prompts

    # Fallback to package data
    package_prompts = Path(__file__).parent / 'prompts' / 'outer-prompt-default.md'
    if package_prompts.exists():
        return package_prompts

    raise FileNotFoundError(
        "Could not find outer-prompt-default.md. "
        "Run 'ralph --init' to install default prompts."
    )
```

### 2. Add Prompt Installation Function

```python
def install_user_prompts(force: bool = False) -> None:
    """Copy default prompts from package to ~/.ralph/prompts/."""
    user_prompts_dir = Path.home() / '.ralph' / 'prompts'
    package_prompts_dir = Path(__file__).parent / 'prompts'

    if user_prompts_dir.exists() and not force:
        print(f"Prompts already installed at {user_prompts_dir}")
        return

    user_prompts_dir.mkdir(parents=True, exist_ok=True)

    for prompt_file in package_prompts_dir.glob('*.md'):
        dest = user_prompts_dir / prompt_file.name
        dest.write_text(prompt_file.read_text(encoding='utf-8'))
        print(f"Installed: {dest}")

    print(f"\n✓ Prompts installed to {user_prompts_dir}")
    print("You can now customize these prompts for your workflow.")
```

### 3. Add --init CLI Argument (line ~1308)

```python
parser.add_argument('--init', action='store_true',
                   help='Install default prompts to ~/.ralph/prompts/ for customization')
```

### 4. Handle --init in main() (line ~1412)

```python
def main() -> int:
    parser = setup_argument_parser()
    args = parser.parse_args()

    # Handle init command
    if args.init:
        install_user_prompts(force=False)
        return 0

    # Existing logic continues...
```

### 5. Minor Cleanup
- Remove shebang (line 1): `#!/usr/bin/env python3`
- No changes needed to log file path (already uses /tmp, works on both platforms)

## New Files to Create

### src/ralph/_version.py
```python
__version__ = "0.1.0"
```

### src/ralph/__init__.py
```python
"""Ralph Loop: Iterative AI agent execution with progress persistence."""

from ralph._version import __version__
from ralph.core import main

__all__ = ['main', '__version__']
```

### src/ralph/__main__.py
```python
"""Entry point for python -m ralph."""
import sys
from ralph.core import main

if __name__ == '__main__':
    sys.exit(main())
```

### pyproject.toml
```toml
[build-system]
requires = ["setuptools>=61.0", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "ralph-loop"
version = "0.1.0"
description = "Iterative AI agent execution with progress persistence"
readme = "README.md"
requires-python = ">=3.9"
license = {text = "MIT"}
keywords = ["ai", "agent", "automation", "llm", "iteration"]
classifiers = [
    "Development Status :: 4 - Beta",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.9",
    "Programming Language :: Python :: 3.10",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
    "Operating System :: POSIX :: Linux",
    "Operating System :: MacOS :: MacOS X",
]

dependencies = []  # Pure stdlib!

[project.optional-dependencies]
dev = [
    "pytest>=7.0",
    "pytest-timeout>=2.1",
    "build>=0.10",
]

[project.scripts]
ralph = "ralph.core:main"

[tool.setuptools]
package-dir = {"" = "src"}

[tool.setuptools.packages.find]
where = ["src"]
include = ["ralph*"]

[tool.setuptools.package-data]
ralph = ["prompts/*.md"]

[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = "test_*.py"
timeout = 300
addopts = "-v"
markers = [
    "slow: marks tests as slow",
    "integration: marks tests as integration tests",
    "installation: marks tests that verify wheel installation",
]
```

### tests/conftest.py
```python
"""Pytest fixtures for ralph testing."""
import os
import subprocess
import sys
from pathlib import Path
import pytest


@pytest.fixture(scope="session")
def test_venv(tmp_path_factory):
    """Create isolated virtualenv for installation testing."""
    venv_dir = tmp_path_factory.mktemp("venv")

    subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], check=True)

    if sys.platform == "win32":
        python_path = venv_dir / "Scripts" / "python.exe"
        pip_path = venv_dir / "Scripts" / "pip.exe"
    else:
        python_path = venv_dir / "bin" / "python"
        pip_path = venv_dir / "bin" / "pip"

    subprocess.run([str(python_path), "-m", "pip", "install", "--upgrade", "pip"],
                   check=True, capture_output=True)

    yield {
        "venv_dir": venv_dir,
        "python": python_path,
        "pip": pip_path,
    }


@pytest.fixture(scope="session")
def built_wheel(tmp_path_factory):
    """Build wheel once for all installation tests."""
    project_root = Path(__file__).parent.parent
    build_dir = tmp_path_factory.mktemp("build")

    subprocess.run(
        ["python", "-m", "build", "--wheel", "--outdir", str(build_dir)],
        cwd=project_root,
        capture_output=True,
        check=True
    )

    wheels = list(build_dir.glob("*.whl"))
    assert len(wheels) == 1, f"Expected 1 wheel, found {len(wheels)}"

    return wheels[0]


@pytest.fixture
def isolated_home(tmp_path, monkeypatch):
    """Mock HOME directory for testing prompt installation."""
    monkeypatch.setenv("HOME", str(tmp_path))
    return tmp_path
```

### tests/test_prompt_loading.py
```python
"""Tests for prompt loading and installation."""
import pytest
from pathlib import Path
from ralph.core import get_default_outer_prompt_path, install_user_prompts


def test_package_prompts_bundled():
    """Verify prompts are bundled in package."""
    from ralph import core
    prompt_path = Path(core.__file__).parent / 'prompts' / 'outer-prompt-default.md'
    assert prompt_path.exists()
    assert prompt_path.read_text()


def test_install_user_prompts(isolated_home):
    """Test installing prompts to ~/.ralph/prompts/."""
    install_user_prompts()

    user_prompts = isolated_home / '.ralph' / 'prompts'
    assert user_prompts.exists()
    assert (user_prompts / 'outer-prompt-default.md').exists()


def test_get_default_prompt_fallback_to_package():
    """Test fallback to package data when ~/.ralph/ doesn't exist."""
    # This uses real home dir, so it tests the fallback path
    prompt_path = get_default_outer_prompt_path()
    assert prompt_path.exists()
```

### tests/test_installation.py
```python
"""Wheel installation smoke tests."""
import subprocess
import os
import pytest


@pytest.mark.installation
def test_wheel_installs(test_venv, built_wheel):
    """Verify wheel installs without errors."""
    result = subprocess.run(
        [str(test_venv["pip"]), "install", str(built_wheel)],
        capture_output=True,
        text=True
    )
    assert result.returncode == 0


@pytest.mark.installation
def test_ralph_command_exists(test_venv, built_wheel):
    """Verify 'ralph' command is available after install."""
    subprocess.run([str(test_venv["pip"]), "install", str(built_wheel)], check=True)

    result = subprocess.run(
        [str(test_venv["python"]), "-m", "ralph", "--help"],
        capture_output=True,
        text=True
    )
    assert result.returncode == 0
    assert "Ralph Loop" in result.stdout


@pytest.mark.installation
def test_prompts_bundled_in_wheel(test_venv, built_wheel):
    """Verify prompt files are accessible in installed package."""
    subprocess.run([str(test_venv["pip"]), "install", str(built_wheel)], check=True)

    result = subprocess.run(
        [str(test_venv["python"]), "-c",
         "from pathlib import Path; import ralph.core; "
         "p = Path(ralph.core.__file__).parent / 'prompts' / 'outer-prompt-default.md'; "
         "print(p.exists())"],
        capture_output=True,
        text=True,
        check=True
    )
    assert "True" in result.stdout


@pytest.mark.installation
def test_init_command(test_venv, built_wheel, tmp_path):
    """Verify --init installs prompts to user directory."""
    subprocess.run([str(test_venv["pip"]), "install", str(built_wheel)], check=True)

    env = os.environ.copy()
    env["HOME"] = str(tmp_path)

    result = subprocess.run(
        [str(test_venv["python"]), "-m", "ralph", "--init"],
        capture_output=True,
        text=True,
        env=env
    )

    assert result.returncode == 0
    assert (tmp_path / '.ralph' / 'prompts' / 'outer-prompt-default.md').exists()


@pytest.mark.installation
def test_version_accessible(test_venv, built_wheel):
    """Verify package version is accessible."""
    subprocess.run([str(test_venv["pip"]), "install", str(built_wheel)], check=True)

    result = subprocess.run(
        [str(test_venv["python"]), "-c", "import ralph; print(ralph.__version__)"],
        capture_output=True,
        text=True,
        check=True
    )
    assert result.stdout.strip().startswith("0.")
```

## Implementation Steps

1. **Restructure project** (30 min)
   - Create `src/ralph/` directory
   - Move `prompts/` → `src/ralph/prompts/`
   - Move `ralph.py` → `src/ralph/core.py`
   - Create new files: `__init__.py`, `__main__.py`, `_version.py`
   - Move docs to `docs/` (or create symlinks)

2. **Update core.py** (45 min)
   - Remove shebang line
   - Add `get_default_outer_prompt_path()` function
   - Add `install_user_prompts()` function
   - Add `--init` argument to parser
   - Handle `--init` in `main()` function

3. **Create pyproject.toml** (15 min)
   - Define package metadata
   - Set entry point: `ralph = ralph.core:main`
   - Include package data: `prompts/*.md`
   - Configure pytest

4. **Create test infrastructure** (60 min)
   - Write `tests/conftest.py` with fixtures
   - Write `tests/test_prompt_loading.py`
   - Write `tests/test_installation.py`

5. **Build and verify** (30 min)
   - Install build: `pip install build`
   - Build wheel: `python -m build`
   - Create test venv: `python3 -m venv test_venv`
   - Install wheel: `test_venv/bin/pip install dist/*.whl`
   - Test commands: `test_venv/bin/ralph --help`, `--init`

6. **Run test suite** (15 min)
   - Install dev deps: `pip install -e ".[dev]"`
   - Run tests: `pytest -v`
   - Run installation tests: `pytest -m installation -v`

7. **Update documentation** (20 min)
   - Update README.md with installation instructions
   - Add examples for `pip install ralph-loop`
   - Document `ralph --init` usage

## Critical Files

- ralph.py → `src/ralph/core.py` - Modify prompt loading (lines 1413-1415), add `install_user_prompts()`, handle `--init`
- prompts/outer-prompt-default.md → `src/ralph/prompts/` - Must be bundled as package data
- .gitignore - Add: `dist/`, `build/`, `*.egg-info`, `src/ralph.egg-info/`

## Verification Steps

### 1. Development Installation Test
```bash
pip install -e ".[dev]"
ralph --help  # Should show help
python -m ralph --help  # Should work too
```

### 2. Wheel Build Test
```bash
python -m build
ls -lh dist/  # Should show .whl and .tar.gz
```

### 3. Clean Installation Test
```bash
python3 -m venv fresh_venv
fresh_venv/bin/pip install dist/ralph_loop-0.1.0-py3-none-any.whl
fresh_venv/bin/ralph --version
fresh_venv/bin/ralph --init
ls -la ~/.ralph/prompts/  # Should show installed prompts
```

### 4. Functional Test
```bash
cd /tmp
mkdir test_repo && cd test_repo
git init
git config user.email "test@test.com"
git config user.name "Test"
echo "# Test" > README.md
git add README.md
git commit -m "Initial"

# Test ralph execution
fresh_venv/bin/ralph "Create a simple hello.py script" --max-iterations 2
```

### 5. Pytest Test Suite
```bash
pytest -v  # All tests
pytest -m installation -v  # Just installation tests
```

### 6. Cross-Platform Verification
- Test on macOS (current platform)
- Test on Ubuntu (VM or GitHub Actions)

## Success Criteria

- ✅ `python -m build` produces valid wheel
- ✅ Wheel installs cleanly with pip
- ✅ `ralph` command available after installation
- ✅ `ralph --help` shows correct usage
- ✅ `ralph --init` installs prompts to ~/.ralph/prompts/
- ✅ Default prompts work from package when ~/.ralph/ doesn't exist
- ✅ All pytest tests pass
- ✅ Works on both macOS and Ubuntu
- ✅ No external dependencies (pure stdlib)
- ✅ Entry point creates executable `ralph` command

## Notes

- **No dependencies**: ralph.py uses only stdlib, preserve this
- **Backward compatibility**: First release, no compatibility concerns
- **User experience**: Prompts work out-of-box, `--init` for customization
- **Testing strategy**: Use existing test patterns (standalone scripts) for unit tests, add pytest for wheel verification
- **Platform support**: Already cross-platform (uses Path, subprocess), just verify on Ubuntu
