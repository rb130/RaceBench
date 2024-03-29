#!/usr/bin/env python3

import sys
import struct
import datetime


"""
typedef struct racebench_statis {
    uint64_t total_run;
    uint64_t trigger_num[MAX_BUGNUM];
    uint64_t trigger_time[MAX_BUGNUM];
} __attribute__((aligned(8),packed)) racebench_statis;
"""


def l2s(l):
    ss = ["[%d]=%s" % (i,v) for i, v in enumerate(l)]
    ss = ", ".join(ss)
    return "{%s}" % ss


def show(name, data):
    print("%s (sum %d, unique %d): %s" % (name, sum(data), sum(map(bool, data)), l2s(data)))


def main():
    if len(sys.argv) != 2:
        print("Usage: %s <rb_stat>" % sys.argv[0])
        exit(0)
    filename = sys.argv[1]
    with open(filename, "rb") as f:
        data = f.read()
    
    bug_num = (len(data) // 8 - 1) // 2
    assert len(data) == 8 * (bug_num * 2 + 1)

    unpacked = list(struct.iter_unpack("<Q", data))
    unpacked = [x[0] for x in unpacked]
    print(unpacked, bug_num)
    total_run = unpacked[0]
    unpacked = unpacked[1:]
    trigger_num = unpacked[0:bug_num]
    trigger_time = []
    for t in unpacked[bug_num:bug_num*2]:
        if t == 0:
            t = None
        else:
            t = datetime.datetime.fromtimestamp(t).strftime("%c")
        trigger_time.append(t)

    print("total_run: %d" % total_run)
    show("trigger_num", trigger_num)
    print("trigger_time", trigger_time)
    print("find bugs:", [i for i in range(bug_num) if trigger_num[i]>0])


if __name__ == "__main__":
    main()
