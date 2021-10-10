#!/usr/bin/env python3

import sys
import os
import json
import re
import subprocess
import logging


def read_file(filename, raw=False):
    mode = 'r' if not raw else 'rb'
    with open(filename, mode) as f:
        return f.read()


def write_file(filename, data, raw=False):
    mode = 'w' if not raw else 'wb'
    with open(filename, mode) as f:
        f.write(data)


def copy(src, dst, recursive=False):
    cmd = ["cp", "-f", src, dst]
    if recursive:
        cmd.append("-r")
    subprocess.run(cmd, check=True)


def escaped_path(s: str):
    # auto add escape charactors and outer quotes
    s = json.dumps(s)
    s = s.replace("$", "\\$")
    return s


def unify_path(old_path):
    abs_target_path = os.path.abspath(target_path)
    abs_old_path = os.path.abspath(old_path)
    if abs_old_path.startswith(abs_target_path):
        return os.path.relpath(abs_old_path, abs_target_path)
    else:
        return old_path


def configure():
    global target_path
    logging.info("configuring")
    subprocess.run(["./rb-build", "config"],
                   cwd=target_path, check=True,
                   stdout=subprocess.DEVNULL)


def build_clean():
    global target_path
    logging.info("cleaning")
    subprocess.run(["./rb-build", "clean"],
                   cwd=target_path, check=True,
                   stdout=subprocess.DEVNULL)


def get_binary_name():
    global binary_name
    global target_path
    proc = subprocess.run(["./rb-build", "binary"],
                          cwd=target_path, check=True,
                          stdout=subprocess.PIPE)
    binary_name = proc.stdout.decode()
    binary_name = binary_name.rstrip('\n')


def get_compile_dest(args):
    try:
        dash_o = args.index("-o")
        return args[dash_o + 1]
    except (ValueError, IndexError):
        return None


def recognize_compiler(exe):
    CC = ["gcc", "clang", "cc"]
    CXX = ["g++", "clang++", "c++"]
    name = os.path.basename(exe)
    if name in CC:
        return "$(CC)"
    if name in CXX:
        return "$(CXX)"
    return exe


def find_link_from_bear(bear_out):

    def is_link_target(execution):
        global binary_name
        exe = execution["executable"]
        if recognize_compiler(exe) == exe:
            return False
        args = execution["arguments"]
        workdir = execution["workingDir"]
        name = get_compile_dest(args)
        if name is None:
            return False
        if os.path.basename(name) != os.path.basename(binary_name):
            return False
        for i in range(1, len(args)):
            arg = args[i]
            if arg.startswith("-"):
                continue
            arg_path = os.path.join(workdir, arg)
            if not os.path.exists(arg_path):
                if args[i-1] != "-o" and args[i-1] != "-l":
                    return False
        return True

    exec_pattern = r"execution: (.*)"
    for match in re.finditer(exec_pattern, bear_out):
        execution = json.loads(match.group(1))
        if is_link_target(execution):
            return execution
    return None


def parse_link_args(link_execution):
    link_opts = []
    target_objs = []
    target_exe = None
    dash_o = -1
    workdir = link_execution["workingDir"]
    for i, arg in enumerate(link_execution["arguments"]):
        if i == 0:
            continue
        if arg == "-o":
            dash_o = i
            continue
        if i == dash_o + 1:
            arg_path = unify_path(os.path.join(workdir, arg))
            target_exe = arg_path
            continue
        if arg.startswith("-"):
            link_opts.append(arg)
        else:
            arg_path = unify_path(os.path.join(workdir, arg))
            target_objs.append(arg_path)
    return link_opts, target_objs, target_exe


def format_code(src_path):
    global target_path
    formatter = os.path.join(os.path.dirname(__file__), "../format/formatter")
    proc = subprocess.run([formatter, src_path, target_path],
                          check=True, stdout=subprocess.DEVNULL)


def format_all_code(target_srcs):
    global target_path
    for src in target_srcs:
        logging.info("formatting %s" % src)
        src_path = os.path.join(target_path, src)
        format_code(src_path)


def target_build():
    global target_path
    global dest_path

    logging.info("compiling")
    compile_cmd_path = "compile_commands.json"
    proc = subprocess.run(["bear", "--output", compile_cmd_path, "--verbose", "--",
                           "sh", "-c", "./rb-build build 2>/dev/null"],
                          cwd=target_path, check=True,
                          stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    compile_cmd_path = os.path.join(target_path, compile_cmd_path)
    compile_cmds = read_file(compile_cmd_path)
    compile_cmds = json.loads(compile_cmds)

    target_srcs = [unify_path(cmd["file"]) for cmd in compile_cmds]

    bear_out = proc.stderr.decode("latin-1")
    link_execution = find_link_from_bear(bear_out)
    if link_execution is None:
        logging.fatal("cannot find linker command line")
        exit(1)
    del link_execution["environment"]
    print("link commands: %s" % link_execution)

    format_all_code(target_srcs)
    os.unlink(compile_cmd_path)

    logging.info("generating makefile")
    gen_makefile(link_execution)


def gen_makefile(link_execution):
    global dest_path
    makefile_path = os.path.join(os.path.dirname(__file__), "sample-Makefile")
    new_makefile_path = os.path.join(dest_path, "Makefile")
    code = read_file(makefile_path)

    linker = link_execution["executable"]
    link_args = link_execution["arguments"][1:]
    workdir = link_execution["workingDir"]
    abs_workdir = os.path.abspath(workdir)
    workdir = unify_path(workdir)

    def convert_link_arg(arg):

        def convert_path(path):
            if os.path.isabs(path):
                if not os.path.isabs(unify_path(path)):
                    return os.path.relpath(path, abs_workdir)
            return path

        if arg.startswith("-"):
            if arg[:2] in {"-I", "-L"}:
                arg = arg[:2] + convert_path(arg[2:])
        else:
            arg = convert_path(arg)

        return escaped_path(arg)

    linker = recognize_compiler(linker)
    link_args = [convert_link_arg(a) for a in link_args]
    if linker == "$(CC)":
        link_args.append("$(CFLAGS)")
    if linker == "$(CXX)":
        link_args.append("$(CXXFLAGS)")

    defs = {"O_LINKER": linker,
            "O_LINK_ARGS": ' '.join(link_args),
            "O_WORKDIR": workdir}
    for k, v in defs.items():
        code = code.replace("{" + k + "}", str(v))
    write_file(new_makefile_path, code)


def copy_target():
    global dest_path
    global target_path
    logging.info("copying target")
    new_target_path = os.path.join(dest_path, "src")
    os.mkdir(dest_path)
    copy(target_path, new_target_path, recursive=True)
    target_path = new_target_path


def main():
    global target_path
    global dest_path

    if len(sys.argv) != 3:
        print("Usage: %s <src> <dst>" % sys.argv[0])
        exit(1)
    target_path = sys.argv[1]
    dest_path = sys.argv[2]
    if os.path.exists(dest_path):
        print("dest path %s already exists" % dest_path)
        exit(1)

    get_binary_name()

    copy_target()

    configure()
    target_build()
    build_clean()


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    main()
