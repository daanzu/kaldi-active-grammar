#!/usr/bin/env bash

set -e -x

export CXXFLAGS="-O2 -g0 -ftree-vectorize"
# -g0: Request debugging information and also use level to specify how much information. The default level is 2.
#      Level 0 produces no debug information at all. Thus, -g0 negates -g.

# Execute all arguments
eval "$*"
