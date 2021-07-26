#!/usr/bin/env python3

import sys
import os
import pathlib
import subprocess
import threading
import signal
import logging


def change_work_dir():
    os.chdir(os.path.abspath(os.path.dirname(__file__)))


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


def read_file(filename, raw=False):
    mode = 'r' if not raw else 'rb'
    with open(filename, mode) as f:
        return f.read()


def copy(src, dst, recursive=False):
    cmd = ["cp", "-f", src, dst]
    if recursive:
        cmd.append("-r")
    subprocess.run(cmd, check=True)


def result_path(fuzzer, target):
    global results_path
    return os.path.join(results_path, fuzzer + "-" + target)


def fuztar_path(fuzzer, target, name):
    res_path = result_path(fuzzer, target)
    return os.path.join(res_path, name)


def init():
    global fuzzers_path
    global targets_path
    global results_path
    global fuzzer_names
    global target_names

    fuzzers_path = os.path.abspath("fuzzers")
    targets_path = os.path.abspath("programs")

    fuzzers_list = os.path.join(fuzzers_path, "list.txt")
    target_list = os.path.join(targets_path, "list.txt")
    fuzzer_names = read_list_file(fuzzers_list)
    target_names = read_list_file(target_list)

    global running_procs, proc_lock
    running_procs = set()
    proc_lock = threading.RLock()


def run_all_fuztar(func, concurrent=False):
    global fuzzer_names
    global target_names
    global ncores

    if not concurrent:
        for fuzzer in fuzzer_names:
            for target in target_names:
                func(fuzzer, target)
        return

    sem = threading.Semaphore(ncores)

    def func_wrap(fuzzer, target):
        sem.acquire()
        func(fuzzer, target)
        sem.release()

    threads = []
    for fuzzer in fuzzer_names:
        for target in target_names:
            th = threading.Thread(target=func_wrap, args=(fuzzer, target))
            th.start()
            threads.append(th)
    
    for th in threads:
        th.join()


def run_prepare(fuzzer, target):
    global targets_path

    logging.info("preparing %s-%s" % (fuzzer, target))

    res_path = result_path(fuzzer, target)
    if os.path.exists(res_path):
        logging.fatal("result path %s exists" % res_path)
        exit(1)
    pathlib.Path(res_path).mkdir(parents=True, exist_ok=True)

    bench_path = fuztar_path(fuzzer, target, "bench")
    input_path = fuztar_path(fuzzer, target, "input")
    output_path = fuztar_path(fuzzer, target, "output")

    os.mkdir(input_path)
    os.mkdir(output_path)

    copy(os.path.join(targets_path, target), bench_path, recursive=True)
    copy(os.path.join(bench_path, "input", "input-seed"), input_path)


def target_command_line(fuzzer, target):
    bench_path = fuztar_path(fuzzer, target, "bench")
    code_path = os.path.join(bench_path, "code")
    command_path = os.path.join(code_path, "command.txt")
    target_cmd = read_list_file(command_path)
    install_dir = os.path.join(code_path, "racebench")
    target_cmd = [x.replace("{install_dir}", install_dir) for x in target_cmd]
    return target_cmd


def run_compile(fuzzer, target):
    global fuzzers_path
    global running_procs, proc_lock

    logging.info("compiling %s-%s" % (fuzzer, target))

    work_dir = result_path(fuzzer, target)
    bench_path = fuztar_path(fuzzer, target, "bench")
    code_path = os.path.join(bench_path, "code")
    compile_log_path = fuztar_path(fuzzer, target, "compile.log")
    compile_log = open(compile_log_path, "wb")
    compile_env = os.path.join(fuzzers_path, fuzzer, "compile_env.sh")
    compile_env = os.path.abspath(compile_env)

    cmd = ["make clean", "make", "make install"]
    cmd = ["bash", "-c", " && ".join(cmd)]
    cmd = [compile_env] + cmd

    target_cmd = target_command_line(fuzzer, target)

    environ = os.environ.copy()
    environ["RACEBENCH_TARGET"] = os.path.relpath(target_cmd[0], code_path)
    environ["RACEBENCH_CODE_PATH"] = code_path

    with proc_lock:
        proc = subprocess.Popen(cmd, env=environ, cwd=work_dir, stdout=compile_log, stderr=subprocess.STDOUT)
        running_procs.add(proc)

    proc.wait()
    compile_log.close()

    with proc_lock:
        running_procs.discard(proc)

    if proc.returncode != 0:
        logging.warning("%s-%s compile error" % (fuzzer, target))


def run_fuzz(fuzzer, target):
    global fuzzers_path
    global fuzz_time
    global running_procs, proc_lock

    logging.info("fuzzing %s-%s" % (fuzzer, target))

    work_dir = result_path(fuzzer, target)
    fuzzer_script = os.path.join(fuzzers_path, fuzzer, "fuzz.sh")
    input_path = fuztar_path(fuzzer, target, "input")
    output_path = fuztar_path(fuzzer, target, "output")
    stat_path = fuztar_path(fuzzer, target, "rb_stat")
    fuzz_log_path = fuztar_path(fuzzer, target, "fuzz.log")
    fuzz_log = open(fuzz_log_path, "wb")
    bench_path = fuztar_path(fuzzer, target, "bench")
    timeout_path = os.path.join(bench_path, "code", "timeout")

    target_cmd = target_command_line(fuzzer, target)

    cmd = ["timeout", "-s", "INT", "-k", "1s", fuzz_time]
    cmd += [fuzzer_script, input_path, output_path] + target_cmd

    environ = os.environ.copy()
    environ["RACEBENCH_STAT"] = stat_path
    environ["RACEBENCH_TIMEOUT"] = read_file(timeout_path)

    with proc_lock:
        proc = subprocess.Popen(cmd, env=environ, cwd=work_dir, stdout=fuzz_log, stderr=subprocess.STDOUT)
        running_procs.add(proc)

    proc.wait()
    fuzz_log.close()

    with proc_lock:
        running_procs.discard(proc)


def signal_cancel():
    with proc_lock:
        for proc in running_procs:
            proc.send_signal(signal.SIGTERM)
    exit(2)


def prepare():
    prepare_script = os.path.join(os.path.curdir, "prepare.sh")
    subprocess.run(prepare_script, check=True, stdout=subprocess.DEVNULL)


def main():
    global ncores, fuzz_time
    global results_path

    if len(sys.argv) != 4:
        print("Usage: %s cores timeout results_path" % sys.argv[0])
        exit(0)

    ncores = int(sys.argv[1])
    ncores = max(1, ncores)
    fuzz_time = sys.argv[2]
    results_path = os.path.abspath(sys.argv[3])
    logging.info("ncores=%d, fuzz_time=%s, results_path=%s" %
                 (ncores, fuzz_time, results_path))

    change_work_dir()
    prepare()
    init()

    signal.signal(signal.SIGTERM, signal_cancel)
    signal.signal(signal.SIGINT, signal_cancel)

    run_all_fuztar(run_prepare, concurrent=False)
    run_all_fuztar(run_compile, concurrent=True)
    run_all_fuztar(run_fuzz, concurrent=True)


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    main()
