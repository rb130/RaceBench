# RaceBench

RaceBench injects triggerable concurrency bugs into existing concurrent programs.

## Build

Build dominator analyzer.
```shell
cd dom
cmake .
make
```

The executable file should be located at `dom/dom`.

## Build

Build dominator analyzer.
```shell
cd dom
cmake .
make
```

The executable file should be located at `dom/dom`.

## How to add a new target

Code of the target program should be formatted with `format/formatter`.

Write a `Makefile` script for the target.
It should implement the following options.
```shell
# compile
make
# install to racebench folder
make install
# clean up racebench and compile results
make clean
```
If `racebench.c` and `racebench_bugs.c` exist, they should also be compiled and linked to the program.
A [tool](#generate-makefile-script) is provided to automatically generate such a script.

Write a `command.txt` containing the command line arguments of the target program.
Put each argument on a single line.
Use macros to mark special arguments.
`{install_dir}` represents the installation directory, i.e., the `racebench` folder.
`{input_file}` represents the input file argument.

Write seed input in `input-seed` file.

Write estimated fuzzing timeout (seconds) in `timeout` file.

Run `generate/main.py`.

## Generate Makefile script

Write a `rb-build` script in the target's directory.
It should implement the following options.
```shell
cd <directory>
# configure the target
rb-build config
# compile the target
rb-build build
# clean up
rb-build clean
# show the name of executable file
rb-build binary
```

When configuring or compiling the target, `rb-build` should make use of environment variables including `CC`, `CFLAGS`, `CXX`, `CXXFLAGS` and `LDFLAGS`.

Run `builder/gen.py <src> <dst>`.
`<src>` is the target's directory.
`<dst>` is the output destination.

This will also automatically format the code.

## Dependencies

- python 3.7+
- strace
- gdb 10.1 (with python support)
- gcc, g++
- clang-tidy
- clang-format
- bear 3.0.8
- llvm/clang 13
- cmake
