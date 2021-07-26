#!/bin/bash

ASLR="/proc/sys/kernel/randomize_va_space"
if [[ `cat $ASLR` -ne "0" ]]; then
    sudo sh -c "echo 0 > $ASLR"
fi