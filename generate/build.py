from typing import Dict, Optional
import os
import subprocess
from utils import *


class Builder:
    def __init__(self, path: str):
        self.path = path

    def exec(self, arg: str, env: Optional[Dict[str, str]] = None, dump_cmd: bool = False):
        cmd = ["make"]
        if arg != "":
            cmd.append(arg)
        new_env = os.environ.copy()
        if env is not None:
            for k, v in env.items():
                new_env[k] = v
        if dump_cmd:
            cmd = ["bear", "--"] + cmd
        subprocess.run(cmd, cwd=self.path, env=new_env,
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def clean(self):
        self.exec("clean")

    def compile(self, debug_info: bool = False, dump_cmd: bool = False):
        if debug_info:
            env = {"CFLAGS": "-g", "CXXFLAGS": "-g", "LDFLAGS": "-g"}
        else:
            env = {}
        self.exec("", env, dump_cmd)

    def install(self):
        self.exec("install")

    def rebuild_and_install(self, debug_info: bool = False, dump_cmd: bool = False):
        self.clean()
        self.compile(debug_info, dump_cmd)
        self.install()

    def clean_compile_db(self):
        compile_db = os.path.join(self.path, "compile_commands.json")
        remove_file(compile_db)
