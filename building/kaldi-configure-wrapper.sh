#!/usr/bin/env bash

# We use this wrapper script to set compiler and linker flags in the environment
# before calling kaldi configure, to avoid issues with setting environment
# variables in commands called from cmake.

set -e -x

export CXXFLAGS="-O3 -g0 -ftree-vectorize"
# -g0: Request debugging information and also use level to specify how much information. The default level is 2.
#      Level 0 produces no debug information at all. Thus, -g0 negates -g.

if [[ "$(uname -s)" == "Darwin" && "$(uname -m)" == "x86_64" ]]; then
  # Intel macOS wheel repair rewrites dylib load commands with longer paths;
  # reserve room for those changes when linking the native libraries.
  export LDFLAGS="${LDFLAGS:+$LDFLAGS }-Wl,-headerpad_max_install_names"
fi

# Execute all arguments
exec "$@"
