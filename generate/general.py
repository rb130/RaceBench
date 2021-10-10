from __future__ import annotations
from enum import Enum
from typing import Callable, Dict, List, Optional, Set, Type
from piece import CodePiece, DefaultValue, Expression, TVal
from utils import *


class FileLine:
    def __init__(self, filename: str, line: int):
        self.filename = filename
        self.line = line

    def extend_path(self, cwd: str) -> FileLine:
        return FileLine(extend_path(self.filename, cwd), self.line)

    def __hash__(self) -> int:
        return hash(self.filename) ^ self.line

    def __eq__(self, other: FileLine) -> bool:
        return self.filename == other.filename and self.line == other.line


class LineLoc(Enum):
    Before = "="
    Middle = ">"
    After = "-"


class LocBeforeLine:
    def __init__(self, site: CodeSite, code_ptr: Optional[int]):
        self.site = site
        self.code_ptr = code_ptr
        self.new_line: Optional[int] = None

    @property
    def filename(self):
        return self.site.filename

    @property
    def line(self):
        return self.site.line

    @property
    def file_line(self):
        return self.site.file_line

    def set_new_line(self, new_line: Optional[int]):
        self.new_line = new_line


class CodeSite:
    result_line_getter: Callable[[Optional[int]], int]

    def __init__(self, fline: FileLine):
        self.file_line = fline
        self.code_list: List[CodeLazy] = []
        self.result_line_getter = lambda _: 0

    @property
    def filename(self):
        return self.file_line.filename

    @property
    def line(self):
        return self.file_line.line

    def append_code(self, code: CodeLazy):
        self.code_list.append(code)

    def exloc_current(self) -> LocBeforeLine:
        return LocBeforeLine(self, len(self.code_list))

    def exloc_start(self) -> LocBeforeLine:
        return LocBeforeLine(self, 0)

    def exloc_middle(self) -> LocBeforeLine:
        return LocBeforeLine(self, None)

    def get_code(self) -> List[CodeLazy]:
        return self.code_list

    def set_result_line_getter(self, getter: Callable[[Optional[int]], int]):
        self.result_line_getter = getter

    def get_result_line(self, index: Optional[int]):
        return self.result_line_getter(index)


class ThreadPointer:
    def __init__(self, tid: int, loc: Optional[LocBeforeLine], line_loc: LineLoc = LineLoc.Before):
        self.tid = tid
        self.location = loc
        self.line_loc = line_loc

    @property
    def filename(self):
        return self.location.filename

    @property
    def line(self):
        return self.location.line

    @property
    def file_line(self):
        return self.location.file_line

    def str_new_line(self) -> str:
        if self.location is None:
            file_line = None
        else:
            lineno = self.location.new_line
            file_line = "%s:%d" % (self.filename, lineno)
        line_loc = self.line_loc.value
        return "%d %s %s" % (self.tid, line_loc, file_line)


class CodeLazy:
    def __init__(self, rcode: CodeReserve):
        self.reserved = rcode
        self.code: Optional[CodePiece] = None
        self.after_order: int = 0

    def set_after_order(self, after_order: int):
        self.after_order = after_order

    def generate(self, state: State):
        self.code = self.reserved.generate(state)

    @property
    def base(self) -> Type[CodePiece]:
        return self.reserved.base


class State:
    def __init__(self):
        self.values: Dict[str, TVal] = dict()
        self.skip_level: int = 0

    def get_var(self, name: str):
        return self.values.get(name, DefaultValue)

    def set_var(self, name: str, value: TVal):
        self.values[name] = value

    def inc_skip_level(self):
        self.skip_level += 1

    def dec_skip_level(self):
        if self.skip_level >= 1:
            self.skip_level -= 1

    def should_skip(self):
        return self.skip_level >= 1


class FutureVal:
    def __call__(self, state: State) -> TVal:
        raise NotImplementedError


class ExpectedVar(FutureVal):
    def __init__(self, name: str):
        self.name = name

    def __call__(self, state: State) -> TVal:
        return state.get_var(self.name)


class CodeReserve:
    def __init__(self, base: Type[CodePiece]):
        self.base = base

    def generate(self, state: State) -> CodePiece:
        raise NotImplementedError

    def used_vars(self) -> Set[str]:
        return self.generate(State()).used_vars()

    def edit_vars(self) -> Set[str]:
        return self.generate(State()).edit_vars()

    @staticmethod
    def convert(x, state: State):
        if isinstance(x, CodeReserve):
            return x.generate(state)
        if isinstance(x, FutureVal):
            return x(state)
        return x


class Reserved(CodeReserve):
    def __init__(self, base: Type[CodePiece], *args, **kwargs):
        super().__init__(base)
        self.args = args
        self.kwargs = kwargs

    def generate(self, state: State) -> CodePiece:
        args = [self.convert(a, state) for a in self.args]
        kwargs = {k: self.convert(v, state) for k, v in self.kwargs.items()}
        return self.base(*args, **kwargs)


class ReservedExpr(CodeReserve):
    def __init__(self, op: str, args: List):
        super().__init__(Expression)
        self.op = op
        self.args = args

    def generate(self, state: State) -> CodePiece:
        args = [self.convert(a, state) for a in self.args]
        return Expression(self.op, args)


class Interleave:
    def __init__(self):
        self.data: List[ThreadPointer] = list()

    def __len__(self):
        return len(self.data)

    def __getitem__(self, idx):
        return self.data[idx]

    def append(self, item: ThreadPointer) -> int:
        index = len(self.data)
        self.data.append(item)
        return index

    def num_threads(self):
        return 1 + max(tp.tid for tp in self.data)


class InjectLocation:
    def __init__(self, file_loc: FileLine, line_loc: LineLoc):
        self.file_loc = file_loc
        self.line_loc = line_loc

    @property
    def filename(self):
        return self.file_loc.filename

    @property
    def line(self):
        return self.file_loc.line

    def is_before(self):
        return self.line_loc == LineLoc.Before

    def __str__(self):
        return "{file}:{line}{sign}".format(
            file=self.filename, line=self.line,
            sign='-' if self.is_before() else '+')


class InsertionPoint:
    def __init__(self, loc: InjectLocation, codes: List[str]):
        self.loc = loc
        self.codes = codes
        self.result_lines: List[int] = [-1] * (self.code_len + 1)

    def get_code(self, index: int) -> str:
        return self.codes[index]

    def set_result_line(self, index: int, line: int):
        self.result_lines[index] = line

    def get_result_line(self, index: int) -> int:
        return self.result_lines[index]

    @property
    def code_len(self):
        return len(self.codes)


class AccInsertionPoint:
    def __init__(self):
        self.points: Dict[FileLine, List[InsertionPoint]] = dict()

    def add_insertion_point(self, ins_point: InsertionPoint) -> Callable[[Optional[int]], int]:
        file_line = ins_point.loc.file_loc
        if file_line not in self.points:
            point_list = []
            self.points[file_line] = point_list
        else:
            point_list = self.points[file_line]
        point_list.append(ins_point)
        return self.result_line_getter(point_list, len(point_list) - 1)

    def result_line_getter(self, point_list: List[InsertionPoint], pt_index: int) -> Callable[[Optional[int]], int]:
        ins_point = point_list[pt_index]

        def get_result_line(index: Optional[int]) -> int:
            if index is None:
                last_ins_point = point_list[-1]
                return last_ins_point.get_result_line(last_ins_point.code_len)
            return ins_point.get_result_line(index)
        return get_result_line
