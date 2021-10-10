from typing import AnyStr
import os


def read_file(filename: str, raw: bool = False) -> AnyStr:
    mode = 'r' if not raw else 'rb'
    encode = 'latin-1' if not raw else None
    with open(filename, mode, encoding=encode) as f:
        return f.read()


def write_file(filename: str, data: AnyStr):
    raw = not isinstance(data, str)
    mode = 'w' if not raw else 'wb'
    encode = 'latin-1' if not raw else None
    with open(filename, mode, encoding=encode) as f:
        f.write(data)


def remove_file(filename: str):
    if os.path.isfile(filename):
        os.unlink(filename)


def extend_path(p: str, cwd: str) -> str:
    if os.path.isabs(p):
        return p
    return os.path.join(cwd, p)


def is_empty_dir(p: str) -> bool:
    if not os.path.isdir(p):
        return False
    return len(os.listdir(p)) == 0


def is_empty_file(p: str) -> bool:
    if not os.path.isfile(p):
        return False
    return len(read_file(p)) == 0
