#!/bin/bash -e

YAML_FILES="ctypes.yaml ctypes_array.yaml ctypes_and_ctypes_array.yaml complex_type.yaml complex_and_ctype.yaml complex_type_array.yaml messages.yaml ctypes_enums.yaml bitfield.yaml bitfield_messages.yaml"

for y in ${YAML_FILES}; do
  echo "===== Processing $y ====="
  ../genmsg.py ${y} --py-gen --h-gen
  ./autotest.py --autotest
  gcc main.c -o main
done
