"""Run each Windows GUI scenario with a fresh Tcl/Tk interpreter process."""

import inspect
import os
import subprocess
import sys
from functools import wraps
from pathlib import Path


def isolated_gui_test(case):
    """Keep Tcl state from earlier GUI cases out of each test's startup.

    The child runs the same pytest case, including its fixtures and assertions.
    A failure or timeout fails the parent test; no GUI checks are skipped/retried.
    """
    node = f"{Path(inspect.getfile(case)).resolve().as_posix()}::{case.__name__}"

    @wraps(case)
    def run(*args, **kwargs):
        if os.environ.get("SUBDAV_GUI_CHILD_CASE") == node:
            return case(*args, **kwargs)
        env = os.environ.copy()
        env["SUBDAV_GUI_CHILD_CASE"] = node
        result = subprocess.run(
            [sys.executable, "-m", "pytest", node, "-q", "--tb=short"],
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr

    return run
