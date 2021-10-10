import sys
import json
import numpy

from utils import *
from target import TargetProgram
from error import BugError


class Config:
    def __init__(self, filename):
        content = read_file(filename)
        content = json.loads(content)
        self.mutate_num = content["mutate_num"]
        self.path_len = content["path_len"]
        self.bug_num = content["bug_num"]


def main():
    origin = sys.argv[1]
    target_root = sys.argv[2]
    config_path = sys.argv[3]
    config = Config(config_path)

    target = TargetProgram(origin, target_root, config.mutate_num)
    target.build_debug()
    for i in range(config.bug_num):
        print("new bug %d" % i)
        sys.stdout.flush()
        while True:
            try:
                target.new_bug(config.path_len)
                sys.stdout.flush()
            except BugError as e:
                print("main retry", type(e).__name__)
            else:
                break
    target.inject_bugs()
    target.dump_bug_info_files()
    target.check_reproduce_all()
    target.dump_install()
    target.cleanup()


if __name__ == "__main__":

    if len(sys.argv) != 4:
        print("Usage: %s origin target config" % sys.argv[0])
        sys.exit()

    numpy.seterr(over="ignore", under="ignore")

    main()
