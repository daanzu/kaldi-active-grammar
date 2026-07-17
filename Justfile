
set ignore-comments
set positional-arguments

docker_repo := 'daanzu/kaldi-fork-active-grammar-manylinux'
piper_voice := 'en_US-ryan-low'
kaldi_model_url := 'https://github.com/daanzu/kaldi-active-grammar/releases/download/v3.0.0/kaldi_model_daanzu_20211030-smalllm.zip'

_default:
	just --list
	just --summary


### BUILDING

build-linux python='python3':
	mkdir -p _skbuild
	rm -rf kaldi_active_grammar/exec
	rm -rf _skbuild/*/cmake-build/ _skbuild/*/cmake-install/ _skbuild/*/setuptools/
	# {{python}} -m pip install -r requirements-build.txt
	# MKL with INTEL_MKL_DIR=/opt/intel/mkl/
	{{python}} setup.py bdist_wheel

build-dockcross *args='':
	building/dockcross-manylinux2010-x64 bash building/build-wheel-dockcross.sh manylinux2010_x86_64 {{args}}

setup-dockcross:
	docker run --rm dockcross/manylinux2010-x64:20210127-72b83fc > building/dockcross-manylinux2010-x64 && chmod +x building/dockcross-manylinux2010-x64
	@# [ ! -e building/dockcross-manylinux2010-x64 ] && docker run --rm dockcross/manylinux2010-x64 > building/dockcross-manylinux2010-x64 && chmod +x building/dockcross-manylinux2010-x64 || true

pip-install-develop:
	KALDIAG_BUILD_SKIP_NATIVE=1 pip3 install --user -e .

# Configure a separate Kaldi fork checkout for local Linux development. This is a one-time setup (or rerun after changing configure options).
configure-linux-develop kaldi_root_dir='../kaldi-fork-active-grammar':
	cd {{kaldi_root_dir}}/tools && ./extras/install_openblas.sh && make -j"$(nproc)"
	# cd {{kaldi_root_dir}}/tools && make -j"$(nproc)"
	cd {{kaldi_root_dir}}/tools/openfst && autoreconf
	cd {{kaldi_root_dir}}/src && CXXFLAGS='-O2' ./configure --shared --static-math --use-cuda=no --mathlib=OPENBLAS
	# cd {{kaldi_root_dir}}/src && CXXFLAGS='-O0 -g3' ./configure --shared --static-math --use-cuda=no --mathlib=OPENBLAS --debug-level=2
	# cd {{kaldi_root_dir}}/src && CXXFLAGS=-O2 ./configure --mkl-root=/home/daanzu/intel/mkl/ --shared --static-math
	make -C {{kaldi_root_dir}}/src -j"$(nproc)" depend

# Rebuild the native library after C++ changes in a separately checked-out fork.
build-linux-develop kaldi_root_dir='../kaldi-fork-active-grammar':
	make -C {{kaldi_root_dir}}/src -j"$(nproc)" dragonfly

# Stage a separate Kaldi fork checkout for an editable Linux Python install. The links keep the repositories independent while Python loads the current native build directly.
setup-linux-develop kaldi_root_dir='../kaldi-fork-active-grammar':
	mkdir -p kaldi_active_grammar/exec/linux/
	ln -srf {{kaldi_root_dir}}/src/lib/libkaldi-dragonfly.so kaldi_active_grammar/exec/linux/

# Copy the DLL from a separate Windows fork whenever MSBuild writes it; useful when a junction is unavailable or an independent staged copy is wanted.
watch-windows-develop kaldi_root_dir='../kaldi-fork-active-grammar' config='Release':
	mkdir -p kaldi_active_grammar/exec/windows
	cp -f "{{kaldi_root_dir}}/kaldiwin_vs2022_MKL/kaldiwin/kaldi-dragonfly/x64/{{config}}/kaldi-dragonfly.dll" kaldi_active_grammar/exec/windows/
	watchexec --postpone --watch "{{kaldi_root_dir}}/kaldiwin_vs2022_MKL/kaldiwin/kaldi-dragonfly/x64/{{config}}" --filter 'kaldi-dragonfly.dll' --fs-events create,modify,rename --debounce 500ms --shell=none -- cp -f "{{kaldi_root_dir}}/kaldiwin_vs2022_MKL/kaldiwin/kaldi-dragonfly/x64/{{config}}/kaldi-dragonfly.dll" kaldi_active_grammar/exec/windows/

# Link the ignored Windows staging directory to a separate fork's MSBuild output through cmd.exe; no symlink privilege is needed and the link must not already exist.
setup-windows-develop kaldi_root_dir='../kaldi-fork-active-grammar' config='Release':
	mkdir -p kaldi_active_grammar/exec
	if test -e kaldi_active_grammar/exec/windows; then echo 'kaldi_active_grammar/exec/windows already exists; remove its staging directory or junction first.' >&2; exit 1; fi
	cmd //c mklink /J "$(cygpath -aw kaldi_active_grammar/exec/windows)" "$(cygpath -aw '{{kaldi_root_dir}}/kaldiwin_vs2022_MKL/kaldiwin/kaldi-dragonfly/x64/{{config}}')"

trigger-build ref='master':
	gh workflow run build.yml --ref {{ref}}


### TESTING

test-model model_dir:
	cd {{invocation_directory()}} && rm -rf kaldi_model kaldi_model.tmp && cp -rp {{model_dir}} kaldi_model

setup-tests:
	uv run --no-project --with-requirements requirements-test.txt -m piper.download_voices --debug --download-dir tests/ '{{piper_voice}}'
	cd tests && [ ! -e kaldi_model ] && curl -L -C - -o kaldi_model.zip '{{kaldi_model_url}}' && unzip -o kaldi_model.zip || true

# Common args: --lf (only run last failed) -k "keyword" (only run tests matching keyword or name)
test *args='':
    uv run --no-project --with-requirements requirements-test.txt --with-requirements requirements-editable.txt -m pytest "$@"

test-separately *args='':
	uv run --no-project --with-requirements requirements-test.txt --with-requirements requirements-editable.txt tests/run_each_test_separately.py "$@"

# Test package after building wheel into wheels/ directory. Runs tests from within tests/ directory to prevent importing kaldi_active_grammar from source tree
test-package *args='':
	uv run -v --no-project --isolated --with-requirements ../requirements-test.txt --with kaldi-active-grammar --find-links wheels/ --directory tests/ -m pytest "$@"

test-package-separately *args='':
	uv run -v --no-project --isolated --with-requirements ../requirements-test.txt --with kaldi-active-grammar --find-links wheels/ --directory tests/ run_each_test_separately.py "$@"
