from typing import Any, Dict, List
import os
from bug import Bug
from general import FileLine

from utils import *
from inject import Injector
from variable import *
from general import *
from piece import BUG_MACRO


PRESET_FILES = [
    "racebench.c",
    "racebench.h",
]

STATE_DEFINE = "racebench_bugs.h"
STATE_INSTANCE = "racebench_bugs.c"

PREPEND_DEFS = ["#include \"%s\"" % STATE_DEFINE]

STRUCT_TYPE_DEFINE = """
struct {name} {{
    {fields}
}};
"""

STRUCT_FIELD_DEFINE = "{type} {name};"
STRUCT_FIELD_SEP = "\n    "
STRUCT_INSTANCE = "struct {struct_name} {var_name} = {init_values};"
STRUCT_EXTERN = "extern struct {struct_name} {var_name};"

CONSTRUCT_FUNC = """
__attribute__((constructor))
static void rb_init_state{bug_id}(void)
{{
    {fields}
}}
"""

CONSTRUCT_FIELD_SEP = "\n    "

DEFINE_BUG_MACRO = "#define " + BUG_MACRO


class StateStruct:
    def __init__(self, bug_id: int, state_name: str, state_vars: List[Variable]):
        self.bug_id = bug_id
        self.state_name = state_name
        self.state_vars = state_vars

    @property
    def struct_name(self) -> str:
        return "rb_state%d_t" % self.bug_id


class RaceBenchCode:
    def __init__(self, build_path: str):
        self.build_path = build_path
        curdir = os.path.dirname(__file__)
        self.rbcode_path = os.path.join(curdir, "rbcode")
        self.states: List[StateStruct] = list()

    def copy_preset_files(self, defs: Dict[str, Any]):
        for name in PRESET_FILES:
            new_name = os.path.join(self.build_path, name)
            name = os.path.join(self.rbcode_path, name)
            content = read_file(name)
            for k, v in defs.items():
                content = content.replace("{" + k + "}", str(v))
            write_file(new_name, content)

    def prepend_state_defs(self, injector: Injector, file_name: str):
        file_name = os.path.join(self.build_path, file_name)
        loc = InjectLocation(FileLine(file_name, 0), LineLoc.Before)
        injector.add(loc, PREPEND_DEFS)

    def add_state(self, bug: Bug):
        state = StateStruct(bug.bug_id, state_name(bug.bug_id), bug.all_vars)
        self.states.append(state)

    def dump_state_defs(self):
        macros = []
        for state in self.states:
            macro = DEFINE_BUG_MACRO.format(bug_id=state.bug_id)
            macros.append(macro)
        macros = "\n".join(macros)

        structs = []
        for state in self.states:
            fields = []
            for var in state.state_vars:
                c_type = var.type.c_type()
                c_attr = var.type.c_attribute()
                if c_attr != "":
                    c_type = c_attr + ' ' + c_type
                field = STRUCT_FIELD_DEFINE.format(type=c_type, name=var.base_name)
                fields.append(field)
            fields = STRUCT_FIELD_SEP.join(fields)
            struct = STRUCT_TYPE_DEFINE.format(name=state.struct_name, fields=fields)
            structs.append(struct)
        struct_defs = "".join(structs)

        externs = []
        instances = []
        for state in self.states:
            init_values = []
            for var in state.state_vars:
                init_values.append(var.type.c_initializer())
            init_values = "{" + ", ".join(init_values) + "}"
            extern = STRUCT_EXTERN.format(struct_name=state.struct_name, var_name=state.state_name) + "\n"
            instance = STRUCT_INSTANCE.format(struct_name=state.struct_name, var_name=state.state_name, init_values=init_values)
            externs.append(extern)
            instances.append(instance)
        externs = "\n".join(externs)
        instances = "\n".join(instances)

        def apply_template(name: str, code: str):
            template_name = os.path.join(self.rbcode_path, name)
            new_name = os.path.join(self.build_path, name)
            template = read_file(template_name)
            code = template.replace("{states}", code)
            write_file(new_name, code)

        apply_template(STATE_DEFINE, '\n\n'.join([macros, struct_defs, externs]))
        apply_template(STATE_INSTANCE, instances)
