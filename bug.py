import os
import random
import subprocess


PATTERN_PATH = "patterns"
CODE_PATH = "inscode"
BUG_TEMPLATE_PATH = os.path.join(CODE_PATH, "bug-template.c")


def rb_input_map(x):
    x &= 0xffffffff
    x ^= 0xda017281;
    x += 0x10101014;
    x = (x << 4) | ((x >> 28) & 0xf);
    x &= 0xffffffff
    return x


def make_carr(lst):
    def to_str(x):
        if isinstance(x, int):
            return hex(x)
        return str(x)
    return "{%s}" % (", ".join(map(to_str, lst)))


class BugManager:
    def __init__(self):
        self.template = []
        for filename in os.listdir(PATTERN_PATH):
            if not filename.endswith(".c"):
                continue
            filename = os.path.join(PATTERN_PATH, filename)
            self.template.append(filename)

        self.results = []
        self.results.append("#define _GNU_SOURCE")
        self.results.append("#include <pthread.h>")
        self.results.append("#include <stdio.h>")
        self.results.append("#include <stdlib.h>")
        self.results.append("#include <time.h>")
        self.results.append("#include <unistd.h>")
        self.results.append("#include \"racebench.h\"")
    
    def add_bug_pattern(self, bug_id):
        bug_file = random.choice(self.template)
        pattern = os.path.splitext(os.path.basename(bug_file))[0]
        proc = subprocess.run(["gcc", "-E", "-P", "-I" + CODE_PATH, "-DBUGID=%d" % bug_id, bug_file],
                              stdout=subprocess.PIPE, check=True)
        self.results.append(proc.stdout.decode())
        return pattern

    def add_bug_wrap(self, bug_id, bytes_input, bytes_index, inter_nums):
        index_num = len(bytes_index)
        inter_num = random.choice(inter_nums)
        input_indices = [x[0] for x in bytes_index]
        input_sizes = [x[1] for x in bytes_index]
        pad_num = max(0, inter_num - index_num)
        pads = [random.randint(0, 0xFFFFFFFF) for _ in range(pad_num)]
        befores = [random.randint(0, 1) for _ in range(inter_num)]
        correct_inputs = []

        for i in range(index_num):
            bs = bytes_input[input_indices[i] : input_indices[i] + input_sizes[i]]
            val = int.from_bytes(bs, byteorder='little')
            correct_inputs.append(val)
        mapped_input = list(map(rb_input_map, correct_inputs))

        magic_value = 0
        for i in range(max(index_num, inter_num)):
            if i < index_num:
                val = mapped_input[i]
            else:
                val = pads[i - index_num]
            magic_value += val
            magic_value &= 0xFFFFFFFF

        proc = subprocess.run(["gcc", "-E", "-P", "-I" + CODE_PATH,
                               "-DBUGID=%d" % bug_id,
                               "-DINTERLEAVE_NUM=%d" % inter_num,
                               "-DINDEX_NUM=%d" % index_num,
                               "-DINPUT_INDICES=%s" % make_carr(input_indices),
                               "-DINPUT_SIZES=%s" % make_carr(input_sizes),
                               "-DINPUT_PADS=%s" % make_carr(pads),
                               "-DBEFORES=%s" % make_carr(befores),
                               "-DMAPPED_INPUTS=%s" % make_carr(mapped_input),
                               "-DMAGIC_VALUE=%s" % hex(magic_value),
                               BUG_TEMPLATE_PATH],
                              stdout=subprocess.PIPE, check=True)
        self.results.append(proc.stdout.decode())

        return inter_num
    
    def get_bug_func_name(self, bug_id):
        return "racebench_bug%d" % bug_id

    def dump(self):
        return '\n'.join(self.results)
