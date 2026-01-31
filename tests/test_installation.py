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
