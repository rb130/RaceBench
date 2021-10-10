from typing import List
import tempfile
import json
import os
import subprocess

from utils import *


def repro_has_trigger(out_path: str) -> bool:
    try:
        out = read_file(out_path)
        out = json.loads(out)
        return len(out) > 0
    except FileNotFoundError:
        return False
    except json.JSONDecodeError:
        return False


class Reproducer:
    def __init__(self, cmd: List[str], cwd: str, timeout: float, step_timeout: float):
        self.cmd = cmd
        self.cwd = cwd
        self.timeout = timeout
        self.step_timeout = step_timeout

    def _tempfile(self):
        return tempfile.NamedTemporaryFile(mode="w", suffix=".repro.json", delete=False)

    def run(self, trace_path: str) -> bool:
        exe_path = os.path.join(os.path.dirname(__file__), "..", "gdb_reproduce", "repro.py")
        config = {
            "cmd": self.cmd,
            "cwd": self.cwd,
            "steptime": self.step_timeout,
            "timeout": self.timeout,
            "trace": trace_path,
        }
        with self._tempfile() as f:
            config_file = f.name
            json.dump(config, f)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".out", delete=False) as f:
            out_path = f.name
        subprocess.run(["python3", exe_path, config_file, out_path], check=True,
                       stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        ans = repro_has_trigger(out_path)
        remove_file(out_path)
        remove_file(config_file)
        return ans
