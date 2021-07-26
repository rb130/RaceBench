#!/usr/bin/env python3

import sys
import os

if __name__ == '__main__':
    if len(sys.argv) != 2:
        print("Usage: %s output_dir" % sys.argv[0])
        exit(1)
    output_dir = sys.argv[1]
    visited = set()
    for filename in os.listdir(output_dir):
        if filename == "HONGGFUZZ.REPORT.TXT":
            continue
        splits = filename.split('.')
        if len(splits) < 11:
            continue
        if splits[1] != "PC" or splits[3] != "STACK":
            continue
        pc = int(splits[2], 16)
        pc &= 0xfff
        sp = int(splits[4], 16)
        sp &= 0xfff
        h = (sp<<12) + pc
        if h in visited:
            continue
        visited.add(h)
        print(os.path.join(output_dir, filename))