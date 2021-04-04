
docker_repo := 'daanzu/kaldi-fork-active-grammar-manylinux'

_default:
	just --list
	just --summary

build-docker:
	cd building; docker build --file Dockerfile.manylinux --tag {{docker_repo}}:latest .
	mkdir -p wheelhouse
	docker run --rm -e KAG_BRANCH=master -e WHEEL_PLAT=manylinux2010_x86_64 -v $(pwd):/io {{docker_repo}} bash /io/building/build-wheel-manylinux.sh
	# docker run --rm -e PLAT=manylinux2010_x86_64 -v .:/io {{docker_repo}} cp ../kaldi/tools/openfst/bin/{fstarcsort,fstcompile,fstinfo} ../kaldi/src/fstbin/fstaddselfloops ../kaldi/src/dragonfly/libkaldi-dragonfly.so ../kaldi/src/dragonflybin/compile-graph-agf /io/kaldi_active_grammar/exec/linux

build-linux python='python3':
	mkdir -p _skbuild
	rm -rf kaldi_active_grammar/exec
	rm -rf _skbuild/*/cmake-build/ _skbuild/*/cmake-install/ _skbuild/*/setuptools/
	# {{python}} -m pip install -r requirements-build.txt
	# MKL with INTEL_MKL_DIR=/opt/intel/mkl/
	{{python}} setup.py bdist_wheel

build-dockcross kaldi_branch mkl_url="":
	building/dockcross-manylinux2010-x64 bash building/build-wheel-dockcross.sh manylinux2010_x86_64 {{kaldi_branch}} {{mkl_url}}

setup-dockcross:
	docker run --rm dockcross/manylinux2010-x64:20210127-72b83fc > building/dockcross-manylinux2010-x64 && chmod +x building/dockcross-manylinux2010-x64
	@# [ ! -e building/dockcross-manylinux2010-x64 ] && docker run --rm dockcross/manylinux2010-x64 > building/dockcross-manylinux2010-x64 && chmod +x building/dockcross-manylinux2010-x64 || true

pip-install-develop:
	KALDIAG_SETUP_RAW=1 pip3 install --user -e .

# Setup an editable development environment on linux
setup-linux-develop kaldi_root_dir:
	# Compile kaldi_root_dir with: env CXXFLAGS=-O2 ./configure --mkl-root=/home/daanzu/intel/mkl/ --shared --static-math
	mkdir -p kaldi_active_grammar/exec/linux/
	ln -sr {{kaldi_root_dir}}/tools/openfst/bin/fstarcsort kaldi_active_grammar/exec/linux/
	ln -sr {{kaldi_root_dir}}/tools/openfst/bin/fstcompile kaldi_active_grammar/exec/linux/
	ln -sr {{kaldi_root_dir}}/tools/openfst/bin/fstinfo kaldi_active_grammar/exec/linux/
	ln -sr {{kaldi_root_dir}}/src/fstbin/fstaddselfloops kaldi_active_grammar/exec/linux/
	ln -sr {{kaldi_root_dir}}/src/dragonfly/libkaldi-dragonfly.so kaldi_active_grammar/exec/linux/
	ln -sr {{kaldi_root_dir}}/src/dragonflybin/compile-graph-agf kaldi_active_grammar/exec/linux/

watch-windows-develop config='Release':
	bash -c "watchexec -v --no-ignore -w /mnt/c/Work/Speech/kaldi/kaldi-windows/kaldiwin_vs2019_MKL/x64/ cp /mnt/c/Work/Speech/kaldi/kaldi-windows-deps/openfst.2019/build_output/x64/{{config}}/bin/{fstarcsort,fstcompile,fstinfo}.exe /mnt/c/Work/Speech/kaldi/kaldi-windows/kaldiwin_vs2019_MKL/x64/{{config}}/{kaldi-dragonfly.dll,compile-graph-agf.exe,fstaddselfloops.exe} /mnt/c/Work/Speech/kaldi/kaldi-active-grammar/kaldi_active_grammar/exec/windows/"

test-model model_dir:
	cd {{invocation_directory()}} && rm -rf kaldi_model kaldi_model.tmp && cp -rp {{model_dir}} kaldi_model

trigger-build ref='master':
	gh api repos/:owner/:repo/actions/workflows/build.yml/dispatches -F ref={{ref}}
