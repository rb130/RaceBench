#!/usr/bin/env python3

import sys
import struct


"""
typedef struct racebench_statis {
    uint32_t total_run;
    uint32_t tried_num[MAX_BUGNUM];
    uint32_t dua_pass_num[MAX_BUGNUM];
    uint32_t check_pass_num[MAX_BUGNUM];
    uint32_t trigger_num[MAX_BUGNUM];
} __attribute__((aligned(4),packed)) racebench_statis;
"""


def l2s(l):
    ss = ["[%d]=%s" % (i,v) for i, v in enumerate(l)]
    ss = ", ".join(ss)
    return "{%s}" % ss


def show(name, data):
    print("%s (%d, %d): %s" % (name, sum(data), sum(map(bool, data)), l2s(data)))


def main():
    if len(sys.argv) != 2:
        print("Usage: %s <rb_stat>" % sys.argv[0])
        exit(0)
    filename = sys.argv[1]
    with open(filename, "rb") as f:
        data = f.read()
    
    bug_num = (len(data) // 4 - 1) // 4
    assert len(data) == 4 * (1 + 4 * bug_num)

    unpacked = list(struct.iter_unpack("<I", data))
    unpacked = [x[0] for x in unpacked]
    total_run = unpacked[0]
    unpacked = unpacked[1:]
    tried_num = unpacked[0:bug_num]
    dua_pass_num = unpacked[bug_num:bug_num*2]
    check_pass_num = unpacked[bug_num*2:bug_num*3]
    trigger_num = unpacked[bug_num*3:bug_num*4]

    print("total_run: %d" % total_run)
    show("tried_num", tried_num)
    show("dua_pass_num", dua_pass_num)
    show("check_pass_num", check_pass_num)
    show("trigger_num", trigger_num)


if __name__ == "__main__":
    main()
