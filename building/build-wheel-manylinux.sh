#!/usr/bin/env bash

set -e -x

PYTHON_EXE=/opt/python/cp38-cp38/bin/python

cd /opt
git clone --depth 1 --branch ${KAG_BRANCH} https://github.com/daanzu/kaldi-active-grammar kaldi-active-grammar
cd kaldi-active-grammar
${PYTHON_EXE} -m pip install setuptools wheel
mkdir -p kaldi_active_grammar/exec/linux
cp ../kaldi/tools/openfst/bin/{fstarcsort,fstcompile,fstinfo} ../kaldi/src/fstbin/fstaddselfloops ../kaldi/src/dragonfly/libkaldi-dragonfly.so ../kaldi/src/dragonflybin/compile-graph-agf kaldi_active_grammar/exec/linux
find kaldi_active_grammar/exec/linux/ -type f | xargs strip
env KALDIAG_SETUP_RAW=1 ${PYTHON_EXE} setup.py bdist_wheel
for whl in dist/*.whl; do auditwheel repair ${whl} --plat ${WHEEL_PLAT} -w /io/wheelhouse/; done
