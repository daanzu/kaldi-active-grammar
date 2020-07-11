#!/usr/bin/env bash

set -e -x

export CXXFLAGS="-O2 -g0"

# Execute all arguments
eval "$*"
