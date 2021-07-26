#!/bin/bash

output_dir=$1
script_path=`dirname ${BASH_SOURCE[0]}`/list_trigger.py
python3 $script_path $output_dir || exit 1