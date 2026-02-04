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
        [sys.executable, "-m", "build", "--wheel", "--outdir", str(build_dir)],
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
