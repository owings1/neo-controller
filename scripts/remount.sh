#!/bin/bash
#
# This works around bug where, by default,
# macOS 14.x before 14.4 writes part of a file immediately,
# and then doesn't update the directory for 20-60 seconds, causing
# the file system to be corrupted.
#
set -e

if [[ ! -e /Volumes/CIRCUITPY ]] ; then
    echo 'no volume found' >&2
    exit 1
fi
disky=`df | grep CIRCUITPY | cut -d" " -f1 | head -n 1`
sudo umount /Volumes/CIRCUITPY
sudo mkdir /Volumes/CIRCUITPY
sleep 2
sudo mount -v -o noasync -t msdos $disky /Volumes/CIRCUITPY

if [[ ! -e /Volumes/CIRCUITPY\ 1 ]]; then
    exit 0
fi

disky=`df | grep CIRCUITPY\ 1 | cut -d" " -f1 | head -n 1`
sudo umount /Volumes/CIRCUITPY\ 1
sudo mkdir /Volumes/CIRCUITPY\ 1 
sleep 2
sudo mount -v -o noasync -t msdos $disky /Volumes/CIRCUITPY\ 1