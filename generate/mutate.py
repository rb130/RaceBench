from typing import ByteString, Callable
import string
import random
from enum import Enum


def mutate_byte(x: int) -> int:
    arithmetic = [x + 1, x - 1, x ^ 1, x << 1, x >> 1]
    letter = string.ascii_letters
    number = string.digits
    punctuation = string.punctuation
    whitespace = string.whitespace
    allbyte = range(256)
    mutators = [arithmetic, letter, number, punctuation, whitespace, allbyte]
    mutator = random.choice(mutators)
    y = random.choice(mutator)
    if isinstance(y, str):
        y = ord(y)
    y &= 0xff
    return y


class Mutator:

    class Method(Enum):
        Change = 0
        New = 1
        Delete = 2

    Methods = [Method.Change, Method.New, Method.Delete]
    DefaultMethodsWeight = [10, 1, 1]

    def __init__(self, checker: Callable[[ByteString], bool]):
        self.checker = checker
        self.methods_weight = Mutator.DefaultMethodsWeight

    def mutate(self, input_bytes: bytearray, num: int):
        if not self.checker(input_bytes):
            raise ValueError("input not valid")
        changed = 0
        while changed < num:
            new_input = self._mutate_once_nocheck(input_bytes)
            if self.checker(new_input):
                input_bytes[:] = new_input
                changed += 1

    def _mutate_once_nocheck(self, input_bytes: bytearray) -> bytearray:
        n = len(input_bytes)
        loc = random.randint(0, n)
        if loc == n:
            method = Mutator.Method.New
            value = random.randint(0, 0xff)
        else:
            method = random.choices(Mutator.Methods, self.methods_weight)[0]
            value = input_bytes[loc]
        value = mutate_byte(value)
        new_input = input_bytes.copy()
        if method == Mutator.Method.New:
            new_input[loc:loc + 1] = [value]
        elif method == Mutator.Method.Delete:
            del new_input[loc]
        elif method == Mutator.Method.Change:
            new_input[loc] = value
        return new_input
