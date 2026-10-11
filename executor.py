from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

TIMEOUT_SECONDS = float(os.getenv("EXECUTION_TIMEOUT_SECONDS", "3"))


def execute_python_code(code: str) -> dict:
    """Execute code outside the API process and return unmodified stdout/traceback."""
    with tempfile.TemporaryDirectory(prefix="code-interpreter-") as temp_dir:
        script = Path(temp_dir) / "submitted.py"
        script.write_text(code, encoding="utf-8")
        env = {"PATH": os.environ.get("PATH", ""), "PYTHONIOENCODING": "utf-8", "PYTHONNOUSERSITE": "1"}
        try:
            completed = subprocess.run(
                [sys.executable, "-I", "-S", str(script)],
                cwd=temp_dir,
                env=env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=TIMEOUT_SECONDS,
                shell=False,
            )
        except subprocess.TimeoutExpired:
            return {"success": False, "output": "Traceback (most recent call last):\nExecutionTimeout: code execution exceeded the time limit\n"}
        if completed.returncode == 0:
            return {"success": True, "output": completed.stdout}
        return {"success": False, "output": completed.stderr or completed.stdout}
