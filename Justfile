
docker_repo := 'daanzu/kaldi-fork-active-grammar-manylinux'

_default:
	just --list

build-docker:
	cd building; docker build --file Dockerfile.manylinux --tag {{docker_repo}}:latest .
	@mkdir -p wheelhouse
	docker run --rm -e KAG_BRANCH=master -e WHEEL_PLAT=manylinux2010_x86_64 -v $(pwd):/io {{docker_repo}} bash /io/building/build-manylinux-wheel.sh
	# docker run --rm -e PLAT=manylinux2010_x86_64 -v .:/io {{docker_repo}} cp ../kaldi/tools/openfst/bin/{fstarcsort,fstcompile,fstinfo} ../kaldi/src/fstbin/fstaddselfloops ../kaldi/src/dragonfly/libkaldi-dragonfly.so ../kaldi/src/dragonflybin/compile-graph-agf /io/kaldi_active_grammar/exec/linux

# setup an editable development environment on linux
setup-linux-develop kaldi_dir:
	mkdir kaldi_active_grammar/exec/linux/
	ln -sr {{kaldi_dir}}/tools/openfst/bin/fstarcsort kaldi_active_grammar/exec/linux/
	ln -sr {{kaldi_dir}}/tools/openfst/bin/fstcompile kaldi_active_grammar/exec/linux/
	ln -sr {{kaldi_dir}}/tools/openfst/bin/fstinfo kaldi_active_grammar/exec/linux/
	ln -sr {{kaldi_dir}}/src/fstbin/fstaddselfloops kaldi_active_grammar/exec/linux/
	ln -sr {{kaldi_dir}}/src/dragonfly/libkaldi-dragonfly.so kaldi_active_grammar/exec/linux/
	ln -sr {{kaldi_dir}}/src/dragonflybin/compile-graph-agf kaldi_active_grammar/exec/linux/
