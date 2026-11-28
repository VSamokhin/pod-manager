"""Keep the Python version in step everywhere it is named.

Dependabot can move the Dockerfile base image to a new Python minor, but not the CI
setup-python version or the ruff/mypy/requires-python settings in pyproject.toml.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_python_version_is_consistent():
    docker = re.search(r"^FROM python:(\d+\.\d+)", (ROOT / "Dockerfile").read_text(), re.M)
    ci = re.search(r'PYTHON_VERSION: "(\d+\.\d+)"', (ROOT / ".github/workflows/ci.yml").read_text())
    pyproject = (ROOT / "pyproject.toml").read_text()
    requires = re.search(r'requires-python = ">=(\d+\.\d+)"', pyproject)
    mypy = re.search(r'python_version = "(\d+\.\d+)"', pyproject)
    ruff = re.search(r'target-version = "py(\d)(\d+)"', pyproject)
    assert docker and ci and requires and mypy and ruff
    versions = {
        "Dockerfile": docker.group(1),
        "ci.yml": ci.group(1),
        "requires-python": requires.group(1),
        "mypy": mypy.group(1),
        "ruff": f"{ruff.group(1)}.{ruff.group(2)}",
    }
    assert len(set(versions.values())) == 1, versions
