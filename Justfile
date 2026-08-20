
set ignore-comments
set positional-arguments

docker_repo := 'daanzu/kaldi-fork-active-grammar-manylinux'
piper_voice := 'en_US-ryan-low'
kaldi_model_url := 'https://github.com/daanzu/kaldi-active-grammar/releases/download/v3.0.0/kaldi_model_daanzu_20211030-smalllm.zip'

_default:
	just --list
	just --summary


### BUILDING

# Build a local wheel using the specified Python interpreter.
build-linux python='python3':
	mkdir -p _skbuild
	rm -rf kaldi_active_grammar/exec
	rm -rf _skbuild/*/cmake-build/ _skbuild/*/cmake-install/ _skbuild/*/setuptools/
	# {{python}} -m pip install -r requirements-build.txt
	# MKL with INTEL_MKL_DIR=/opt/intel/mkl/
	{{python}} setup.py bdist_wheel

# Build and repair a manylinux wheel with the checked-in Dockcross helper.
build-dockcross *args='':
	building/dockcross-manylinux2010-x64 --args "-e KALDIAG_BUILD_VERSION -e KALDI_REVISION" bash building/build-wheel-dockcross.sh manylinux2010_x86_64 {{args}}

# Download and make executable the Dockcross helper for manylinux builds.
setup-dockcross:
	docker run --rm dockcross/manylinux2010-x64:20210127-72b83fc > building/dockcross-manylinux2010-x64 && chmod +x building/dockcross-manylinux2010-x64
	@# [ ! -e building/dockcross-manylinux2010-x64 ] && docker run --rm dockcross/manylinux2010-x64 > building/dockcross-manylinux2010-x64 && chmod +x building/dockcross-manylinux2010-x64 || true

# Install the Python package in editable mode while skipping native builds. Useful for active development.
pip-install-develop:
	KALDIAG_BUILD_SKIP_NATIVE=1 pip3 install --user -e .

# Show whether a separate Kaldi checkout matches the commit locked by this repository.
native-status kaldi_root_dir='../kaldi-fork-active-grammar':
	@expected="$(python3 building/native_revision.py)"; actual="$(git -C {{kaldi_root_dir}} rev-parse HEAD)"; echo "locked:   $expected"; echo "checkout: $actual"; if [ "$expected" = "$actual" ]; then echo "status:   matching"; else echo "status:   DIFFERENT"; fi; git -C {{kaldi_root_dir}} status --short --branch

# Require a separate Kaldi checkout to be clean and at the locked commit.
native-verify kaldi_root_dir='../kaldi-fork-active-grammar':
	python3 building/native_revision.py --verify-checkout {{kaldi_root_dir}} --require-clean

# Fetch and detach a clean separate Kaldi checkout at the locked commit. Refuses to discard local changes.
native-sync kaldi_root_dir='../kaldi-fork-active-grammar':
	@if ! git -C {{kaldi_root_dir}} rev-parse --git-dir >/dev/null 2>&1; then mkdir -p {{kaldi_root_dir}}; git -C {{kaldi_root_dir}} init; git -C {{kaldi_root_dir}} remote add origin https://github.com/daanzu/kaldi-fork-active-grammar.git; fi
	@test -z "$(git -C {{kaldi_root_dir}} status --porcelain)" || { echo "Native checkout is dirty; refusing to change it." >&2; exit 1; }
	revision="$(python3 building/native_revision.py)"; git -C {{kaldi_root_dir}} fetch --depth=1 origin "$revision"; git -C {{kaldi_root_dir}} checkout --detach "$revision"

# Record the current commit of a separate, clean Kaldi checkout as the matching native revision.
native-lock kaldi_root_dir='../kaldi-fork-active-grammar':
	@test -z "$(git -C {{kaldi_root_dir}} status --porcelain)" || { echo "Native checkout is dirty; commit it before updating the lock." >&2; exit 1; }
	git -C {{kaldi_root_dir}} rev-parse HEAD > kaldi-native-revision.txt
	python3 building/native_revision.py

# Configure a separate Kaldi fork checkout for local Linux development. This is a one-time setup (or rerun after changing configure options).
configure-linux-develop kaldi_root_dir='../kaldi-fork-active-grammar':
	cd {{kaldi_root_dir}}/tools && ./extras/install_openblas.sh && CXXFLAGS='-Wno-missing-template-keyword' make -j"$(nproc)"
	# cd {{kaldi_root_dir}}/tools && make -j"$(nproc)"
	cd {{kaldi_root_dir}}/tools/openfst && autoreconf
	cd {{kaldi_root_dir}}/src && CXXFLAGS='-O2 -Wno-template-id-cdtor' ./configure --shared --static-math --use-cuda=no --mathlib=OPENBLAS
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

# Manually trigger the GitHub Actions wheel-build workflow for a ref.
trigger-build ref='master':
	gh workflow run build.yml --ref {{ref}}


### TESTING

# Replace the local test Kaldi model with a copy of the specified model.
test-model model_dir:
	cd {{invocation_directory()}} && rm -rf kaldi_model kaldi_model.tmp && cp -rp {{model_dir}} kaldi_model

# Download the Piper voice and Kaldi model required by the test suite.
setup-tests:
	uv run --no-project --with-requirements requirements-test.txt -m piper.download_voices --debug --download-dir tests/ '{{piper_voice}}'
	cd tests && [ ! -e kaldi_model ] && curl -L -C - -o kaldi_model.zip '{{kaldi_model_url}}' && unzip -o kaldi_model.zip || true

# Create a reusable virtual environment for repeated local test runs.
setup-tests-venv:
	rm -rf .venv
	uv venv --no-project
	uv pip install --python .venv/bin/python -r requirements-test.txt -r requirements-editable.txt

# Run the long-term stress harness directly with full knob control (see --help). Supports JSON baselines, absolute performance limits, observe-only runs, and explicit partial runs.
stress *args='':
	if [ -x .venv/bin/python ]; then .venv/bin/python tests/stress/longterm.py "$@"; else uv run --no-project --with-requirements requirements-test.txt --with-requirements requirements-editable.txt tests/stress/longterm.py "$@"; fi

# Quick smoke run of the stress harness for both frameworks.
stress-smoke *args='':
	just stress --profile smoke --framework both "$@"

# Run the stress harness against a released wheel in an isolated environment, for cross-version baselines (AGF only; released rule ids force a uniform --lazy-fraction, so the compared run needs the same value; see TESTING.md). Args: version, then harness args.
stress-release version *args='':
	shift; uv run --no-project --isolated --with-requirements requirements-test.txt --with 'kaldi-active-grammar=={{version}}' tests/stress/longterm.py --framework agf-direct --lazy-fraction 1 "$@"

# Run the test suite with pytest. Args: --lf (only run last failed), -k "keyword" (match tests), --maxfail=1 (fail fast)
test *args='':
	if [ -x .venv/bin/python ]; then .venv/bin/python -m pytest "$@"; else uv run --no-project --with-requirements requirements-test.txt --with-requirements requirements-editable.txt -m pytest "$@"; fi

# [DEPRECATED] Retained for historical native-state/isolation diagnosis; use `just test`. Args: --fail-fast (stop after the first failed test process)
test-separately *args='':
	if [ -x .venv/bin/python ]; then .venv/bin/python tests/run_each_test_separately.py "$@"; else uv run --no-project --with-requirements requirements-test.txt --with-requirements requirements-editable.txt tests/run_each_test_separately.py "$@"; fi

# Test the built wheel from tests/ so the source tree cannot be imported accidentally. Args: --lf (only run last failed), -k "keyword" (match tests), --maxfail=1 (fail fast)
test-package *args='':
	uv run -v --no-project --isolated --with-requirements ../requirements-test.txt --with kaldi-active-grammar --find-links wheels/ --directory tests/ -m pytest "$@"

# [DEPRECATED] Retained for historical native-state/isolation diagnosis; use `just test-package`. Args: --fail-fast (stop after the first failed test process)
test-package-separately *args='':
	uv run -v --no-project --isolated --with-requirements ../requirements-test.txt --with kaldi-active-grammar --find-links wheels/ --directory tests/ run_each_test_separately.py "$@"
