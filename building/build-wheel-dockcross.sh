#!/usr/bin/env bash

# This script builds a Python wheel for kaldi-active-grammar using dockcross,
# and is to be RUN WITHIN THE DOCKCROSS CONTAINER. It optionally installs Intel
# MKL if MKL_URL is provided, then builds the wheel and repairs it for the
# specified platform using auditwheel.
#
# Usage: ./build-wheel-dockcross.sh [--skip-native] <WHEEL_PLAT> <KALDI_BRANCH> [MKL_URL]
# - --skip-native: Skip the native build step
# - WHEEL_PLAT: The platform tag for the wheel (e.g., manylinux2014_x86_64)
# - KALDI_BRANCH: The Kaldi branch to use for building
# - MKL_URL: Optional URL to download and install Intel MKL

set -e -x

PYTHON_EXE=/opt/python/cp38-cp38/bin/python

# Parse optional arguments and filter them out
SKIP_NATIVE=false
ARGS=()
while [[ $# -gt 0 ]]; do
  case $1 in
    --skip-native)
      SKIP_NATIVE=true
      shift
      ;;
    *)
      ARGS+=("$1")
      shift
      ;;
  esac
done
# Set positional arguments from filtered array
set -- "${ARGS[@]}"

# Parse required arguments
WHEEL_PLAT=$1
KALDI_BRANCH=$2
MKL_URL=$3

if [ -z "$PYTHON_EXE" ] || [ -z "$WHEEL_PLAT" ] || [ -z "$KALDI_BRANCH" ]; then
    echo "ERROR: variable not set!"
    exit 1
fi

if [ -n "$MKL_URL" ]; then
    pushd _skbuild
    wget --no-verbose --no-clobber $MKL_URL
    mkdir -p /tmp/mkl
    MKL_FILE=$(basename $MKL_URL)
    tar zxf $MKL_FILE -C /tmp/mkl --strip-components=1
    sed -i.bak -e 's/ACCEPT_EULA=decline/ACCEPT_EULA=accept/g' -e 's/ARCH_SELECTED=ALL/ARCH_SELECTED=INTEL64/g' /tmp/mkl/silent.cfg
    sudo /tmp/mkl/install.sh --silent /tmp/mkl/silent.cfg
    rm -rf /tmp/mkl
    export INTEL_MKL_DIR="/opt/intel/mkl/"
    popd
fi

if [ "$SKIP_NATIVE" = true ]; then
    export KALDIAG_BUILD_SKIP_NATIVE=1
    # Patch the native binaries restored from cache to work with auditwheel repair below; final result should be idempotent
    patchelf --force-rpath --set-rpath "$(pwd)/kaldi_active_grammar.libs" kaldi_active_grammar/exec/linux/libkaldi-dragonfly.so
    readelf -d kaldi_active_grammar/exec/linux/libkaldi-dragonfly.so | egrep 'NEEDED|RUNPATH|RPATH'
    # ldd kaldi_active_grammar/exec/linux/libkaldi-dragonfly.so
    # LD_DEBUG=libs ldd kaldi_active_grammar/exec/linux/libkaldi-dragonfly.so
else
    # Clean in preparation for native build
    mkdir -p _skbuild
    rm -rf _skbuild/*/cmake-install/ _skbuild/*/setuptools/
    rm -rf kaldi_active_grammar/exec
fi

KALDI_BRANCH=$KALDI_BRANCH $PYTHON_EXE setup.py bdist_wheel

# ls -lR kaldi_active_grammar/exec/linux

mkdir -p wheelhouse
for whl in dist/*.whl; do
    unzip -l $whl
    auditwheel show $whl
    auditwheel repair $whl --plat $WHEEL_PLAT -w wheelhouse/
    # auditwheel -v repair $whl --plat $WHEEL_PLAT -w wheelhouse/
done
