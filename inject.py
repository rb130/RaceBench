import os
import re


inject_file_blacklist = ["racebench.c"]


class Location:
    def __init__(self, filename, line=0, isBefore=True):
        self.filename = filename
        self.line = line
        self.isBefore = isBefore
    
    def __str__(self):
        return "{file}:{line}{sign}".format(
            file=self.filename, line=self.line,
            sign='-' if self.isBefore else '+')


class InjectError(Exception): pass


class Insertion:
    def __init__(self, loc, code):
        self.loc = loc
        self.code = code


class Injector:
    def __init__(self):
        self.ops = dict()
        self.line_cache = dict()

    def add(self, loc: Location, code: str):
        filename = os.path.abspath(loc.filename)
        if filename not in self.ops:
            self.ops[filename] = []
        self.ops[filename].append(Insertion(loc, code))
    

    def commit(self):
        ahead_lines = {}
        for filename, insertion in self.ops.items():
            with open(filename, "r") as f:
                lines = f.readlines()

            insertion = sorted(insertion, key=lambda x: (x.loc.line, not x.loc.isBefore))
            modified_lines = []
            ins_idx = 0

            while ins_idx < len(insertion) and insertion[ins_idx].loc.line == 0:
                modified_lines.append(insertion[ins_idx].code)
                ins_idx += 1
            ahead_lines[filename] = ins_idx

            for lineno in range(len(lines)):
                has_insert = False
                raw_line = lines[lineno]
                if raw_line.endswith("\n"):
                    raw_line = raw_line[:-1]
                lineno += 1
                cur_line = []
                while ins_idx < len(insertion) and insertion[ins_idx].loc.line == lineno:
                    if not insertion[ins_idx].loc.isBefore:
                        break
                    cur_line.append(insertion[ins_idx].code)
                    ins_idx += 1
                    has_insert = True
                cur_line.append(raw_line)
                while ins_idx < len(insertion) and insertion[ins_idx].loc.line == lineno:
                    # assert not insertion[ins_idx].loc.isBefore
                    cur_line.append(insertion[ins_idx].code)
                    ins_idx += 1
                    has_insert = True
                if has_insert and not Injector.is_good_line(raw_line):
                    raise InjectError()
                modified_lines.append(' '.join(cur_line))
            
            while ins_idx < len(insertion):
                modified_lines.append(insertion[ins_idx].code)
                ins_idx += 1
        
            with open(filename, "w") as f:
                f.write('\n'.join(modified_lines))

        self.ops = dict()
        return ahead_lines


    def build_cache(self, filename):
        with open(filename) as f:
            lines = f.readlines()
        line_good = [Injector.is_good_line(line) for line in lines]
        self.line_cache[filename] = line_good

    def can_insert_at(self, loc):
        filename = os.path.abspath(loc.filename)
        if os.path.basename(filename) in inject_file_blacklist:
            return False
        line = loc.line
        if filename not in self.line_cache:
            self.build_cache(filename)
        cache = self.line_cache[filename]
        return line == 0 or line > len(cache) or cache[line-1]

    @staticmethod
    def is_good_line(line):
        line = line.rstrip("\n")
        if re.search(r"\{|\}|\n", line) is not None:
            return False
        if re.search(r"\b(break|continue|goto|return|longjmp)\b", line) is not None:
            return False
        if line.strip().startswith("#"):
            return False
        return True