from __future__ import annotations
from typing import Dict, List
import os
import re

from general import *
from utils import write_file


BadExtensions = {".h", ".hpp", ".hxx"}

PatternIndent = re.compile(r"^(\s*)")


def indent_of_line(line: str) -> str:
    return PatternIndent.search(line).group(1)


class InjectChecker:
    PatternBlock = re.compile(r"\{|\}")
    PatternLable = re.compile(r"\b(case)?\s*\w+:")
    PatternJump = re.compile(r"\b(break|continue|goto|return|longjmp)\b")

    def __init__(self, blacklist: List[str]):
        self.blacklist = set(blacklist)
        self.line_cache = dict()

    def build_cache(self, filename: str):
        with open(filename, "r", encoding='latin-1') as f:
            lines = f.readlines()
        line_good = [self.is_good_line(line) for line in lines]
        self.line_cache[filename] = line_good

    def can_insert_before(self, filename: str, line: int) -> bool:
        ext = os.path.splitext(filename)[1]
        if ext in BadExtensions:
            return False
        filename = os.path.abspath(filename)
        if os.path.basename(filename) in self.blacklist:
            return False
        if filename not in self.line_cache:
            self.build_cache(filename)
        cache = self.line_cache[filename]
        return line == 0 or line > len(cache) or cache[line - 1]

    @staticmethod
    def is_good_line(line: str) -> bool:
        line = line.rstrip("\n")
        if '\n' in line:
            return False
        if InjectChecker.PatternBlock.search(line):
            return False
        if InjectChecker.PatternLable.search(line):
            return False
        if InjectChecker.PatternJump.search(line):
            return False
        if line.strip().startswith("#"):
            return False
        return True


class CodeAccumulator:
    def __init__(self):
        self.lines: List[str] = []

    def add_code_line(self, line: str) -> int:
        lineno = self.current_line()
        self.lines.append(line)
        return lineno

    def current_line(self) -> int:
        return len(self.lines) + 1

    def to_str(self) -> str:
        return "\n".join(self.lines)


class Injector:
    def __init__(self):
        self.ops: Dict[str, List[InsertionPoint]] = dict()

    def add(self, loc: InjectLocation, codes: List[str]) -> InsertionPoint:
        filename = os.path.abspath(loc.filename)
        if filename not in self.ops:
            self.ops[filename] = []
        ins_point = InsertionPoint(loc, codes)
        self.ops[filename].append(ins_point)
        return ins_point

    def commit(self):
        for filename, insertion in self.ops.items():
            with open(filename, "r", encoding='latin-1') as f:
                raw_lines = f.readlines()

            insertion = insertion[:]
            for lineno, code in enumerate(raw_lines):
                lineno += 1
                code = code.rstrip("\r\n")
                loc = InjectLocation(FileLine(filename, lineno), LineLoc.Middle)
                insertion.append(InsertionPoint(loc, [code]))
            insertion.sort(key=lambda x: (x.loc.line, x.loc.line_loc.value))

            acc = CodeAccumulator()
            last_lineno = -1
            indent = ""

            for ins in insertion:
                lineno = ins.loc.line
                if lineno != last_lineno:
                    last_lineno = lineno
                    raw_line = raw_lines[lineno - 1] if lineno >= 1 else ""
                    indent = indent_of_line(raw_line)

                for i in range(ins.code_len):
                    code = ins.get_code(i)
                    if ins.loc.line_loc != LineLoc.Middle:
                        code = indent + code
                    new_lineno = acc.add_code_line(code)
                    ins.set_result_line(i, new_lineno)
                ins.set_result_line(ins.code_len, acc.current_line())

            write_file(filename, acc.to_str())

        self.ops.clear()
