import gdb
import json
import subprocess


debug = False


def delay_kill(pids, timeout):
    return subprocess.Popen([
        "/bin/sh", "-c",
        "sleep %d && kill -KILL %s"
            % (timeout, ' '.join(map(str, pids)))
        ],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def gdb_execute(cmd, show=None):
    if show is None:
        show = debug
    if debug:
        print(cmd)
    return gdb.execute(cmd, from_tty=False, to_string=not show)


def gdb_execute_timeout(cmd, show=None, stepTimeout=None):
    global config
    if show is None:
        show = debug
    if stepTimeout is None:
        gdb_execute(cmd, show)
        return
    pids = [x.pid for x in gdb.inferiors()]
    proc = delay_kill(pids, stepTimeout)
    gdb_bad = None
    ans = None
    try:
        ans = gdb_execute(cmd, show)
    except gdb.error as e:
        gdb_bad = e
    if proc.poll() is not None:
        # program was killed
        raise TimeoutError("gdb execute timeout")
    else:
        # stop killer
        proc.kill()
        if gdb_bad:
            raise gdb_bad
        return ans


def kill_all():
    inferior_id = [i.num for i in gdb.inferiors()]
    if len(inferior_id) > 0:
        inferiors = " ".join(map(str, inferior_id))
        gdb_execute("kill inferiors " + inferiors)


def gdb_quit():
    kill_all()
    gdb_execute("quit")


def gdb_live():
    return any(th.is_valid() for th in gdb.selected_inferior().threads())


def gdb_path(s: str):
    # auto add escape charactors and outer quotes
    s = json.dumps(s)
    s = s.replace("$", "\\$")
    return s