#!/bin/bash

fuzzer_dir=`dirname ${BASH_SOURCE[0]}`/AFL-maple
fuzzer_dir=$(realpath $fuzzer_dir)

# Stage 1. original compilation (without instrumentation, used for maple)

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

# Stage 2. temporary save out of workdir
tmp_name=$(mktemp -p /tmp --suffix=.maple)
cp "${target}" "${tmp_name}" || exit 1

# Stage 3. instrumented compile
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

# Stage 4. copy the saved one back

mv "${tmp_name}" "${target}.maple" || exit 1
chmod +x "${target}.maple" || exit 1
