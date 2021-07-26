#!/bin/bash

fuzzer_dir=`dirname ${BASH_SOURCE[0]}`/honggfuzz
fuzzer_dir=$(realpath $fuzzer_dir)
export CC=$fuzzer_dir/hfuzz_cc/hfuzz-gcc
export CXX=$fuzzer_dir/hfuzz_cc/hfuzz-g++

target=${RACEBENCH_TARGET}
code_path=${RACEBENCH_CODE_PATH}

if [[ `gcc --version | awk '/gcc/ && ($3+0)<8{print "below"}'` = "below" ]]; then
    export HFUZZ_CC_USE_GCC_BELOW_8=1
fi

cd ${code_path}
make clean
make || exit 1
make install || exit 1

if [[ ! -f ${target} ]]; then
    # ${target} is a relative path to ${code_path}
    echo "Target binary file does not exist: ${target}"
    exit 1
fi
