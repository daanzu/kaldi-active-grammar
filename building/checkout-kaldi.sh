#!/usr/bin/env bash

# Create a minimal checkout of one exact Kaldi commit for ExternalProject.
# CMake's GIT_SHALLOW mode only accepts branch or tag names, not commit hashes.

set -euo pipefail

source_dir=$1
repository=$2
revision=$3

if [[ -z "$source_dir" || "$source_dir" == / ]]; then
    echo "Refusing unsafe Kaldi source directory: '$source_dir'" >&2
    exit 1
fi

rm -rf "$source_dir"
mkdir -p "$source_dir"
git -C "$source_dir" init
git -C "$source_dir" remote add origin "$repository"
git -C "$source_dir" fetch --depth=1 origin "$revision"
git -C "$source_dir" checkout --detach FETCH_HEAD

test "$(git -C "$source_dir" rev-parse HEAD)" = "$revision"
