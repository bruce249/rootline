from __future__ import annotations

import shutil
import subprocess


def available() -> bool:
    if shutil.which("entire") is None:
        return False
    proc = subprocess.run(["entire", "brain", "--help"], capture_output=True, text=True)
    return proc.returncode == 0
