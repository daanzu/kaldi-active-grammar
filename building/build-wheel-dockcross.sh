#!/usr/bin/env bash

set -e -x

PYTHON_EXE=/opt/python/cp38-cp38/bin/python
MKL_URL="http://registrationcenter-download.intel.com/akdlm/irc_nas/tec/16533/l_mkl_2020.1.217.tgz"
MKL_FILE=$(basename $MKL_URL)
# MKL_DIR=${MKL_URL%.*}
WHEEL_PLAT=$1

if [ -z "$WHEEL_PLAT" ] || [ -z "$PYTHON_EXE" ]; then
    echo "ERROR: variable not set!"
    exit 1
fi

mkdir -p _skbuild
rm -rf _skbuild/*/cmake-install/ _skbuild/*/setuptools/
rm -rf kaldi_active_grammar/exec

pushd _skbuild
wget --no-verbose --no-clobber $MKL_URL
mkdir -p /tmp/mkl
tar zxf $MKL_FILE -C /tmp/mkl --strip-components=1
sed -i.bak -e 's/ACCEPT_EULA=decline/ACCEPT_EULA=accept/g' -e 's/ARCH_SELECTED=ALL/ARCH_SELECTED=INTEL64/g' /tmp/mkl/silent.cfg
sudo /tmp/mkl/install.sh --silent /tmp/mkl/silent.cfg
rm -rf /tmp/mkl
popd

# $PYTHON_EXE -m pip install --upgrade setuptools wheel scikit-build cmake ninja
$PYTHON_EXE setup.py bdist_wheel

mkdir -p wheelhouse
for whl in dist/*.whl; do auditwheel repair $whl --plat $WHEEL_PLAT -w wheelhouse/; done
