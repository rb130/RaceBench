#!/bin/bash

fuzzer_dir=`dirname ${BASH_SOURCE[0]}`/AFL
fuzzer_dir=$(realpath $fuzzer_dir)
export CC=$fuzzer_dir/afl-gcc
export CXX=$fuzzer_dir/afl-g++
export AFL_QUIET=1
export AFL_DONT_OPTIMIZE=1

target=${RACEBENCH_TARGET}
code_path=${RACEBENCH_CODE_PATH}

cd ${code_path}
make clean
make || exit 1
make install || exit 1

if [[ ! -f ${target} ]]; then
    # ${target} is a relative path to ${code_path}
    echo "Target binary file does not exist: ${target}"
    exit 1
fi