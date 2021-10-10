import functools
from typing import ByteString, List, Optional
import os
import shutil
import subprocess
import tempfile
import json
from error import *
import signal

from utils import *
from general import *
from tracer import Trace
from build import Builder
from mutate import Mutator
from inject import InjectChecker, Injector
from bug import Bug
from bug_extract import BugExtractor
from dom import DomAnalyzer
from rbcode import RaceBenchCode
from piece import codes_to_indent_str
from convert import Converter
from reproduce import Reproducer


BUG_TRIGGER_MESSAGE = b"RaceBench crashes deliberately"

GDB_StepTimeout = 1


def _bug_test_timeout(bug: Bug) -> float:
    return GDB_StepTimeout * max(60, len(bug.order) / 3.0)


class TargetCode:

    def __init__(self, origin: str, code_dir: str):
        self.code_dir = code_dir
        self.install_dir = os.path.join(self.code_dir, "racebench")
        shutil.copytree(origin, self.code_dir, dirs_exist_ok=is_empty_dir(self.code_dir))
        self.builder = Builder(self.code_dir)
        self.rbcode = RaceBenchCode(self.code_dir)
        self._parse_code_config()
        self.injector = Injector()

    def _parse_commands(self):
        commands = read_file(os.path.join(self.code_dir, "command.txt"))
        self.exec_command: List[str] = []
        for line in commands.split("\n"):
            if len(line) > 0:
                self.exec_command.append(line)

    def _parse_code_config(self):
        self.exec_timeout = float(read_file(os.path.join(self.code_dir, "timeout")))
        self._parse_commands()

    def command_line(self, input_file: str) -> List[str]:
        return [arg.format(install_dir=self.install_dir, input_file=input_file)
                for arg in self.exec_command]

    def check_compile(self) -> bool:
        try:
            self.builder.rebuild_and_install()
            return True
        except subprocess.CalledProcessError:
            return False

    def build_debug(self):
        self.builder.rebuild_and_install(debug_info=True, dump_cmd=True)

    def _add_racebench_code(self, bugs: List[Bug]):
        arg_input = self.exec_command.index("{input_file}")
        max_bug_id = max(bug.bug_id for bug in bugs)
        defs = {"bug_num": max_bug_id + 1, "arg_input": arg_input}
        self.rbcode.copy_preset_files(defs)
        for bug in bugs:
            self.rbcode.add_state(bug)
        self.rbcode.dump_state_defs()

    def inject_bugs(self, bugs: List[Bug]):
        self._add_racebench_code(bugs)
        file_names = set().union(*[b.get_all_files() for b in bugs])
        for name in file_names:
            self.rbcode.prepend_state_defs(self.injector, name)
        ins_acc = AccInsertionPoint()
        for bug in bugs:
            self._injector_add_bug(ins_acc, bug)
        self.injector.commit()
        for bug in bugs:
            self._bug_reorder(bug)

    def _injector_add_bug(self, ins_acc: AccInsertionPoint, bug: Bug):
        for loc, site in bug.iter_code_sites():
            filename = os.path.join(self.code_dir, loc.filename)
            loc = InjectLocation(FileLine(filename, loc.line), LineLoc.Before)
            codes = [code.code for code in site.get_code()]
            assert None not in codes
            codes = codes_to_indent_str(codes)
            ins_point = self.injector.add(loc, codes)
            result_line_getter = ins_acc.add_insertion_point(ins_point)
            site.set_result_line_getter(result_line_getter)

    def _bug_reorder(self, bug: Bug):
        for i in range(len(bug.order)):
            loc = bug.order[i].location
            if loc is None:
                continue
            new_line = loc.site.get_result_line(loc.code_ptr)
            loc.set_new_line(new_line)

    def cleanup(self):
        self.builder.clean()
        self.builder.clean_compile_db()

    def check_too_easy(self, input_file: str) -> bool:
        cmd = self.command_line(input_file)
        environ = os.environ.copy()
        environ["RACEBENCH_STAT"] = "/dev/null"
        try:
            proc = subprocess.Popen(cmd, env=environ,
                                    stdin=subprocess.DEVNULL,
                                    stdout=subprocess.DEVNULL,
                                    stderr=subprocess.PIPE)
            retcode = proc.wait(self.exec_timeout)
            if -retcode == signal.SIGABRT:
                stderr = proc.stderr.read()
                if stderr.find(BUG_TRIGGER_MESSAGE) != -1:
                    return True
            return False
        except subprocess.TimeoutExpired:
            proc.kill()
            print("bug check timeout")
            return True

    def check_reproduce(self, bug: Bug, answer_file: str) -> bool:
        print("check reproduce %d" % bug.bug_id)
        repro = Reproducer(
            cmd=self.command_line(bug.input_file),
            cwd=self.code_dir,
            step_timeout=GDB_StepTimeout,
            timeout=_bug_test_timeout(bug),
        )
        return repro.run(answer_file)

    def convert_answer(self, bug: Bug, order_file: str, answer_file: str):
        converter = Converter(
            cmd=self.command_line(bug.input_file),
            srcdir=".",
            step_timeout=GDB_StepTimeout,
            cwd=self.code_dir,
            timeout=_bug_test_timeout(bug),
        )
        converter.run(order_file, answer_file)


class TargetProgram:
    GDB_TimeoutMultiplier = 20
    EasyCheckNum = 100

    def __init__(self, origin: str, target_root: str, mutate_num: int):
        self.root = os.path.abspath(target_root)
        self.mutate_num = mutate_num

        self.code_dir = os.path.join(self.root, "code")
        self.input_dir = os.path.join(self.root, "input")
        self.log_dir = os.path.join(self.root, "log")
        self.trace_dir = os.path.join(self.root, "trace")
        self.install_dir = os.path.join(self.root, "install")

        os.mkdir(self.root)
        os.mkdir(self.input_dir)
        os.mkdir(self.log_dir)
        os.mkdir(self.trace_dir)

        self.target_code = TargetCode(origin, self.code_dir)
        self._copy_input_seed()
        self._parse_blacklist(os.path.join(self.code_dir, "blacklist.txt"))
        self.mutator = Mutator(self.has_new_thread)
        self.inject_checker = InjectChecker(self.blacklist)
        self.dom = DomAnalyzer(self.code_dir)
        self.bugs: List[Bug] = []

    def _copy_input_seed(self):
        shutil.copy(os.path.join(self.code_dir, "input-seed"), self.input_dir)
        self.input_seed = read_file(os.path.join(self.input_dir, "input-seed"), raw=True)

    def command_line(self, input_file: str) -> List[str]:
        return self.target_code.command_line(input_file)

    @property
    def exec_timeout(self) -> float:
        return self.target_code.exec_timeout

    def build_debug(self):
        print("build debug")
        self.target_code.build_debug()

    def cleanup(self):
        self.target_code.cleanup()

    def _parse_blacklist(self, filename: str):
        self.blacklist: List[str] = list()
        if not os.path.exists(filename):
            return
        with open(filename, "r", encoding='latin-1') as f:
            for line in f.readlines():
                name = line.strip()
                if len(name) > 0:
                    self.blacklist.append(name)

    def mutate_input(self) -> bytearray:
        print("mutate input")
        new_input = bytearray(self.input_seed)
        self.mutator.mutate(new_input, self.mutate_num)
        return new_input

    def has_new_thread(self, input_bytes: ByteString) -> bool:
        with tempfile.NamedTemporaryFile(
            mode="wb", prefix="strace-", dir=self.log_dir, delete=True,
        ) as temp_file:
            temp_file.write(input_bytes)
            temp_file.flush()
            args = self.command_line(temp_file.name)
            cmd = ["strace", "-e", "clone", "-f"] + args
            cmd = ["timeout", "-s", "KILL", str(self.exec_timeout)] + cmd
            environ = os.environ.copy()
            environ["RACEBENCH_STAT"] = "/dev/null"
            proc = subprocess.run(cmd, check=False, env=environ,
                                  stdin=subprocess.DEVNULL,
                                  stdout=subprocess.DEVNULL,
                                  stderr=subprocess.PIPE)
            return proc.stderr.find(b"clone(") != -1

    def _get_trace(self, input_file: str, uuid: str) -> Trace:
        print("gdb trace")
        with tempfile.NamedTemporaryFile(prefix=uuid, suffix=".log", dir=self.log_dir, delete=False) as trace_file:
            trace_file_name = trace_file.name
        with tempfile.NamedTemporaryFile(prefix=uuid, suffix=".black", dir=self.log_dir, delete=False) as black_file:
            black_file_name = black_file.name
        config = {
            "cmd": self.command_line(input_file),
            "srcdir": ".",
            "cwd": self.code_dir,
            "log": trace_file_name,
            "blacklist": black_file_name,
            "steptime": GDB_StepTimeout,
            "timeout": self.exec_timeout * self.GDB_TimeoutMultiplier,
        }
        with tempfile.NamedTemporaryFile(
            mode="w", prefix=uuid, suffix=".trace.json", dir=self.log_dir, delete=False,
        ) as config_file:
            json.dump(config, config_file)
            config_file.flush()
            trace = Trace.run(config_file.name)
        return trace

    def bug_location_checker(self, fileline: Optional[FileLine]) -> bool:
        if fileline is None:
            return False
        x = fileline.extend_path(self.code_dir)
        return self.inject_checker.can_insert_before(x.filename, x.line)

    def temp_input_file(self, input_bytes: bytes, uuid: str):
        with tempfile.NamedTemporaryFile(
            mode="wb", prefix=uuid, suffix=".in", dir=self.log_dir, delete=False,
        ) as in_file:
            in_file.write(input_bytes)
            return in_file.name

    def new_bug(self, path_len: int):
        print("extract bug")
        bug_id = len(self.bugs)
        uuid = str(bug_id) + "."
        input_bytes = self.mutate_input()
        input_file = self.temp_input_file(input_bytes, uuid)
        trace = self._get_trace(input_file, uuid)
        bug_checker = lambda bug: self._check_bug_trigger(bug, uuid)
        bug_extractor = BugExtractor(self.bug_location_checker, self.dom, bug_checker)
        bug = bug_extractor.extract(bug_id, trace, input_file, path_len)
        self.bugs.append(bug)

    def _check_bug_trigger(self, bug: Bug, uuid: str):
        tmpdir = tempfile.TemporaryDirectory(prefix=uuid, suffix=".code", dir=self.log_dir)
        temp_target = TargetCode(self.code_dir, tmpdir.name)
        temp_target.inject_bugs([bug])
        temp_target.build_debug()
        for _ in range(self.EasyCheckNum):
            if temp_target.check_too_easy(bug.input_file):
                raise BugTooEasy
        with tempfile.NamedTemporaryFile(suffix=".order", dir=tmpdir.name, delete=False) as f:
            order_file = f.name
        with tempfile.NamedTemporaryFile(suffix=".answer", dir=tmpdir.name, delete=False) as f:
            answer_file = f.name
        bug.dump_order(order_file)
        temp_target.convert_answer(bug, order_file, answer_file)
        if not temp_target.check_reproduce(bug, answer_file):
            raise CantReproduce

    def inject_bugs(self):
        self.target_code.inject_bugs(self.bugs)

    def dump_bug_info_files(self):
        self.build_debug()
        for bug in self.bugs:
            self._dump_bug_log_file(bug)
            self._dump_input_file(bug)
            self._dump_order_file(bug)
        print("convert answer")
        for bug in self.bugs:
            self._dump_answer_file(bug)

    def bug_log_file(self, bug_id: int):
        return os.path.join(self.trace_dir, "bug-%d.json" % bug_id)

    def bug_input_file(self, bug_id: int):
        return os.path.join(self.input_dir, "input-%d" % bug_id)

    def bug_order_file(self, bug_id: int):
        return os.path.join(self.trace_dir, "order-%d.txt" % bug_id)

    def bug_answer_file(self, bug_id: int):
        return os.path.join(self.trace_dir, "answer-%d.txt" % bug_id)

    def _dump_bug_log_file(self, bug: Bug):
        file_name = self.bug_log_file(bug.bug_id)
        write_file(file_name, json.dumps(bug.log.get_items(), indent=4))

    def _dump_input_file(self, bug: Bug):
        file_name = self.bug_input_file(bug.bug_id)
        shutil.copyfile(bug.input_file, file_name)

    def _dump_order_file(self, bug: Bug):
        file_name = self.bug_order_file(bug.bug_id)
        bug.dump_order(file_name)

    def _dump_answer_file(self, bug: Bug):
        order_file = self.bug_order_file(bug.bug_id)
        answer_file = self.bug_answer_file(bug.bug_id)
        return self.target_code.convert_answer(bug, order_file, answer_file)

    def dump_install(self):
        old_install = os.path.join(self.code_dir, "racebench")
        shutil.copytree(old_install, self.install_dir)

    def check_reproduce_all(self):
        for bug in self.bugs:
            answer_file = self.bug_answer_file(bug.bug_id)
            if not self.target_code.check_reproduce(bug, answer_file):
                raise CantReproduce(bug.bug_id)
