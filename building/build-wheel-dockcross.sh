#!/usr/bin/env bash

# This script builds a Python wheel for kaldi-active-grammar using dockcross,
# and is to be RUN WITHIN THE DOCKCROSS CONTAINER. It optionally installs Intel
# MKL if MKL_URL is provided, then builds the wheel and repairs it for the
# specified platform using auditwheel.
#
# Usage: ./build-wheel-dockcross.sh <WHEEL_PLAT> <KALDI_BRANCH> [MKL_URL]
# - WHEEL_PLAT: The platform tag for the wheel (e.g., manylinux2014_x86_64)
# - KALDI_BRANCH: The Kaldi branch to use for building
# - MKL_URL: Optional URL to download and install Intel MKL

set -e -x

PYTHON_EXE=/opt/python/cp38-cp38/bin/python
WHEEL_PLAT=$1
KALDI_BRANCH=$2
MKL_URL=$3

if [ -z "$WHEEL_PLAT" ] || [ -z "$PYTHON_EXE" ]; then
    echo "ERROR: variable not set!"
    exit 1
fi

mkdir -p _skbuild
rm -rf _skbuild/*/cmake-install/ _skbuild/*/setuptools/
rm -rf kaldi_active_grammar/exec

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

# $PYTHON_EXE -m pip install --upgrade setuptools wheel scikit-build cmake ninja
KALDI_BRANCH=$KALDI_BRANCH $PYTHON_EXE setup.py bdist_wheel

mkdir -p wheelhouse
for whl in dist/*.whl; do auditwheel repair $whl --plat $WHEEL_PLAT -w wheelhouse/; done
