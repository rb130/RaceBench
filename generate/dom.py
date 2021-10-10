from typing import List
from enum import Enum
import os
import subprocess


class DomMode(Enum):
    Any = 0
    PreOnly = 1
    PostOnly = 2
    Both = 3


class DomAnalyzer:
    def __init__(self, build_path: str):
        self.build_path = build_path
        curdir = os.path.dirname(__file__)
        self.dom_exe = os.path.join(curdir, "dom", "dom")

    def query(self, file_name: str, line: int, mode: DomMode) -> List[int]:
        file_name = os.path.join(self.build_path, file_name)
        cmd = [self.dom_exe,
               "-p", self.build_path,
               "--source", file_name,
               "--line", str(line),
               "--mode", str(mode.value)]
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=True)
        ans = proc.stdout.split()
        ans = [int(x) for x in ans]
        return ans
