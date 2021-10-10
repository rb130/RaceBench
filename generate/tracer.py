from __future__ import annotations
from typing import Dict, List, Optional, Set
import os
import subprocess
import json
import re
import ast

from general import FileLine, LineLoc
from utils import *


log_pattern = re.compile(r"(\d+) ([=>]) (None|(.*):(\d+))\s*")


class ThreadPos:
    def __init__(self, tid: int, line_loc: LineLoc, file_line: Optional[FileLine]):
        self.tid = tid
        self.line_loc = line_loc
        self.file_line = file_line


def parse_log_line(line: str) -> Optional[ThreadPos]:
    match = log_pattern.match(line)
    if match is None:
        return None
    tid = int(match.group(1))
    line_loc = LineLoc(match.group(2))
    if match.group(3) == "None":
        file_line = None
    else:
        file_line = FileLine(match.group(4), int(match.group(5)))
    return ThreadPos(tid, line_loc, file_line)


def parse_logs(log_path: str) -> List[ThreadPos]:
    lines = read_file(log_path).split("\n")
    ans = []
    for line in lines:
        tpos = parse_log_line(line)
        if tpos is None:
            continue
        ans.append(tpos)
    return ans


def parse_blacklist(black_path: str) -> Dict[str, Set[int]]:
    lines = read_file(black_path).split("\n")
    ans: Dict[str, Set[int]] = dict()
    for line in lines:
        pos = line.find(":")
        if pos == -1:
            continue
        filename = line[:pos].strip()
        lines = ast.literal_eval(line[pos + 1:])
        if filename not in ans:
            ans[filename] = set()
        ans[filename].update(lines)
    return ans


class Trace:
    def __init__(self, positions: List[ThreadPos], blacklist: Dict[str, Set[int]], srcdir: str):
        self.srcdir = srcdir
        self.blacklist = blacklist

        tmax = max(tpos.tid for tpos in positions)
        self.num_threads = tmax + 1

        self.pos_table = [ThreadPos(-1, True, None)]
        self.pos_index = [[0] * (tmax + 1)]
        for tpos in positions:
            idx = len(self.pos_table)
            self.pos_table.append(tpos)
            cur_index = self.pos_index[-1][:]
            cur_index[tpos.tid] = idx
            self.pos_index.append(cur_index)

    def __len__(self) -> int:
        return len(self.pos_table)

    def __getitem__(self, index) -> ThreadPos:
        return self.pos_table[index]

    def thread_pos(self, tnum: int, idx: int) -> ThreadPos:
        return self.pos_table[self.pos_index[idx][tnum]]

    def in_blacklist(self, file_line: FileLine) -> bool:
        filename = file_line.filename
        if filename not in self.blacklist:
            return False
        return file_line.line in self.blacklist[filename]

    @staticmethod
    def run(config_file: str) -> Trace:
        exe_path = os.path.join(os.path.dirname(__file__), "..", "gdb_trace", "trace.py")
        subprocess.run(["python3", exe_path, config_file],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        with open(config_file, "r", encoding='latin-1') as f:
            config = json.load(f)
        cwd = config["cwd"]
        log_path = extend_path(config["log"], cwd)
        black_path = extend_path(config["blacklist"], cwd)
        srcdir = extend_path(config["srcdir"], cwd)
        logs = parse_logs(log_path)
        blacklist = parse_blacklist(black_path)
        return Trace(logs, blacklist, srcdir)
