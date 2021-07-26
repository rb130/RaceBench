#!/bin/bash

fuzzer_dir=`dirname $0`/honggfuzz
fuzzer=$fuzzer_dir/honggfuzz

input_dir=$1
output_dir=$2
args=()
for arg in "${@:3}"; do
    if [[ "{input_file}" == "$arg" ]]; then
        arg="___FILE___"
    fi
    args+=("$arg")
done

time_limit=${RACEBENCH_TIMEOUT}
memory_limit=1024 # Mib
num_thread=1

rm -rf $output_dir
$fuzzer -t $time_limit --rlimit_as $memory_limit -n $num_thread -i $input_dir -W $output_dir --tmout_sigvtalrm -- "${args[@]}"
