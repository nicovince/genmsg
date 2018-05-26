#!/bin/bash -e

YAML_FILES="ctypes.yaml ctypes_array.yaml ctypes_and_ctypes_array.yaml complex_type.yaml complex_and_ctype.yaml"

for y in ${YAML_FILES}; do
  ../genmsg.py ${y} --py-gen
  ./autotest.py
done
