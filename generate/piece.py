from __future__ import annotations
from enum import Enum
from typing import List, Set, Union
import numpy


BUG_MACRO = "RACEBENCH_BUG_{bug_id}"

TVal = numpy.uint32
DefaultValue = TVal(0)


class CodePiece:
    def __init__(self, shift: int = 0):
        self.shift = shift

    def __str__(self) -> str:
        raise NotImplementedError

    def used_vars(self) -> Set[str]:
        raise NotImplementedError

    def edit_vars(self) -> Set[str]:
        raise NotImplementedError


def codes_to_indent_str(codes: List[CodePiece], indent: str = "    ") -> List[str]:
    ans = []
    level = 0
    for c in codes:
        new_level = level + c.shift
        cur_level = new_level if isinstance(c, BlockEnd) else level
        s = indent * cur_level + str(c)
        level = new_level
        ans.append(s)
    return ans


class Assign(CodePiece):
    def __init__(self, var: str):
        self.var = var
        super().__init__()

    def __str__(self) -> str:
        raise NotImplementedError

    def edit_vars(self) -> Set[str]:
        return {self.var}


class IfCond(CodePiece):
    def __init__(self, cond: Expression):
        self.cond = cond
        super().__init__(shift=1)

    def __str__(self) -> str:
        return "if (%s) {" % str(self.cond)

    def used_vars(self) -> Set[str]:
        return self.cond.used_vars()

    def edit_vars(self) -> Set[str]:
        return set()


class BlockEnd(CodePiece):
    def __init__(self):
        super().__init__(shift=-1)

    def __str__(self) -> str:
        return "}"

    def used_vars(self) -> Set[str]:
        return set()

    def edit_vars(self) -> Set[str]:
        return set()


class Crash(CodePiece):
    def __init__(self, bug_id: int):
        super().__init__()
        self.bug_id = bug_id

    def __str__(self) -> str:
        return "racebench_trigger(%d);" % self.bug_id

    def used_vars(self) -> Set[str]:
        return set()

    def edit_vars(self) -> Set[str]:
        return set()


class AssignImm(Assign):
    def __init__(self, var: str, imm: TVal):
        super().__init__(var)
        self.imm = imm

    def __str__(self) -> str:
        mask = (1 << 32) - 1
        return "%s = %s;" % (self.var, hex(self.imm & mask))

    def used_vars(self) -> Set[str]:
        return {self.var}


class AssignVar(Assign):
    def __init__(self, var: str, rvar: str):
        super().__init__(var)
        self.rvar = rvar

    def __str__(self) -> str:
        return "%s = %s;" % (self.var, self.rvar)

    def used_vars(self) -> Set[str]:
        return {self.var, self.rvar}


class AssignInput(Assign):
    def __init__(self, var: str, index: int):
        super().__init__(var)
        self.index = index

    def __str__(self) -> str:
        return "if ({index} < rb_input_size) {{ {var} = rb_input[{index}]; }}".format(var=self.var, index=self.index)

    def used_vars(self) -> Set[str]:
        return {self.var}


class InputValue(CodePiece):
    def __init__(self, index: int, fall_back: TVal):
        super().__init__()
        self.index = index
        self.fall_back = fall_back

    def __str__(self) -> str:
        return "{index} < rb_input_size ? (uint32_t)rb_input[{index}] : {fall_back}".format(index=self.index, fall_back=hex(self.fall_back))

    def used_vars(self) -> Set[str]:
        return set()

    def edit_vars(self) -> Set[str]:
        return set()


class Expression(CodePiece):
    def __init__(self, op: str, args: List[Union[str, TVal, CodePiece]]):
        super().__init__()
        self.op = op
        self.args = args

    def __str__(self) -> str:
        def to_str(x):
            if isinstance(x, TVal):
                return hex(x)
            if isinstance(x, str):
                return x
            return str(x)

        if len(self.args) == 1:
            return "%s(%s)" % (self.op, to_str(self.args[0]))
        if len(self.args) == 2:
            return "(%s) %s (%s)" % (to_str(self.args[0]), self.op, to_str(self.args[1]))
        if len(self.args) == 3:
            if self.op == "?:":
                return "(%s) ? (%s) : (%s)" % tuple(map(to_str, self.args))
        raise ValueError(self.op, self.args)

    def used_vars(self) -> Set[str]:
        s = set()
        for arg in self.args:
            if isinstance(arg, str):
                s.add(arg)
            elif isinstance(arg, Expression):
                s.update(arg.used_vars())
        return s

    def edit_vars(self) -> Set[str]:
        return set()


class AssignExpr(Assign):
    def __init__(self, var: str, expr: Expression):
        super().__init__(var)
        self.expr = expr

    def __str__(self) -> str:
        return "%s = %s;" % (self.var, str(self.expr))

    def used_vars(self) -> Set[str]:
        return {self.var} | self.expr.used_vars()


class AssignControl(Assign):
    def __init__(self, var: str, cond: Expression, rvar: str):
        super().__init__(var)
        self.cond = cond
        self.rvar = rvar

    def __str__(self) -> str:
        return "if (%s) { %s = %s; }" % (str(self.cond), self.var, self.rvar)

    def used_vars(self) -> Set[str]:
        return {self.var, self.rvar} | self.cond.used_vars()


class Assume(CodePiece):
    class ImplType(Enum):
        Crash = 1
        Chain = 2
        Nest = 3

    def __init__(self, cond: Expression):
        super().__init__()
        self.cond = cond

    def __str__(self) -> str:
        raise NotImplementedError

    def used_vars(self) -> Set[str]:
        return self.cond.used_vars()


class LockOp(CodePiece):
    def __init__(self, name: str, require: bool):
        super().__init__()
        self.name = name
        self.require = require

    def __str__(self) -> str:
        if self.require:
            return "pthread_mutex_lock(&(%s));" % self.name
        else:
            return "pthread_mutex_unlock(&(%s));" % self.name

    def used_vars(self) -> Set[str]:
        return {self.name}

    def edit_vars(self) -> Set[str]:
        return {self.name}


class Wait(CodePiece):
    def __init__(self, cv: str, lock: str):
        super().__init__()
        self.cv = cv
        self.lock = lock

    def __str__(self) -> str:
        return "pthread_cond_wait(&(%s), &(%s));" % (self.cv, self.lock)

    def used_vars(self) -> Set[str]:
        return {self.cv, self.lock}

    def edit_vars(self) -> Set[str]:
        return {self.cv, self.lock}


class Notify(CodePiece):
    def __init__(self, cv: str):
        super().__init__()
        self.cv = cv

    def __str__(self) -> str:
        return "pthread_cond_signal(&(%s));" % self.cv

    def used_vars(self) -> Set[str]:
        return {self.cv}

    def edit_vars(self) -> Set[str]:
        return {self.cv}


class Sleep(CodePiece):
    def __init__(self, time_us: int):
        super().__init__()
        self.time_us = time_us

    def __str__(self) -> str:
        return "usleep(%d);" % self.time_us

    def used_vars(self) -> Set[str]:
        return set()

    def edit_vars(self) -> Set[str]:
        return set()


class IfdefBug(CodePiece):
    def __init__(self, bug_id: int):
        super().__init__()
        self.bug_id = bug_id

    def __str__(self) -> str:
        return "#ifdef " + BUG_MACRO.format(bug_id=self.bug_id)

    def used_vars(self) -> Set[str]:
        return set()

    def edit_vars(self) -> Set[str]:
        return set()


class IfdefEnd(CodePiece):
    def __init__(self):
        super().__init__()

    def __str__(self) -> str:
        return "#endif"

    def used_vars(self) -> Set[str]:
        return set()

    def edit_vars(self) -> Set[str]:
        return set()
