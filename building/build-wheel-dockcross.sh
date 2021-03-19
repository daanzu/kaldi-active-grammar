#!/usr/bin/env bash

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
