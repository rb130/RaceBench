from __future__ import annotations
import random
from typing import Callable, Dict, List, Set, Tuple

from general import *
from executor import CodePieceExecutor
from piece import BlockEnd, IfCond, IfdefBug, IfdefEnd
from tracer import ThreadPos, Trace
from variable import Variable


class Bug:
    def __init__(self, bug_id: int, input_file: str):
        self.bug_id = bug_id
        self.input_file = input_file
        self.sites: Dict[FileLine, CodeSite] = dict()
        self.log = BugLog()
        self.order = Interleave()
        self.all_vars: List[Variable] = list()

    def get_code(self, loc: FileLine) -> List[CodeLazy]:
        if loc not in self.sites:
            return []
        return self.sites[loc].get_code()

    def get_site(self, loc: FileLine) -> CodeSite:
        if loc not in self.sites:
            self.sites[loc] = CodeSite(loc)
        return self.sites[loc]

    def append_code(self, loc: FileLine, code: CodeReserve) -> CodeLazy:
        lazy = CodeLazy(code)
        site = self.get_site(loc)
        if len(site.get_code()) == 0:
            site.append_code(CodeLazy(Reserved(IfdefBug, self.bug_id)))
        site.append_code(lazy)
        return lazy

    def append_ifdef_end(self):
        for site in self.sites.values():
            if len(site.get_code()) == 0:
                continue
            lazy = CodeLazy(Reserved(IfdefEnd))
            lazy.generate(State())
            site.append_code(lazy)

    def get_all_files(self) -> Set[str]:
        return set(loc.filename for loc in self.sites.keys())

    def add_vars(self, var: List[Variable]):
        self.all_vars.extend(var)

    def append_order(self, item: ThreadPointer) -> int:
        return self.order.append(item)

    def iter_code_sites(self):
        return self.sites.items()

    def dump_order(self, file_name: str):
        with open(file_name, "w", encoding='latin-1') as f:
            for tp in self.order:
                f.write(tp.str_new_line() + '\n')


class BugLog:
    def __init__(self):
        self.items: List[Dict] = []

    def add_location(self, tid: int, fileline: FileLine):
        self.items.append({
            "type": "next",
            "thread": tid,
            "file": fileline.filename,
            "line": fileline.line,
        })

    def add_pattern(self, name: str, locs: List[Tuple[int, FileLine]]):
        locs = [
            {
                "thread": tid,
                "file": loc.filename,
                "line": loc.line
            } for tid, loc in locs
        ]
        self.items.append({
            "type": "pattern",
            "name": name,
            "locations": locs,
        })

    def add_assume(self, name: str):
        self.items.append({
            "type": "assume",
            "outcome": name,
        })

    def get_items(self):
        return self.items


class TraceWalker:
    def __init__(self, trace: Trace, bug: Bug, checker: Callable[[FileLine], bool]):
        self.trace = trace
        self.bug = bug
        self.checker = checker
        self.current = 0
        self.used_tnum: Set[int] = set()

    def move_to(self, index: int):
        assert index >= self.current
        if index == self.current:
            return
        for i in range(self.current + 1, index + 1):
            tpos = self.trace[i]
            if tpos.file_line is None:
                exloc = None
            else:
                site = self.bug.get_site(tpos.file_line)
                if tpos.line_loc == LineLoc.Middle:
                    exloc = site.exloc_middle()
                else:
                    exloc = site.exloc_start()
            self.bug.append_order(ThreadPointer(tpos.tid, exloc, tpos.line_loc))
        self.current = index
        self.used_tnum.clear()

    def _thread_pos(self, tnum: int) -> Optional[ThreadPos]:
        pos = self.trace.thread_pos(tnum, self.current)
        if pos.file_line and self.checker(pos.file_line):
            return pos
        return None

    def available_pos(self) -> List[ThreadPointer]:
        if self.current >= len(self.trace):
            return []
        tpos = []
        for tnum in range(self.trace.num_threads):
            if tnum in self.used_tnum:
                continue
            pos = self._thread_pos(tnum)
            if pos and pos.line_loc == LineLoc.Before:
                site = self.bug.get_site(pos.file_line)
                tpos.append(ThreadPointer(tnum, site.exloc_current()))
        return tpos

    def get_available_pos_at(self, index: int) -> List[Tuple[int, FileLine]]:
        if index >= len(self.trace):
            return []
        ans = []
        for tnum in range(self.trace.num_threads):
            if index == self.current and tnum in self.used_tnum:
                continue
            pos = self.trace.thread_pos(tnum, index)
            if pos.file_line is None or pos.line_loc != LineLoc.Before:
                continue
            if not self.checker(pos.file_line):
                continue
            ans.append((pos.tid, pos.file_line))
        return ans

    def mark_use(self, tnum: int):
        self.used_tnum.add(tnum)

    def get_one_pos(self) -> ThreadPointer:
        tpos = self.available_pos()
        if len(tpos) == 0:
            raise ValueError("no available position")
        tpos = random.choice(tpos)
        self.mark_use(tpos.tid)
        return tpos


class BugExecWrap:
    def __init__(self, bug: Bug, executor: CodePieceExecutor):
        self.bug = bug
        self.executor = executor
        self.generate = False

    def set_generate(self, generate: bool):
        self.generate = generate

    def execute(self, order_index: int, file_line: FileLine, code_ptr: int):
        code = self.bug.get_code(file_line)[code_ptr]
        if code.code is None:
            if not self.generate:
                raise ValueError("code has not been generated")
            if order_index < code.after_order:
                # skip generation and don't run any code
                # but we still need to change the skip level
                if code.base == IfCond:
                    self.executor.inc_skip_level()
                elif code.base == BlockEnd:
                    self.executor.dec_skip_level()
                return
            code.generate(self.executor.state)
        self.executor.run(code.code)

    def max_code_ptr(self, file_line: FileLine) -> int:
        return len(self.bug.get_code(file_line))
