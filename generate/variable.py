from __future__ import annotations
from enum import Enum


STATE_NAME = "rb_state{bug_id}"


class VarType(Enum):
    Normal = 0
    Lock = 1
    CondVar = 2

    def name_prefix(self):
        prefix = ["var", "lock", "cv"]
        return prefix[self.value]

    def c_type(self):
        c_type = ["uint32_t", "pthread_mutex_t", "pthread_cond_t"]
        return c_type[self.value]

    def c_attribute(self):
        c_attr = ["volatile", "", ""]
        return c_attr[self.value]

    def c_initializer(self):
        c_init = ["0", "PTHREAD_MUTEX_INITIALIZER", "PTHREAD_COND_INITIALIZER"]
        return c_init[self.value]


def state_name(bug_id: int):
    return STATE_NAME.format(bug_id=bug_id)


class Variable:
    def __init__(self, var_type: VarType, bug_id: int, suffix: str):
        self.type = var_type
        self.prefix = state_name(bug_id) + "."
        self.name = self.prefix + var_type.name_prefix() + "_" + suffix

    @property
    def base_name(self) -> str:
        return self.name[len(self.prefix):]
