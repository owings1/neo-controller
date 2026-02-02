#!/bin/bash
set -e
if [[ "$#" -ne 1 ]]; then
  echo "Usage: $0 <dest>" >&2
  exit 1
fi
dest="$(realpath "$1")"
cd "$(dirname "$0")"
cp -X -v \
  classes.py \
  code.py \
  defaults.py \
  utils.py \
  "$dest"
cp -X -v -n \
  settings.py \
  "$dest"
cp -X -v -n \
  lib/* \
  "$dest/lib/"