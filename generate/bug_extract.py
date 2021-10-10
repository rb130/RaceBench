from typing import Callable
import sys
import random

from bug import *
from codegen import CodeGenerator
from executor import CheckerExecutor, CodePieceExecutor, InterleaveExec
from pattern import BugPattern, PatternGenerator, StepMarker
from tracer import Trace
from piece import *
from general import *
from dom import DomAnalyzer
from error import *
from utils import read_file


# TODO: post-condition


class BugExtractState:

    def __init__(self, bug_id: int, trace: Trace, dom: DomAnalyzer,
                 loc_checker: Callable[[FileLine], bool],
                 input_file: str):
        self.trace = trace
        self.input_bytes = read_file(input_file, raw=True)
        self.code_gen = CodeGenerator(bug_id, self.input_bytes)
        self.bug = Bug(bug_id, input_file)
        self.walker = TraceWalker(trace, self.bug, loc_checker)
        self.pattern_gen = PatternGenerator(self.bug, self.code_gen, dom)

    def random_index(self, count: int, start: int, stop: int) -> int:
        total = stop - start
        for _ in range(total):
            index = random.randrange(start, stop)
            if len(self.walker.get_available_pos_at(index)) >= count:
                return index
        raise BugNoPosition

    @property
    def trace_len(self) -> int:
        return len(self.trace)

    @staticmethod
    def _prob_old(x: int, path_len: int) -> float:
        p = x * (2.0 / path_len)
        return min(p, 1.0)

    def select_edit_var(self, path_len):
        var_count = self.code_gen.count_editable_vars()
        if self._prob_old(var_count, path_len) > random.random():
            var = self.code_gen.old_var(need_edit=True)
        else:
            var = self.code_gen.new_var(editable=True)
        return var

    def add_bug(self, path_len: int):
        start_index = self.walker.current
        path_len = min(path_len, (self.trace_len - start_index) // 2)
        start_index2 = min(start_index + 1 + path_len, self.trace_len - 1)
        bug_index = self.random_index(2, start_index2, self.trace_len)
        pre_indexes = set()
        while len(pre_indexes) != path_len:
            index = self.random_index(1, start_index, bug_index)
            if index not in pre_indexes:
                pre_indexes.add(index)
        pre_indexes = sorted(pre_indexes)

        for i in range(path_len):
            self.walker.move_to(pre_indexes[i])
            var = self.select_edit_var(path_len)
            tpos = self.walker.get_one_pos()
            a = self.code_gen.new_assign(var)
            self.bug.append_code(tpos.file_line, a)
            site = self.bug.get_site(tpos.file_line)
            self.bug.append_order(ThreadPointer(tpos.tid, site.exloc_current()))
            self.bug.log.add_location(tpos.tid, tpos.file_line)

        self.walker.move_to(bug_index)
        cond_var = self.code_gen.old_var(need_edit=False)
        self.code_gen.set_editable(cond_var, False)
        cond = ReservedExpr("==", [cond_var, ExpectedVar(cond_var)])
        next_bug = self.add_pattern(cond)

        if next_bug:
            next_path_len = (path_len + 1) // 2
            self.add_bug(next_path_len)

    def add_pattern(self, pre_cond: ReservedExpr) -> bool:
        pattern, marks0, marks1 = self.pattern_gen.generate(self.walker)

        def bug_pattern_iter(pattern: BugPattern):
            cnt = [0, 0]
            for o in pattern.order:
                codes = pattern.get_codes(o, cnt[o])
                marker = (marks0, marks1)[o][cnt[o]]
                cnt[o] += 1
                yield codes, marker

        bug_locs = []
        for codes, marker in bug_pattern_iter(pattern):
            bug_locs.append((marker.tid, marker.file_line))
        self.bug.log.add_pattern(pattern.name, bug_locs)

        init_index = self.walker.current
        next_bug = False
        for codes, marker in bug_pattern_iter(pattern):
            if init_index + marker.step > self.walker.current:
                self.walker.move_to(init_index + marker.step)
            codes.insert(0, Reserved(IfCond, pre_cond))
            codes.append(Reserved(BlockEnd))
            for i, code in enumerate(codes):
                if code.base == Assume:
                    weights = self.assume_weights()
                    impl_type = random.choices(list(Assume.ImplType), weights)[0]
                    next_bug = self.expand_assume(code, marker, impl_type)
                else:
                    site = self.bug.get_site(marker.file_line)
                    code_lazy = self.bug.append_code(marker.file_line, code)
                    order_index = self.bug.append_order(ThreadPointer(marker.tid, site.exloc_current()))
                    # set when to generate pre_cond
                    if i == 0 and code.base == IfCond:
                        code_lazy.set_after_order(order_index)
            self.walker.mark_use(marker.tid)

        return next_bug

    def assume_weights(self):
        weights = {
            Assume.ImplType.Crash: 10,
            Assume.ImplType.Chain: 3,
            Assume.ImplType.Nest: 2,
        }
        num = len(self.walker.available_pos())
        if num < 2:
            weights[Assume.ImplType.Nest] = 0
        return [weights[impl_type] for impl_type in list(Assume.ImplType)]

    def expand_assume(self, assume: CodeReserve, marker: StepMarker, impl_type: Assume.ImplType) -> bool:
        assert isinstance(assume, Reserved) and assume.base == Assume
        cond = ReservedExpr("!", [assume.args[0]])
        next_bug = False
        self.bug.log.add_assume(impl_type.name)
        loc = marker.file_line
        site = self.bug.get_site(loc)
        if impl_type == Assume.ImplType.Crash:
            self.bug.append_code(loc, Reserved(IfCond, cond))
            self.bug.append_code(loc, Reserved(Crash, self.bug.bug_id))
            self.bug.append_code(loc, Reserved(BlockEnd))
        elif impl_type == Assume.ImplType.Chain:
            var = self.code_gen.new_var(editable=False)
            # TODO: use the new var
            a = Reserved(AssignExpr, var, cond)
            self.bug.append_code(loc, a)
            next_bug = True
        elif impl_type == Assume.ImplType.Nest:
            next_bug = self.add_pattern(cond)
        else:
            raise ValueError("assume impl_type error")
        self.bug.append_order(ThreadPointer(marker.tid, site.exloc_current()))
        return next_bug

    def implement(self):
        self.bug.append_ifdef_end()
        self.bug.add_vars(self.code_gen.list_all_vars())

        cp_runner = CodePieceExecutor(self.input_bytes)
        ex0 = BugExecWrap(self.bug, cp_runner)
        ex0.set_generate(True)
        ix0 = InterleaveExec(self.bug.order, ex0.execute, ex0.max_code_ptr)
        while ix0.next():
            if cp_runner.state.should_skip():
                raise CantFollowOrder

        checker = CheckerExecutor(self.input_bytes)
        ex_chk = BugExecWrap(self.bug, checker)
        ix_chk = InterleaveExec(self.bug.order, ex_chk.execute, ex_chk.max_code_ptr)
        while ix_chk.next():
            if checker.state.should_skip():
                raise CantFollowOrder
        if not checker.has_triggered():
            raise BugCantTrigger


class BugExtractor:
    FAIL_LIMIT = 20

    def __init__(self, loc_checker: Callable[[FileLine], bool], dom: DomAnalyzer,
                 bug_checker: Callable[[Bug], None]):
        self.loc_checker = loc_checker
        self.dom = dom
        self.bug_checker = bug_checker

    def extract(self, bug_id: int, trace: Trace, input_file: str, path_len: int) -> Bug:

        def loc_checker_with_trace(fileline: FileLine) -> bool:
            return self.loc_checker(fileline) and not trace.in_blacklist(fileline)

        fail_count = 0
        while True:
            sys.stdout.flush()
            state = BugExtractState(bug_id, trace, self.dom, loc_checker_with_trace, input_file)
            try:
                state.add_bug(path_len)
                state.implement()
                self.bug_checker(state.bug)
            except BugError as e:
                print("retry", type(e).__name__)
                fail_count += 1
                if fail_count >= self.FAIL_LIMIT:
                    raise e
                continue
            break
        return state.bug
