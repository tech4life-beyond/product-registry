from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _run(cmd: list[str]) -> None:
    p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    assert p.returncode == 0, f"Command failed: {' '.join(cmd)}\nSTDOUT:\n{p.stdout}\nSTDERR:\n{p.stderr}"


def test_build_product_index_check_passes() -> None:
    _run(["python3", "tools/build_product_index.py", "--check"])


def test_validate_registry_passes() -> None:
    _run(["python3", "tools/validate_registry.py"])
