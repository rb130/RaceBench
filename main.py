#!/usr/bin/env python3

import os
import sys
import time
import json
import subprocess
import shutil
import pathlib
import logging
import random
import string
import tempfile
import signal

from inject import *
from bug import BugManager


def exec_rb_build(arg: str, env={}):
    global target_code_path
    cmd = ["make"]
    if arg != "":
        cmd.append(arg)
    new_env = os.environ.copy()
    for k, v in env.items():
        new_env[k] = v
    subprocess.run(cmd, cwd=target_code_path, env=new_env,
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def target_compile(debug_info=False):
    if debug_info:
        env = {"CFLAGS": "-g", "CXXFLAGS": "-g", "LDFLAGS": "-g"}
    else:
        env = {}
    exec_rb_build("", env)


def target_install():
    exec_rb_build("install")


def target_clean():
    exec_rb_build("clean")


def target_build(debug_info=False):
    target_compile(debug_info)
    target_install()


def read_file(filename, raw=False):
    mode = 'r' if not raw else 'rb'
    with open(filename, mode) as f:
        return f.read()


def write_file(filename, data, raw=False):
    mode = 'w' if not raw else 'wb'
    with open(filename, mode) as f:
        f.write(data)


def read_list_file(filename):
    ans = []
    with open(filename, "r") as f:
        for line in f.readlines():
            line = line.strip()
            if len(line) == 0:
                continue
            # line comments
            if line[0] == '#':
                continue
            ans.append(line)
    return ans


def change_work_dir():
    os.chdir(os.path.abspath(os.path.dirname(__file__)))


def prepare():
    signal.signal(signal.SIGTTIN, signal.SIG_IGN)
    signal.signal(signal.SIGTTOU, signal.SIG_IGN)

    prepare_script = os.path.join(os.getcwd(), "prepare.sh")
    subprocess.run(["sh", "-c", prepare_script],
                   check=True, stdout=subprocess.DEVNULL)


def read_config():
    global config_path, config
    with open(config_path, "r") as f:
        config = json.load(f)


def copy(src, dst, recursive=False):
    cmd = ["cp", "-f", src, dst]
    if recursive:
        cmd.append("-r")
    subprocess.run(cmd, check=True)


def setup_target():
    global target_path, config_path
    global config
    global target_code_path
    global target_input_path
    global target_log_path

    new_target_path = os.path.join("target", config["name"])
    if os.path.exists(new_target_path):
        logging.warning("target path %s alread exists" % new_target_path)
        shutil.rmtree(new_target_path)
    pathlib.Path(new_target_path).mkdir(parents=True, exist_ok=True)

    target_code_path = os.path.join(new_target_path, "code")
    copy(target_path, target_code_path, recursive=True)
    target_path = new_target_path

    target_input_path = os.path.join(target_path, "input")
    pathlib.Path(target_input_path).mkdir(exist_ok=True)
    copy(os.path.join(target_code_path, "input-seed"), target_input_path)

    target_log_path = os.path.join(target_path, "log")
    pathlib.Path(target_log_path).mkdir(exist_ok=True)
    copy(config_path, target_log_path)


def exec_args(input_file: str):
    global target_code_path
    install_dir = os.path.join(target_code_path, "racebench")
    comamnd_file = os.path.join(target_code_path, "command.txt")
    args = []
    with open(comamnd_file, "r") as f:
        for line in f.readlines():
            line = line.rstrip('\n')
            if line == "":
                continue
            arg = line.format(install_dir=install_dir, input_file=input_file)
            args.append(arg)
    return args


def get_arg_input():
    comamnd_file = os.path.join(target_code_path, "command.txt")
    with open(comamnd_file, "r") as f:
        for i, line in enumerate(f.readlines()):
            line = line.rstrip('\n')
            if line == "{input_file}":
                return i
    return -1


def copy_racebench_src():
    global target_code_path
    global config

    bug_num = config["bug"]["num"]
    try_num = config["bug"]["maxTry"]
    arg_input = get_arg_input()
    if arg_input == -1:
        logging.fatal("no arg_input")
        exit(1)

    files = ["racebench.c", "racebench.h"]
    defs = {"bug_num": bug_num,
            "try_num": try_num,
            "arg_input": arg_input}

    for name in files:
        path = os.path.join("inscode", name)
        new_path = os.path.join(target_code_path, name)
        code = read_file(path)
        for k, v in defs.items():
            code = code.replace("{" + k + "}", str(v))
        write_file(new_path, code)


def has_new_thread(bytes_input):
    global target_log_path
    global config

    timeout = config["mutate"]["stepTimeout"]

    with tempfile.NamedTemporaryFile(mode="wb", delete=True, prefix="fuzzy-", dir=target_log_path) as f:
        f.write(bytes_input)
        f.flush()

        args = exec_args(f.name)
        cmd = ["strace", "-e", "clone", "-f"] + args
        cmd = ["timeout", "-s", "INT", str(timeout)] + cmd
        environ = os.environ.copy()
        environ["RACEBENCH_STAT"] = "/dev/null"

        proc = subprocess.run(cmd, env=environ, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        return proc.stderr.find(b"clone(") != -1


def mutate_byte(x):
    while True:
        arithmetic = [x + 1, x - 1, x ^ 1, x << 1, x >> 1]
        letter = string.ascii_letters
        number = string.digits
        punctuation = string.punctuation
        allbyte = range(256)
        mutators = [arithmetic, letter, number, punctuation, allbyte]
        mutator = random.choice(mutators)
        y = random.choice(mutator)
        if isinstance(y, str):
            y = ord(y)
        y &= 0xff
        if y != x:
            return y


def mutate_bytes(bytes_input, byte_num):
    if byte_num > len(bytes_input):
        return False
    loc = random.randint(0, len(bytes_input) - byte_num)
    new_input = bytes_input.copy()
    for i in range(loc, loc + byte_num):
        new_input[i] = mutate_byte(new_input[i])
    if not has_new_thread(new_input):
        return None
    bytes_input[:] = new_input
    return loc


def get_mutated_input():
    global target_input_path, target_log_path
    global config

    input_seed_file = os.path.join(target_input_path, "input-seed")
    input_seed = read_file(input_seed_file, raw=True)

    byte_nums = config["bug"]["byteNum"]
    byte_nums = random.choice(byte_nums)
    total_trials = config["mutate"]["trials"]

    while True:
        cur_input = bytearray(input_seed)
        bytes_index = []
        for byte_num in byte_nums:
            for trials in range(total_trials):
                loc = mutate_bytes(cur_input, byte_num)
                if loc is not None:
                    # success
                    bytes_index.append((loc, byte_num))
                    break
            else:
                # all trials failed
                break
        else:
            # all byte_nums succeeded
            break

    return cur_input, bytes_index


def parloc_rand_name():
    parloc_rand_name.names = getattr(parloc_rand_name, "names", set())
    while True:
        chars = [random.choice(string.ascii_letters + string.digits)
                 for _ in range(6)]
        ans = ''.join(chars)
        if ans in parloc_rand_name.names:
            continue
        parloc_rand_name.names.add(ans)
        return ans


def find_parloc(bytes_input):
    global target_log_path
    global target_code_path
    global config

    rand_name = parloc_rand_name()
    input_file = os.path.join(target_log_path, "input-" + rand_name)
    parloc_out_file = os.path.join(target_log_path, "parloc-" + rand_name + ".out")
    conf_file = os.path.join(target_log_path, "parloc-" + rand_name + ".conf")
    log_file = os.path.join(target_log_path, "parloc-" + rand_name + ".log")

    args = exec_args(input_file)

    parloc_conf = config["parloc"]
    parloc_conf["output"] = parloc_out_file
    conf = {
        "program": {
            "exe": args[0],
            "args": args[1:],
            "srcdir": target_code_path,
        },
        "parloc": parloc_conf,
    }

    write_file(input_file, bytes_input, raw=True)
    write_file(conf_file, json.dumps(conf, indent=4), raw=False)

    environ = os.environ.copy()
    environ["PARLOC_CONFIG"] = conf_file
    environ["PYTHONPATH"] = os.getcwd() + ":" + os.getenv("PYTHONPATH", "")
    environ["RACEBENCH_STAT"] = "/dev/null"

    timeout = parloc_conf["totalTimeout"] + 1
    try:
        proc = subprocess.run(["gdb", "-q", "-nx", "--readnow", "-x", "parloc.py"],
                              env=environ,
                              timeout=timeout,
                              stdout=open(log_file, "wb"),
                              stderr=subprocess.STDOUT)
    except subprocess.TimeoutExpired:
        pass

    if not os.path.exists(parloc_out_file):
        return []
    out = read_file(parloc_out_file)
    parlocs = json.loads(out)
    return parlocs


def parloc_filter(parloc):
    parloc_filter.injector = getattr(parloc_filter, "injector", Injector())

    blacklist_path = os.path.join(target_code_path, "blacklist.txt")
    if os.path.exists(blacklist_path):
        blacklist = read_list_file(blacklist_path)
    else:
        blacklist = []

    def good_loc(ploc):
        filename, lineno = ploc["file"], ploc["line"]
        good_exts = [".c", ".cpp", ".cxx", ".cc"]
        if not any(filename.endswith(ext) for ext in good_exts):
            return False
        if os.path.basename(filename) in blacklist:
            return False
        loc = Location(filename, lineno, isBefore=False)
        return parloc_filter.injector.can_insert_at(loc)

    return good_loc(parloc[0]) and good_loc(parloc[1])


def locate_bug_one(bug_id):
    while True:
        logging.info("mutating input")
        bytes_input, bytes_index = get_mutated_input()
        logging.info("finding parloc")
        gdb_parlocs = find_parloc(bytes_input)
        gdb_parlocs = list(filter(parloc_filter, gdb_parlocs))
        if len(gdb_parlocs) > 0:
            parloc = random.choice(gdb_parlocs)
            logging.info("parloc %s" % parloc)
            break
    return (bytes_input, bytes_index, parloc)


def locate_bugs():
    global config
    bug_num = int(config["bug"]["num"])
    bugs = []
    for bug_id in range(bug_num):
        logging.info("locating bug %d" % bug_id)
        bug = locate_bug_one(bug_id)
        bugs.append(bug)
    return bugs


def save_input(bytes_input, bugid):
    global target_input_path
    in_file = os.path.join(target_input_path, "input-%d" % bugid)
    write_file(in_file, bytes_input, raw=True)


def unify_path(old_path):
    global target_code_path
    rpath = os.path.abspath(target_code_path)
    old_path = os.path.abspath(old_path)
    if old_path.startswith(rpath):
        return os.path.relpath(old_path, rpath)
    else:
        return old_path


def insert_bugs(bugs):
    global config
    global target_path
    global target_code_path

    injector = Injector()
    bugm = BugManager()
    bug_list = []

    for bug_id, bug in enumerate(bugs):
        bytes_input, bytes_index, parloc = bug
        save_input(bytes_input, bug_id)
        loc0 = Location(parloc[0]["file"], parloc[0]["line"], isBefore=False)
        loc1 = Location(parloc[1]["file"], parloc[1]["line"], isBefore=False)

        bug_func = bugm.get_bug_func_name(bug_id)
        decl_func = "void {func}(int);".format(func=bug_func)
        decl_func = "#ifdef __cplusplus\nextern \"C\"\n#endif\n" + decl_func
        code_template = "{func}({part});"
        injector.add(loc0, code_template.format(func=bug_func, part=0))
        injector.add(loc1, code_template.format(func=bug_func, part=1))
        injector.add(Location(loc0.filename), decl_func)
        injector.add(Location(loc1.filename), decl_func)

        pattern = bugm.add_bug_pattern(bug_id)
        interleave_num = bugm.add_bug_wrap(bug_id, bytes_input, bytes_index, config["bug"]["interNum"])

        _loc0 = Location(unify_path(loc0.filename), loc0.line, loc0.isBefore)
        _loc1 = Location(unify_path(loc1.filename), loc1.line, loc1.isBefore)
        bug_cur = {
            "id": bug_id,
            "bytes_index": bytes_index,
            "parloc": [str(_loc0), str(_loc1)],
            "pattern": pattern,
            "interleave": interleave_num
        }
        bug_list.append(bug_cur)

    injector.commit()
    bug_code = bugm.dump()
    bug_code_path = os.path.join(target_code_path, "racebench_bugs.c")
    write_file(bug_code_path, bug_code)

    bug_list_path = os.path.join(target_path, "bugs.json")
    bug_list = json.dumps(bug_list, indent=4)
    write_file(bug_list_path, bug_list)


def main():
    global config_path, target_path
    if len(sys.argv) != 3:
        print("Usage: %s <config> <target>" % sys.argv[0])
        exit()
    config_path = os.path.abspath(sys.argv[1])
    target_path = os.path.abspath(sys.argv[2])

    logging.info("preparing")
    change_work_dir()
    prepare()
    read_config()
    setup_target()

    logging.info("compiling target")
    copy_racebench_src()
    target_clean()
    target_build(debug_info=True)

    logging.info("locating bugs")
    time_start = time.time()
    bugs = locate_bugs()

    logging.info("inserting bugs")
    insert_bugs(bugs)
    time_end = time.time()

    logging.info("compiling target")
    target_build()

    logging.info("time per bug: %.2f" % ((time_end - time_start) / len(bugs)))


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    main()
