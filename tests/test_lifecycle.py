import ctypes
import gc
import sys
import weakref
from types import SimpleNamespace

import pytest

from kaldi_active_grammar import KaldiError
from kaldi_active_grammar import Compiler, KaldiRule, PlainDictationRecognizer, disable_donation_message
from kaldi_active_grammar.ffi import FFIObject, _ffi
from kaldi_active_grammar.wfst import NativeWFST
from kaldi_active_grammar.wrapper import (
    KaldiAgfCompiler,
    KaldiAgfNNet3Decoder,
    KaldiLafNNet3Decoder,
    KaldiPlainNNet3Decoder,
)


class NativeOwner(FFIObject):
    """Small test double exercising the real CFFI ownership helpers."""

    def __init__(self, calls, destructor_result=True):
        self.calls = calls

        def destructor(pointer):
            calls.append(pointer[0])
            return destructor_result

        self.destructor = destructor
        pointer = _ffi.new('int *', 42)
        self.pointer = self._own_native(pointer, destructor, 'test pointer')

    def close(self):
        self._release_native('pointer', self.destructor, 'test pointer')


class RecordingNativeLibrary(object):
    """Minimal native-library double for wrapper lifecycle tests."""

    def __init__(self):
        self.destructor_calls = []
        self.operation_calls = []

    def _destruct(self, pointer):
        self.destructor_calls.append(pointer)
        return True

    nnet3_agf__destruct = _destruct
    nnet3_laf__destruct = _destruct
    nnet3_agf__destruct_compiler = _destruct

    def __getattr__(self, name):
        if name.startswith('nnet3_'):
            def operation(*args):
                self.operation_calls.append((name, args))
                if 'add_grammar_fst' in name:
                    return args[1]
                return True
            return operation
        raise AttributeError(name)


def make_decoder(decoder_type):
    decoder = object.__new__(decoder_type)
    decoder._lib = RecordingNativeLibrary()
    decoder._model = _ffi.cast('void *', 1)
    decoder.num_grammars = 0
    return decoder


def make_wfst(native=True, compiled=True):
    fst = object.__new__(NativeWFST)
    fst.native_obj = _ffi.cast('void *', 2) if native else None
    fst._compiled_native_obj = _ffi.cast('void *', 3) if compiled else None
    return fst


def test_close_releases_once_and_rejects_use_after_close():
    calls = []
    owner = NativeOwner(calls)

    owner.close()
    owner.close()

    assert calls == [42]
    with pytest.raises(KaldiError, match='closed test pointer'):
        owner._require_native(owner.pointer, 'test pointer')


def test_garbage_collection_releases_native_pointer_in_cycle():
    calls = []
    owner = NativeOwner(calls)
    owner.cycle = owner
    owner_reference = weakref.ref(owner)

    del owner
    gc.collect()

    assert owner_reference() is None
    assert calls == [42]


def test_context_manager_closes_on_exception():
    calls = []

    with pytest.raises(RuntimeError):
        with NativeOwner(calls):
            raise RuntimeError('test error')

    assert calls == [42]


def test_public_lifecycle_uses_close_only():
    resource_types = (
        Compiler,
        KaldiRule,
        PlainDictationRecognizer,
        KaldiPlainNNet3Decoder,
        KaldiAgfNNet3Decoder,
        KaldiLafNNet3Decoder,
        KaldiAgfCompiler,
        NativeWFST,
    )
    for resource_type in resource_types:
        assert hasattr(resource_type, 'close')
        assert hasattr(resource_type, '__enter__')
        assert hasattr(resource_type, '__exit__')
        assert not hasattr(resource_type, 'destroy')
        assert not hasattr(resource_type, 'destruct')


def test_explicit_close_reports_destructor_failure_and_remains_idempotent():
    calls = []
    owner = NativeOwner(calls, destructor_result=False)

    with pytest.raises(KaldiError, match='test pointer'):
        owner.close()
    owner.close()

    assert calls == [42]


@pytest.mark.parametrize('decoder_type', [KaldiAgfNNet3Decoder, KaldiLafNNet3Decoder])
def test_active_decoder_close_is_idempotent_for_both_backends(decoder_type):
    decoder = make_decoder(decoder_type)
    decoder._model = decoder._own_native(
        decoder._model,
        (decoder._lib.nnet3_agf__destruct if decoder_type is KaldiAgfNNet3Decoder
         else decoder._lib.nnet3_laf__destruct),
        'test decoder',
        )

    decoder.close()
    decoder.close()

    assert len(decoder._lib.destructor_calls) == 1
    with pytest.raises(KaldiError, match='closed nnet3 decoder'):
        decoder.remove_grammar_fst(0)


@pytest.mark.parametrize('decoder_type', [KaldiAgfNNet3Decoder, KaldiLafNNet3Decoder])
def test_active_decoder_context_manager_closes_both_backends(decoder_type):
    decoder = make_decoder(decoder_type)
    destructor = (decoder._lib.nnet3_agf__destruct if decoder_type is KaldiAgfNNet3Decoder
        else decoder._lib.nnet3_laf__destruct)
    decoder._model = decoder._own_native(decoder._model, destructor, 'test decoder')

    with decoder as entered:
        assert entered is decoder

    assert len(decoder._lib.destructor_calls) == 1


@pytest.mark.parametrize('decoder_type', [KaldiAgfNNet3Decoder, KaldiLafNNet3Decoder])
def test_active_decoder_finalizer_closes_both_backends(decoder_type):
    decoder = make_decoder(decoder_type)
    library = decoder._lib
    destructor = (library.nnet3_agf__destruct if decoder_type is KaldiAgfNNet3Decoder
        else library.nnet3_laf__destruct)
    decoder._model = decoder._own_native(decoder._model, destructor, 'test decoder')
    decoder_reference = weakref.ref(decoder)

    del decoder
    gc.collect()

    assert decoder_reference() is None
    assert len(library.destructor_calls) == 1


@pytest.mark.parametrize('decoder_type', [KaldiAgfNNet3Decoder, KaldiLafNNet3Decoder])
def test_active_decoders_reject_closed_models_before_native_calls(decoder_type):
    decoder = make_decoder(decoder_type)
    decoder._model = None
    grammar_fst = make_wfst()

    with pytest.raises(KaldiError, match='closed nnet3 decoder'):
        decoder.add_grammar_fst(0, grammar_fst)

    assert decoder._lib.operation_calls == []


def test_agf_rejects_missing_compiled_fst_before_native_call():
    decoder = make_decoder(KaldiAgfNNet3Decoder)
    grammar_fst = make_wfst(compiled=False)

    with pytest.raises(KaldiError, match='closed compiled native WFST'):
        decoder.add_grammar_fst(0, grammar_fst)
    with pytest.raises(KaldiError, match='closed compiled native WFST'):
        decoder.reload_grammar_fst(0, grammar_fst)

    assert decoder._lib.operation_calls == []


def test_laf_and_mimic_reject_closed_native_fst_before_native_call():
    decoder = make_decoder(KaldiLafNNet3Decoder)
    grammar_fst = make_wfst(native=False)

    with pytest.raises(KaldiError, match='closed native WFST'):
        decoder.add_grammar_fst(0, grammar_fst)
    with pytest.raises(KaldiError, match='closed native WFST'):
        decoder.reload_grammar_fst(0, grammar_fst)
    with pytest.raises(KaldiError, match='closed native WFST'):
        decoder.set_mimic_grammar_fst(0, grammar_fst)

    assert decoder._lib.operation_calls == []


def test_agf_compiler_rejects_closed_compiler_and_wfst():
    compiler = object.__new__(KaldiAgfCompiler)
    compiler._lib = RecordingNativeLibrary()
    compiler._compiler = _ffi.cast('void *', 1)

    with pytest.raises(KaldiError, match='closed native WFST'):
        compiler.compile_graph({}, grammar_fst=make_wfst(native=False))

    compiler._compiler = None
    with pytest.raises(KaldiError, match='closed AGF compiler'):
        compiler.compile_graph({}, grammar_fst=make_wfst())

    assert compiler._lib.operation_calls == []


def test_agf_compiler_rejects_uninitialized_compiler():
    compiler = object.__new__(KaldiAgfCompiler)
    compiler._lib = RecordingNativeLibrary()

    with pytest.raises(KaldiError, match='closed AGF compiler'):
        compiler.compile_graph({}, grammar_fst=make_wfst())

    assert compiler._lib.operation_calls == []


def test_rule_filepath_rejects_missing_temporary_directory():
    rule = object.__new__(KaldiRule)
    rule.compiler = SimpleNamespace(tmp_dir=None)
    rule.fst = SimpleNamespace(filename='rule.fst')
    rule.closed = False

    with pytest.raises(KaldiError, match='temporary directory'):
        rule.filepath


def make_closable_rule(compiler, rule_id=-1):
    rule = object.__new__(KaldiRule)
    rule.compiler = compiler
    rule.id = rule_id
    rule.loaded = False
    rule.closed = False
    rule.fst = SimpleNamespace(native=False)
    return rule


def assert_closed_rule_accessors_raise(rule):
    for accessor in ('fst_cache', 'decoder', 'pending_compile', 'pending_load', 'filepath'):
        with pytest.raises(KaldiError, match='Cannot use a KaldiRule after calling close\\(\\)'):
            getattr(rule, accessor)


def test_rule_close_rejects_post_close_accessor_access():
    compiler = SimpleNamespace(
        decoder=None,
        compile_queue=set(),
        compile_duplicate_filename_queue=set(),
        load_queue=set(),
        )
    rule = make_closable_rule(compiler)

    rule.close()

    assert_closed_rule_accessors_raise(rule)


def test_rule_close_skips_unload_when_decoder_is_gone():
    compiler = SimpleNamespace(
        decoder=None,
        compile_queue=set(),
        compile_duplicate_filename_queue=set(),
        load_queue=set(),
        )
    rule = make_closable_rule(compiler)
    rule.loaded = True

    rule.close()

    assert rule.closed


def test_rule_context_manager_closes_rule():
    compiler = SimpleNamespace(
        decoder=None,
        compile_queue=set(),
        compile_duplicate_filename_queue=set(),
        load_queue=set(),
        )
    rule = make_closable_rule(compiler)

    with rule as entered:
        assert entered is rule

    assert rule.closed
    assert_closed_rule_accessors_raise(rule)


def test_compiler_close_rejects_post_close_accessor_access():
    compiler = object.__new__(Compiler)
    compiler._closed = False
    compiler.decoder = None
    compiler._agf_compiler = None
    compiler.kaldi_rule_by_id_dict = {}
    compiler._all_rules = weakref.WeakSet()
    compiler.compile_queue = set()
    compiler.compile_duplicate_filename_queue = set()
    compiler.load_queue = set()
    rule = make_closable_rule(compiler)
    compiler._all_rules.add(rule)
    compiler.kaldi_rule_by_id_dict[rule.id] = rule

    compiler.close()

    assert_closed_rule_accessors_raise(rule)


def test_compiler_close_closes_nonterm_rule_native_fst(change_to_test_dir):
    disable_donation_message()
    compiler = Compiler()
    rule = KaldiRule(compiler, 'top', nonterm=False, exported=False)
    native_fst = rule.fst
    assert isinstance(native_fst, NativeWFST)

    compiler.close()

    assert rule.closed
    assert native_fst.native_obj is None


def test_native_wfst_pointer_accessors_reject_closed_objects():
    fst = make_wfst(native=False, compiled=False)

    with pytest.raises(KaldiError, match='closed native WFST'):
        fst._get_native_obj()
    with pytest.raises(KaldiError, match='closed compiled native WFST'):
        fst.compiled_native_obj
    with pytest.raises(KaldiError, match='Cannot assign closed compiled native WFST'):
        fst.compiled_native_obj = _ffi.NULL


@pytest.mark.skipif(not sys.platform.startswith('linux'), reason='uses Linux RSS reporting')
def test_repeated_native_compiler_lifecycles_reach_memory_plateau(change_to_test_dir):
    """Catch large native allocations retained once per Compiler instance."""
    disable_donation_message()

    def current_rss_kib():
        with open('/proc/self/status') as status:
            line = next(line for line in status if line.startswith('VmRSS:'))
        return int(line.split()[1])

    closed_rss = []
    for _ in range(3):
        with Compiler():
            pass
        gc.collect()
        ctypes.CDLL(None).malloc_trim(0)
        closed_rss.append(current_rss_kib())

    # Allow normal allocator/library noise, but not the former ~118 MiB leak
    # on every construction.  Ignore the first cycle's one-time initialization.
    assert max(closed_rss[1:]) - min(closed_rss[1:]) < 64 * 1024
