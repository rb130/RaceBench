from __future__ import annotations
from enum import Enum
from functools import partial
from itertools import chain
import random
from typing import Callable, List, Set, Tuple, Type
from bug import *
from dom import DomAnalyzer, DomMode
from codegen import CodeGenerator
from piece import *
from general import *
from variable import VarType


MIN_ASSIGN_LEN = 3


class BugPattern:
    def __init__(self, name: str,
                 code0: List[List[CodeReserve]], code1: List[List[CodeReserve]],
                 order: List[int], dom_mode: DomMode):
        self.name = name
        self.code0 = code0
        self.code1 = code1
        self.order = order
        self.dom_mode = dom_mode
        self.used_vars: Set[str] = set()
        for code in chain(*(code0 + code1)):
            self.used_vars.update(code.used_vars())

    def get_codes(self, part: int, index: int) -> List[CodeReserve]:
        return (self.code0, self.code1)[part][index]


class BasePattern:
    LockProb = 0.2

    def __init__(self, gen: CodeGenerator):
        self.gen = gen

    def list_all_generators(self) -> List[Callable[[], BugPattern]]:
        raise NotImplementedError

    def add_locks(self,
                  code0: List[List[CodeReserve]], lock0: List[bool],
                  code1: List[List[CodeReserve]], lock1: List[bool]):
        lvar = self.gen.new_var(VarType.Lock)
        for code, lock in zip([code0, code1], [lock0, lock1]):
            for i in range(len(code)):
                if not (lock[i] or random.random() < self.LockProb):
                    continue
                c = code[i]
                c.insert(0, Reserved(LockOp, lvar, True))
                c.append(Reserved(LockOp, lvar, False))


class AtomicityViolation(BasePattern):

    class AccType(Enum):
        WWA = 0
        RWA = 1
        WAW = 2

    def generate(self, acc_type: AtomicityViolation.AccType) -> BugPattern:
        code0: List[List[CodeReserve]]
        code1: List[List[CodeReserve]]
        lock0: List[bool]
        lock1: List[bool]
        order: List[int]
        dom_mode: DomMode
        if acc_type == AtomicityViolation.AccType.WWA:
            """
            code0:
                v1 {
                    tvar = ...
                    var = tvar
                }
                assume var == tvar
            code1:
                v2 {
                    var = ...
                }
            """
            var = self.gen.new_var(editable=False)
            tvar = self.gen.new_var(editable=False)
            v1 = self.gen.new_assign_many(tvar, MIN_ASSIGN_LEN)
            v1.append(Reserved(AssignVar, var, tvar))
            v2 = self.gen.new_assign_many(var, MIN_ASSIGN_LEN)
            ck = Reserved(Assume, ReservedExpr("==", [var, tvar]))
            code0 = [[*v1], [ck]]
            code1 = [[*v2]]
            lock0 = [True, False]
            lock1 = [False]
            order = [0, 1, 0]
            dom_mode = DomMode.PreOnly
        elif acc_type == AtomicityViolation.AccType.RWA:
            """
            code0:
                v1 {
                    tmp = var
                }
                assume var == tmp
            code1:
                v2 {
                    var = ...
                }
            """
            var = self.gen.old_var(need_edit=True)
            self.gen.set_editable(var, False)
            tmp = self.gen.new_var(editable=False)
            v1 = Reserved(AssignVar, tmp, var)
            v2 = self.gen.new_assign_many(var, MIN_ASSIGN_LEN)
            ck = Reserved(Assume, ReservedExpr("==", [var, tmp]))
            code0 = [[v1], [ck]]
            code1 = [[*v2]]
            lock0 = [False, False]
            lock1 = [False]
            order = [0, 1, 0]
            dom_mode = DomMode.PreOnly
        elif acc_type == AtomicityViolation.AccType.WAW:
            """
            code0:
                v1 {
                    tmp1 = ...
                    var = tmp1
                }
                v2 {
                    tmp2 = ...
                    var = tmp2
                }
            code1:
                if (var != 0)
                    assume var == tmp2
            """
            var = self.gen.new_var(editable=False)
            v1 = self.gen.new_assign_many(var, MIN_ASSIGN_LEN)
            tmp1 = self.gen.new_var(editable=True)
            v1 = self.gen.new_assign_many(tmp1, MIN_ASSIGN_LEN)
            v1.append(Reserved(AssignVar, var, tmp1))
            tmp2 = self.gen.new_var(editable=False)
            v2 = self.gen.new_assign_many(tmp2, MIN_ASSIGN_LEN)
            v2.append(Reserved(AssignVar, var, tmp2))
            ck0 = Reserved(IfCond, ReservedExpr("!=", [var, DefaultValue]))
            ck1 = Reserved(Assume, ReservedExpr("==", [var, tmp2]))
            code0 = [[*v1], [*v2]]
            code1 = [[ck0, ck1, Reserved(BlockEnd)]]
            lock0 = [False, True]
            lock1 = [False]
            order = [0, 1, 0]
            dom_mode = DomMode.PostOnly
        else:
            raise ValueError("acc_type error")

        self.add_locks(code0, lock0, code1, lock1)
        return BugPattern(acc_type.name, code0, code1, order, dom_mode)

    def list_all_generators(self) -> List[Callable[[], BugPattern]]:
        ans = []
        for acc in AtomicityViolation.AccType:
            func = partial(self.generate, acc_type=acc)
            ans.append(func)
        return ans


class OrderViolation(BasePattern):

    class OpType(Enum):
        NoWait = 0
        Disorder = 1
        #Spurious = 2
        Sleep = 3

    def generate(self, op_type: OrderViolation.OpType) -> BugPattern:
        code0: List[List[CodeReserve]]
        code1: List[List[CodeReserve]]
        dom_mode: DomMode
        if op_type == OrderViolation.OpType.NoWait:
            # TODO: too easy
            """
            code0:
                assume var == tmp
            code1:
                v1 {
                    tmp = ...
                    var = tmp
                }
            """
            tmp = self.gen.new_var(editable=False)
            var = self.gen.new_var(editable=False)
            v1 = self.gen.new_assign_many(tmp, MIN_ASSIGN_LEN)
            v1.append(Reserved(AssignVar, var, tmp))
            ck = Reserved(Assume, ReservedExpr("==", [var, tmp]))
            code0 = [[ck]]
            code1 = [[*v1]]
            lock0 = [False]
            lock1 = [True]
            order = [0, 1]
            dom_mode = DomMode.Any
        elif op_type == OrderViolation.OpType.Disorder:
            """
            code0:
                if (cvar) {
                    assume var == tmp
                }
            code1:
                c1 {
                    cvar = 1
                }
                v1 {
                    tmp = ...
                    var = tmp
                }
            """
            var = self.gen.new_var(editable=False)
            tmp = self.gen.new_var(editable=False)
            cvar = self.gen.new_var(editable=False)
            cond = Reserved(IfCond, ReservedExpr("!=", [cvar, DefaultValue]))
            c1 = Reserved(AssignImm, cvar, TVal(DefaultValue + 1))
            v1 = self.gen.new_assign_many(tmp, MIN_ASSIGN_LEN)
            v1.append(Reserved(AssignVar, var, tmp))
            ck = Reserved(Assume, ReservedExpr("==", [var, tmp]))
            code0 = [[cond, ck, Reserved(BlockEnd)]]
            code1 = [[c1], [*v1]]
            lock0 = [False]
            lock1 = [False, True]
            order = [1, 0, 1]
            dom_mode = DomMode.PostOnly
        elif op_type == OrderViolation.OpType.Sleep:
            """
            code0:
                v0 {
                    sleep()
                }
                assume var == tmp
            code1:
                v1 {
                    tmp = ...
                    var = tmp
                }
            """
            tmp = self.gen.new_var(editable=False)
            var = self.gen.new_var(editable=False)
            v1 = self.gen.new_assign_many(tmp, MIN_ASSIGN_LEN)
            v1.append(Reserved(AssignVar, var, tmp))
            ck = Reserved(Assume, ReservedExpr("==", [var, tmp]))
            v0 = Reserved(Sleep, self.gen.sleep_time)
            code0 = [[v0], [ck]]
            code1 = [[*v1]]
            lock0 = [False, False]
            lock1 = [True]
            order = [0, 1, 0]
            dom_mode = DomMode.PreOnly
        else:
            raise ValueError("op_type error")

        self.add_locks(code0, lock0, code1, lock1)
        return BugPattern(op_type.name, code0, code1, order, dom_mode)

    def list_all_generators(self) -> List[Callable[[], BugPattern]]:
        ans = []
        for op in OrderViolation.OpType:
            func = partial(self.generate, op_type=op)
            ans.append(func)
        return ans


class StepMarker:
    def __init__(self, step: int, tid: int, file_line: FileLine):
        self.step = step
        self.tid = tid
        self.file_line = file_line


class PatternGenerator:
    MarkLocationSteps = 50
    base_patterns: List[Type[BasePattern]] = [AtomicityViolation, OrderViolation]

    def __init__(self, bug: Bug, gen: CodeGenerator, dom: DomAnalyzer):
        self.bug = bug
        self.code_gen = gen
        self.dom = dom
        self.generators: List[Callable[[], BugPattern]] = []
        for g in self.base_patterns:
            g = g(self.code_gen)
            self.generators += g.list_all_generators()

    def generate(self, walker: TraceWalker) -> Tuple[BugPattern, List[StepMarker], List[StepMarker]]:
        generator = random.choice(self.generators)
        bug_pattern = generator()
        locs0, locs1 = self.get_locations(bug_pattern, walker)

        for i in [0, 1]:
            locs = (locs0, locs1)[i]
            codes = (bug_pattern.code0, bug_pattern.code1)[i]
            while len(codes) > len(locs):
                locs.append(locs[-1])

        return bug_pattern, locs0, locs1

    def get_locations(self, pattern: BugPattern, walker: TraceWalker):
        locs_init = walker.available_pos()
        random.shuffle(locs_init)
        locs0 = [StepMarker(0, locs_init[0].tid, locs_init[0].file_line)]
        locs1 = [StepMarker(0, locs_init[1].tid, locs_init[1].file_line)]

        avoid_vars = pattern.used_vars
        max_part_len = max(len(pattern.code0), len(pattern.code1))
        min_part_len = min(len(pattern.code0), len(pattern.code1))
        if max_part_len == 1:
            return locs0, locs1
        assert max_part_len == 2 and min_part_len == 1

        next_locs: List[StepMarker] = list()
        for step in range(1, self.MarkLocationSteps):
            cur_index = walker.current + step
            if cur_index == len(walker.trace):
                break
            tpos = walker.trace[cur_index]
            if not (tpos.line_loc == LineLoc.Before and tpos.file_line):
                continue
            if not walker.checker(tpos.file_line):
                continue

            keep0 = keep1 = False
            for _tid, pos in walker.get_available_pos_at(cur_index):
                if pos is locs0[-1].file_line:
                    keep0 = True
                if pos is locs1[-1].file_line:
                    keep1 = True
            if not keep1:
                if not keep0:
                    break
                if step != 0:
                    break
                locs0, locs1 = locs1, locs0

            pos = tpos.file_line
            if pos == locs1[-1].file_line:
                break
            exist_code = self.bug.get_code(tpos.file_line)
            if any(avoid_vars & code.reserved.edit_vars() for code in exist_code):
                break
            next_locs.append(StepMarker(step, tpos.tid, pos))

        first_loc = locs0[0].file_line
        good_lines = self.dom.query(first_loc.filename, first_loc.line, pattern.dom_mode)
        good_lines = set(good_lines)
        next_locs = list(filter(
            lambda tloc: tloc.file_line.filename == first_loc.filename and tloc.file_line.line in good_lines,
            next_locs))

        if len(next_locs) == 0:
            return locs0, locs1
        next_loc = random.choice(next_locs)
        locs0.append(next_loc)
        if len(pattern.code0) == max_part_len:
            return locs0, locs1
        else:
            return locs1, locs0
