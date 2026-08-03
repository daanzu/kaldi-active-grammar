
import re

import pytest


def test_laf_rejects_runtime_pronunciation_updates():
    from kaldi_active_grammar import Compiler, KaldiError

    compiler = Compiler.__new__(Compiler)
    compiler.decoding_framework = 'laf'

    with pytest.raises(KaldiError, match='LAF does not support adding words or pronunciations at runtime'):
        compiler.add_word('example')


def test_compiler_rejects_removed_native_fst_option():
    from kaldi_active_grammar import Compiler

    # The option is gone from the signature, so this fails before any model directory is opened.
    for value in (True, False):
        with pytest.raises(TypeError, match='native_fst'):
            Compiler(native_fst=value)


def test_compiler_rejects_removed_agf_indirect_framework():
    from kaldi_active_grammar import Compiler, KaldiError

    with pytest.raises(KaldiError, match="framework='agf-indirect' was removed"):
        Compiler(framework='agf-indirect')


def test_compiler_rejects_unknown_framework():
    from kaldi_active_grammar import Compiler, KaldiError

    with pytest.raises(KaldiError, match='Invalid Compiler framework'):
        Compiler(framework='not-a-framework')


def test_agf_graph_compilation_rejects_laf_framework():
    from kaldi_active_grammar import Compiler, KaldiError

    compiler = Compiler.__new__(Compiler)
    compiler._closed = False
    compiler.decoding_framework = 'laf'
    compiler._agf_compiler = None  # LAF does not construct one

    with pytest.raises(KaldiError, match="not available with framework='laf'"):
        compiler._compile_agf_graph(input_filename='dictation_G.fst')


def test_activity_ids_are_normalized_for_native_abi():
    from kaldi_active_grammar.wrapper import _prepare_grammars_activity
    from kaldi_active_grammar.ffi import _ffi

    activity_p, activity_size = _prepare_grammars_activity([7, 2, 7])
    assert activity_size == 2
    assert list(activity_p)[:activity_size] == [2, 7]

    # None means "keep current native activity": NULL pointer, size 0.
    none_p, none_size = _prepare_grammars_activity(None)
    assert none_size == 0
    assert none_p == _ffi.NULL

    # Empty means "disable all rules": non-NULL pointer distinct from None, size 0.
    empty_p, empty_size = _prepare_grammars_activity([])
    assert empty_size == 0
    assert empty_p != none_p

    # Booleans are rejected so the legacy positional mask ([True, ...]) fails loudly
    # instead of being misread as rule ID 1.
    with pytest.raises(TypeError):
        _prepare_grammars_activity([True])

    # Non-integral IDs are rejected.
    with pytest.raises(TypeError):
        _prepare_grammars_activity([1.5])

    # A non-iterable is rejected.
    with pytest.raises(TypeError):
        _prepare_grammars_activity(5)

    # Negative IDs are rejected.
    with pytest.raises(ValueError):
        _prepare_grammars_activity([-1])


def test_import_and_version():
    import kaldi_active_grammar as kag
    assert isinstance(kag.__version__, str)
    assert kag.__version__.strip() != ""

    version_pattern = r'^\d+\.\d+\.\d+(?:[-+].+)?$'
    assert re.match(version_pattern, kag.__version__), f"Version '{kag.__version__}' does not match semantic versioning format"
