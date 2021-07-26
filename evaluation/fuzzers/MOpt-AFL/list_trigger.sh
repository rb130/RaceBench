#!/bin/bash

output_dir=$1

mapfile -t crash_list < <(find $output_dir -type d -name "crashes")
mapfile -t hang_list < <(find $output_dir -type d -name "hangs")
dir_list=( "${crash_list[@]}" "${hang_list[@]}" )

files=()
for dir in "${dir_list[@]}"; do
    for filename in $(ls "$dir"); do
        if [[ "$filename" != "README.txt" ]]; then
            files+=( "$dir/$filename" )
        fi
    done
done

for filename in "${files[@]}"; do
    echo "$filename"
done