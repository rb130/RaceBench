from __future__ import annotations
from typing import Any, ByteString, Callable, Dict, List, Optional, Tuple
import random
import numpy

from piece import *
from error import *
from general import *
from variable import *


class VarData:
    def __init__(self, var: Variable, editable: bool, use_count: int = 0):
        self.var = var
        self.editable = editable
        self.use_count = use_count

    def increase_use(self):
        self.use_count += 1

    def is_normal(self):
        return self.var.type == VarType.Normal

    @property
    def name(self):
        return self.var.name


class CodeGenerator:
    ProbRandImm = 0.5
    sleep_time: int = 100
    prob_new_var: float = 0.5
    operations = ["+", "-", "^"]

    def __init__(self, bug_id: int, input_bytes: ByteString):
        self.bug_id = bug_id
        self.input_bytes = input_bytes
        self.all_vars: Dict[str, VarData] = dict()
        self.count = 0

    def list_all_vars(self) -> List[Variable]:
        return list(v.var for v in self.all_vars.values())

    def new_var(self, var_type: VarType = VarType.Normal, editable: bool = False) -> str:
        v = Variable(var_type, self.bug_id, str(self.count))
        self.count += 1
        self.all_vars[v.name] = VarData(v, editable)
        return v.name

    def old_var(self, need_edit: bool) -> str:
        def var_filter(v: VarData) -> bool:
            if not v.is_normal():
                return False
            if need_edit and not v.editable:
                return False
            return True
        usable_vars = list(filter(var_filter, self.all_vars.values()))
        if len(usable_vars) == 0:
            var = self.new_var(editable=need_edit)
            var = self.all_vars[var]
        else:
            var = min(usable_vars, key=lambda v: v.use_count)
        var.increase_use()
        return var.name

    def count_editable_vars(self) -> int:
        count = 0
        for v in self.all_vars.values():
            if v.editable:
                count += 1
        return count

    def set_editable(self, var_name: str, editable: bool):
        v = self.all_vars[var_name]
        v.editable = editable

    def new_assign(self, var_name: str, use_vars: Optional[List[str]] = None) -> CodeReserve:
        if use_vars is None:
            use_vars = []

        assign_methods = [
            (0, self._new_assign_imm),
            (0, self._new_assign_input),
            (1, self._new_assign_var),
            (2, self._new_assign_control),
            (numpy.inf, self._new_assign_expr),
        ]
        methods: List[Callable[[List[str]], Any]] = []
        for n_use, method in assign_methods:
            if n_use < len(use_vars):
                continue
            methods.append(method)
        method = random.choice(methods)
        val = method(use_vars)
        op = random.choice(self.operations)
        return Reserved(AssignExpr, var_name, ReservedExpr(op, [var_name, val]))

    def new_assign_many(self, var_name: str, min_len: int, use_vars: Optional[List[str]] = None) -> List[CodeReserve]:
        ans: List[CodeReserve] = []

        if use_vars is None:
            use_vars = set()
        else:
            use_vars = set(use_vars)
        for _ in range(min_len):
            if random.random() < self.ProbRandImm:
                v = self.new_var(editable=False)
                ans.append(Reserved(AssignImm, v, self.random_value()))
            else:
                v = self.old_var(need_edit=False)
            use_vars.add(v)
        use_vars = list(use_vars)

        while len(use_vars) > 1:
            num = random.randint(0, min(len(use_vars), 2))
            if num == 0 and len(use_vars) >= 1 and len(ans) > min_len:
                num = 1
            cur_use_vars = use_vars[:num]
            v = self.new_var(editable=True)
            a = self.new_assign(v, cur_use_vars)
            ans.append(a)
            use_vars = use_vars[num:] + [v]

        v = use_vars[0]
        op = random.choice(self.operations)
        a = Reserved(AssignExpr, var_name, ReservedExpr(op, [var_name, v]))
        ans.append(a)
        return ans

    @staticmethod
    def random_value() -> TVal:
        return TVal(random.getrandbits(32))

    def _new_assign_imm(self, use_vars: List[str]) -> TVal:
        imm = self.random_value()
        assert len(use_vars) == 0
        return imm

    def _new_assign_var(self, use_vars: List[str]) -> str:
        assert len(use_vars) <= 1
        if len(use_vars) == 1:
            rvar = use_vars[0]
        else:
            rvar = self.old_var(need_edit=False)
        return rvar

    def _new_assign_expr(self, use_vars: List[str]) -> ReservedExpr:
        vals = use_vars[:]
        for _ in range(max(1, len(use_vars))):
            if random.random() < self.ProbRandImm:
                v = self.random_value()
            else:
                v = self.old_var(need_edit=False)
            vals.append(v)
        random.shuffle(vals)
        expr = self.random_value()
        for v in vals:
            op = random.choice(self.operations)
            expr = ReservedExpr(op, [expr, v])
        return expr

    def _new_assign_input(self, use_vars: List[str]) -> InputValue:
        assert len(use_vars) == 0
        index = random.randrange(0, len(self.input_bytes))
        return InputValue(index, self.random_value())

    def _new_assign_control(self, use_vars: List[str]) -> ReservedExpr:
        assert len(use_vars) <= 2
        if len(use_vars) >= 1:
            rvar = use_vars.pop()
        else:
            rvar = self.old_var(need_edit=False)
        if len(use_vars) >= 1:
            cvar = use_vars.pop()
        else:
            cvar = self.old_var(need_edit=False)
        cond = ReservedExpr("==", [cvar, ExpectedVar(cvar)])
        fall = self.random_value()
        return ReservedExpr("?:", [cond, rvar, fall])
