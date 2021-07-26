#!/usr/bin/env python3

import gdb
import time
import json
import re
import os
import random
import pathlib

from gdb_utils import *


debug = True


def gdb_execute_timeout_wrap(cmd, show=None, stepTimeout=None):
    global config, start_time, total_timeout
    if stepTimeout is None:
        stepTimeout = config["parloc"]["stepTimeout"]
    stepTimeout = min(stepTimeout, total_timeout - (time.time() - start_time))
    gdb_execute_timeout(cmd, show, stepTimeout)


def file_in_folder(filename, dirname):
    if not os.path.isfile(filename):
        return False
    p = pathlib.PurePath(os.path.abspath(filename))
    try:
        p.relative_to(dirname)
    except ValueError:
        return False
    return True

file_blacklist = ["racebench.c"]

def good_source_file(filename):
    global srcdir
    if os.path.basename(filename) in file_blacklist:
        return False
    return file_in_folder(filename, srcdir)


def print_answer(ans):
    global config
    s = []
    for pos1, pos2 in ans:
        s.append([
            {"file": pos1[0], "line": pos1[1]},
            {"file": pos2[0], "line": pos2[1]},
        ])
    s = json.dumps(s, indent=4, sort_keys=True)
    out = config["parloc"]["output"]
    with open(out, "w") as f:
        f.write(s)


def read_config():
    global config
    config_name = os.environ["PARLOC_CONFIG"]
    config = {}
    try:
        with open(config_name, "r") as f:
            config = json.load(f)
    except FileNotFoundError:
        gdb.write("cannot open config file: {}\n".format(config_name), gdb.STDERR)
        gdb_quit()
    except json.JSONDecodeError as e:
        gdb.write("config file parsing error: {}\n".format(e), gdb.STDERR)
        gdb_quit()


def gdb_start():
    global config
    exe_path = gdb_path(config["program"]["exe"])
    gdb_execute("file -readnow " + exe_path)
    args = config["program"]["args"]
    args = " ".join(map(gdb_path, args))
    args += " >/dev/null 2>&1"
    gdb_execute("set args " + args)
    gdb_execute("set startup-with-shell on")
    gdb_execute("set non-stop off")
    gdb_execute("start")


def gdb_setup():
    gdb_execute("set follow-fork-mode parent")
    gdb_execute("set detach-on-fork off")
    gdb_execute("set follow-exec-mode new")
    gdb_execute("set scheduler-locking step")
    gdb_execute("set schedule-multiple on")
    gdb_execute("set print finish off")
    gdb_execute("set pagination off")


def gdb_newrun():
    # restart the program
    kill_all()
    gdb_start()
    gdb_setup()


def read_src_files():
    global config, sources, srcdir
    gdb_newrun()
    srcdir = config["program"]["srcdir"]
    srcdir = os.path.abspath(srcdir)
    if not srcdir.endswith(os.path.sep):
        srcdir += os.path.sep

    sources = {}
    file_name = None
    line_nums = set()
    listing = False

    def update():
        if file_name is None:
            return
        if len(line_nums) == 0:
            return
        sources[file_name] = sorted(line_nums)

    # get breakable line number in source files
    for line in gdb_execute("maintenance info line-table", show=False).split('\n'):
        if len(line) == 0:
            continue
        if line.startswith("objfile: "):
            update()
            file_name = None
            line_nums = set()
            listing = False
        elif line.startswith("symtab: "):
            match = re.search("symtab: (.*) \(\(struct", line)
            if match is None:
                continue
            _file_name = match.group(1)
            if not good_source_file(_file_name):
                continue
            file_name = _file_name
        elif line.startswith("INDEX "):
            listing = True
        elif listing:
            line_num = line.split()[1]
            if line_num == "END" or line_num == "0":
                continue
            line_num = int(line_num)
            line_nums.add(line_num)
    update()

    if len(sources) == 0:
        gdb.write("No source file found in symtab.\n", gdb.STDERR)
        gdb_quit()


# check if frame is our insterest
def good_frame(frame):
    sal = frame.find_sal()
    if not sal.is_valid():
        return False
    line = sal.line
    symtab = sal.symtab
    if symtab is None:
        return False
    filename = symtab.fullname()
    if not good_source_file(filename):
        return False
    return True


def get_file_line(frame):
    sal = frame.find_sal()
    line = sal.line
    filename = sal.symtab.fullname()
    return (filename, line)


def list_all_threads():
    gdb_execute("info thread")
    threads = []
    for inferior in gdb.inferiors():
        threads += inferior.threads()
    return threads


def get_good_frame():
    try:
        if debug:
            gdb_execute("info stack")
        frame = gdb.newest_frame()
    except gdb.error:
        return None, None
    level = 0
    while frame is not None:
        if good_frame(frame):
            break
        frame = frame.older()
        level += 1
    return level, frame


# return a good frame, or None if program dead.
def adjusted_newest_frame():
    global config
    # lookup a good frame
    frame_adjust_step = config["parloc"]["frameAdjustStep"]
    level = frame = None
    for _ in range(frame_adjust_step):
        level, frame = get_good_frame()
        if frame is not None:
            break
        try:
            gdb_execute_timeout_wrap("next")
        except (TimeoutError, gdb.error):
            return None
    if frame is None:
        return None
    
    # move to the frame
    for i in range(level):
        try:
            gdb_execute_timeout_wrap("finish")
        except (TimeoutError, gdb.error):
            return None

    try:
        frame = gdb.newest_frame()
        if not good_frame(frame):
            return None
        return frame
    except gdb.error:
        return None


def get_insertable(th):
    global config

    if not th.is_valid():
        return None
    th.switch()
    if debug:
        print("get insertable: ", th.num)
    frame = adjusted_newest_frame()
    if frame is None:
        return None
    pos = get_file_line(frame)

    try:
        gdb_execute_timeout_wrap("next")
    except (TimeoutError, gdb.error):
        return None

    return pos


def move_step(th):
    th.switch()
    if adjusted_newest_frame() is None:
        return False
    try:
        gdb_execute_timeout_wrap("step")
    except (TimeoutError, gdb.error):
        return False
    return True


def set_random_breakpoints():
    global config
    breakpoint_cnt = config["parloc"]["breakPointNum"]
    lines = ["%s:%s" % (src, line) for src in sources for line in sources[src]]
    positions = random.sample(lines, min(len(lines), breakpoint_cnt))
    print("breakpoints:", positions)
    bps = []
    for pos in positions:
        is_temp = random.choice([True, False])
        bp = gdb.Breakpoint(pos, internal=True, temporary=is_temp)
        bp.silent = True
        bps.append(bp)
    return bps


name_blacklist = [
    "join",
    "lock",
    "wait"
]

def notbad_frame_names(th):
    th.switch()
    frames = []
    try:
        frame = gdb.newest_frame()
        while frame is not None:
            frames.append(frame)
            frame = frame.older()
    except gdb.error:
        pass
    for frame in frames:
        name = frame.name()
        if name is None:
            continue
        name = name.lower()
        for s in name_blacklist:
            if name.find(s) != -1:
                return False
    return True


def try_once():
    global config
    global start_time, total_timeout
    wanderSteps = config["parloc"]["wanderSteps"]
    wanderSteps = max(wanderSteps, 1)
    if debug:
        print("try once")

    gdb_newrun()

    bps = set_random_breakpoints()
    ans = set()

    for cont_step in range(wanderSteps):
        if not gdb_live():
            break
        if len(ans) >= wanderSteps:
            break
        if time.time() - start_time >= total_timeout:
            break
        try:
            gdb_execute("set scheduler-locking off")
            gdb_execute_timeout_wrap("continue")
            gdb_execute("set scheduler-locking on")
        except (gdb.error, TimeoutError):
            break

        threads = list(filter(notbad_frame_names, list_all_threads()))
        if len(threads) < 2:
            continue
        random.shuffle(threads)
        threads = threads[:2]

        for step in range(wanderSteps):
            inserts = [get_insertable(th) for th in threads]
            if None in inserts:
                break
            print("answer: " + str(inserts))
            ans.add((inserts[0], inserts[1]))
            print_answer(ans)
            if len(ans) >= wanderSteps:
                break
            if not move_step(random.choice(threads)):
                break


    for bp in bps:
        if bp.is_valid():
            bp.delete()

    if len(ans) == 0:
        return False
    return True


def main():
    global config
    global start_time, total_timeout

    start_time = time.time()

    read_config()
    read_src_files()
    totTrial = config["parloc"]["trials"]
    total_timeout = config["parloc"]["totalTimeout"]

    for trial in range(totTrial):
        if try_once():
            break
    gdb_quit()


main()
