
docker_repo := 'daanzu/kaldi-fork-active-grammar-manylinux'

_default:
	just --list

build-docker:
	cd building; docker build --file Dockerfile.manylinux --tag {{docker_repo}}:latest .
	mkdir -p wheelhouse
	docker run --rm -e KAG_BRANCH=master -e WHEEL_PLAT=manylinux2010_x86_64 -v $(pwd):/io {{docker_repo}} bash /io/building/build-wheel-manylinux.sh
	# docker run --rm -e PLAT=manylinux2010_x86_64 -v .:/io {{docker_repo}} cp ../kaldi/tools/openfst/bin/{fstarcsort,fstcompile,fstinfo} ../kaldi/src/fstbin/fstaddselfloops ../kaldi/src/dragonfly/libkaldi-dragonfly.so ../kaldi/src/dragonflybin/compile-graph-agf /io/kaldi_active_grammar/exec/linux

build-linux python='python3':
	mkdir -p _skbuild
	rm -rf kaldi_active_grammar/exec
	rm -rf _skbuild/*/cmake-install/ _skbuild/*/setuptools/
	{{python}} setup.py bdist_wheel

build-dockcross:
	building/dockcross-manylinux2010-x64 bash building/build-wheel-dockcross.sh manylinux2010_x86_64

setup-dockcross:
	docker run --rm dockcross/manylinux2010-x64 > building/dockcross-manylinux2010-x64 && chmod +x building/dockcross-manylinux2010-x64
	@# [ ! -e building/dockcross-manylinux2010-x64 ] && docker run --rm dockcross/manylinux2010-x64 > building/dockcross-manylinux2010-x64 && chmod +x building/dockcross-manylinux2010-x64 || true

pip-install-develop:
	KALDIAG_SETUP_RAW=1 pip3 install --user -e .

# setup an editable development environment on linux
setup-linux-develop kaldi_root_dir:
	mkdir -p kaldi_active_grammar/exec/linux/
	ln -sr {{kaldi_root_dir}}/tools/openfst/bin/fstarcsort kaldi_active_grammar/exec/linux/
	ln -sr {{kaldi_root_dir}}/tools/openfst/bin/fstcompile kaldi_active_grammar/exec/linux/
	ln -sr {{kaldi_root_dir}}/tools/openfst/bin/fstinfo kaldi_active_grammar/exec/linux/
	ln -sr {{kaldi_root_dir}}/src/fstbin/fstaddselfloops kaldi_active_grammar/exec/linux/
	ln -sr {{kaldi_root_dir}}/src/dragonfly/libkaldi-dragonfly.so kaldi_active_grammar/exec/linux/
	ln -sr {{kaldi_root_dir}}/src/dragonflybin/compile-graph-agf kaldi_active_grammar/exec/linux/

test_model model_dir:
	cd {{invocation_directory()}} && rm -rf kaldi_model kaldi_model.tmp && cp -rp {{model_dir}} kaldi_model
