from typing import Any, Callable, List, Optional
import numpy
from functools import reduce
import operator

from general import LocBeforeLine, FileLine, Interleave, State, ThreadPointer
from piece import *
from error import *


def eval_op(op: str, args: List[TVal]) -> TVal:
    if op == "+":
        return numpy.sum(args, dtype=TVal)
    elif op == "^":
        return reduce(operator.xor, args)
    elif op == "-":
        if len(args) == 1:
            return -args[0]
        elif len(args) == 2:
            return args[0] - args[1]
    elif op == "!":
        if len(args) == 1:
            return TVal(args[0] == 0)
    elif op == "==":
        if len(args) == 2:
            return TVal(args[0] == args[1])
    elif op == "!=":
        if len(args) == 2:
            return TVal(args[0] != args[1])
    elif op == "&&":
        if len(args) == 2:
            return TVal(bool(args[0]) and bool(args[1]))
    elif op == "?:":
        if len(args) == 3:
            return args[1] if args[0] else args[2]
    raise NotImplementedError


def eval_input(input_bytes: bytes, iv: InputValue) -> TVal:
    if iv.index < len(input_bytes):
        return TVal(input_bytes[iv.index])
    else:
        return iv.fall_back


class InterleaveExec:
    def __init__(self, interleave: Interleave,
                 execute: Callable[[int, FileLine, int], Any],
                 max_code_ptr: Callable[[FileLine], int]):
        self.interleave = interleave
        self.execute = execute
        self.max_code_ptr = max_code_ptr
        self.num_threads = self.interleave.num_threads()
        self.threads = [ThreadPointer(tid, None) for tid in range(self.num_threads)]
        self.cur_index = 0

    def next(self) -> bool:
        if self.cur_index >= len(self.interleave):
            return False
        tp = self.interleave[self.cur_index]
        self.cur_index += 1
        old_loc = self.threads[tp.tid]
        self._move_exec(old_loc.location, tp.location)
        self.threads[tp.tid] = tp
        return True

    def _move_exec(self, old_loc: Optional[LocBeforeLine], new_loc: Optional[LocBeforeLine]):
        if old_loc is None:
            return
        old_ptr = old_loc.code_ptr
        if old_ptr is None:
            old_ptr = self.max_code_ptr(old_loc.file_line)
        if new_loc is None:
            self.exec_range(old_loc.file_line, old_ptr, self.max_code_ptr(old_loc.file_line))
            return
        new_ptr = new_loc.code_ptr
        if new_ptr is None:
            new_ptr = self.max_code_ptr(new_loc.file_line)
        if new_ptr == 0:
            self.exec_range(old_loc.file_line, old_ptr, self.max_code_ptr(old_loc.file_line))
        else:
            if not (old_loc.file_line == new_loc.file_line):
                self.exec_range(old_loc.file_line, old_ptr, self.max_code_ptr(old_loc.file_line))
                self.exec_range(new_loc.file_line, 0, new_ptr)
            else:
                self.exec_range(new_loc.file_line, old_ptr, new_ptr)

    def exec_range(self, file_line: FileLine, old_code_ptr: int, new_code_ptr: int):
        assert old_code_ptr <= new_code_ptr
        for ptr in range(old_code_ptr, new_code_ptr):
            self.execute(self.cur_index - 1, file_line, ptr)


class CodePieceExecutor:
    def __init__(self, input_bytes: bytes):
        self.state = State()
        self.input_bytes = input_bytes

    def eval_input(self, iv: InputValue):
        return eval_input(self.input_bytes, iv)

    def eval_expr(self, expr: Expression) -> TVal:
        args = []
        for arg in expr.args:
            if isinstance(arg, str):
                arg = self.state.get_var(arg)
            elif isinstance(arg, Expression):
                arg = self.eval_expr(arg)
            elif isinstance(arg, InputValue):
                arg = self.eval_input(arg)
            if not isinstance(arg, TVal):
                raise ValueError("expr arg", arg)
            args.append(arg)
        ans = eval_op(expr.op, args)
        assert isinstance(ans, TVal)
        return ans

    def inc_skip_level(self):
        self.state.inc_skip_level()

    def dec_skip_level(self):
        self.state.dec_skip_level()

    def should_skip(self) -> bool:
        return self.state.should_skip()

    def run(self, code: CodePiece):
        if isinstance(code, BlockEnd):
            self.dec_skip_level()
        elif isinstance(code, IfCond):
            if self.should_skip() or not self.eval_expr(code.cond):
                self.inc_skip_level()
        if self.should_skip():
            return
        self.run_without_skip(code)

    def run_without_skip(self, code: CodePiece):
        do_nothing = [BlockEnd, IfCond, Crash, Sleep, IfdefBug, IfdefEnd]
        if isinstance(code, Assign):
            self.run_assign(code)
        elif isinstance(code, LockOp):
            self.run_lock_op(code)
        elif any(isinstance(code, t) for t in do_nothing):
            pass
        else:
            raise NotImplementedError("exec", code)

    def run_assign(self, code: Assign):
        var = code.var
        if isinstance(code, AssignImm):
            val = code.imm
        elif isinstance(code, AssignVar):
            val = self.state.get_var(code.rvar)
        elif isinstance(code, AssignInput):
            old_val = self.state.get_var(var)
            val = self.eval_input(InputValue(code.index, old_val))
        elif isinstance(code, AssignExpr):
            val = self.eval_expr(code.expr)
        elif isinstance(code, AssignControl):
            if self.eval_expr(code.cond):
                val = self.state.get_var(code.rvar)
            else:
                val = self.state.get_var(var)
        else:
            raise NotImplemented("exec assign", code)
        self.state.set_var(var, val)

    def run_lock_op(self, code: LockOp):
        if code.require:
            if self.state.get_var(code.name) != 0:
                raise LockError
            self.state.set_var(code.name, 1)
        else:
            if self.state.get_var(code.name) != 1:
                raise LockError
            self.state.set_var(code.name, 0)


class CheckerExecutor(CodePieceExecutor):
    def __init__(self, input_bytes: bytes):
        super().__init__(input_bytes)
        self.trigger = False

    def run_without_skip(self, code: CodePiece):
        do_nothing = [BlockEnd, IfCond, Sleep, IfdefBug, IfdefEnd]
        if isinstance(code, Assign):
            self.run_assign(code)
        elif isinstance(code, LockOp):
            self.run_lock_op(code)
        elif isinstance(code, Crash):
            self.trigger = True
        elif any(isinstance(code, t) for t in do_nothing):
            pass
        else:
            raise NotImplementedError("exec", code)

    def has_triggered(self):
        return self.trigger
