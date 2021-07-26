#!/bin/bash

fuzzer_dir=`dirname $0`/AFLplusplus
fuzzer=$fuzzer_dir/afl-fuzz

input_dir=$1
output_dir=$2
args=()
for arg in "${@:3}"; do
    if [[ "{input_file}" == "$arg" ]]; then
        arg="@@"
    fi
    args+=("$arg")
done

time_limit=$((${RACEBENCH_TIMEOUT}*1000))
mem_limit=1G
export AFL_NO_AFFINITY=1
export AFL_NO_UI=1
export AFL_I_DONT_CARE_ABOUT_MISSING_CRASHES=1
export AFL_SKIP_CPUFREQ=1

rm -rf $output_dir
$fuzzer -t $time_limit -m $mem_limit -i $input_dir -o $output_dir -- "${args[@]}"
