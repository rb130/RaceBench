from typing import List
import json
import tempfile
import subprocess
import os

from utils import *


class Converter:
    def __init__(self, cmd: List[str], srcdir: str, step_timeout: float, cwd: str, timeout: float):
        self.cmd = cmd
        self.srcdir = srcdir
        self.step_timeout = step_timeout
        self.cwd = cwd
        self.timeout = timeout

    def _tempfile(self):
        return tempfile.NamedTemporaryFile(mode="w", suffix=".convert.json", delete=False)

    def run(self, log_path: str, out_path: str):
        exe_path = os.path.join(os.path.dirname(__file__), "..", "gdb_trace", "convert.py")
        config = {
            "cmd": self.cmd,
            "srcdir": self.srcdir,
            "cwd": self.cwd,
            "steptime": self.step_timeout,
            "timeout": self.timeout,
            "log": log_path,
            "output": out_path,
        }
        with self._tempfile() as f:
            config_file = f.name
            json.dump(config, f)
        subprocess.run(["python3", exe_path, config_file], check=True,
                       stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        remove_file(config_file)
        assert os.path.isfile(out_path) and not is_empty_file(out_path)
