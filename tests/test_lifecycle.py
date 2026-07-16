import ctypes
import gc
import sys
import weakref

import pytest

from kaldi_active_grammar import KaldiError
from kaldi_active_grammar import Compiler, disable_donation_message
from kaldi_active_grammar.ffi import FFIObject, _ffi


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

    destroy = close


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


def test_explicit_close_reports_destructor_failure_and_remains_idempotent():
    calls = []
    owner = NativeOwner(calls, destructor_result=False)

    with pytest.raises(KaldiError, match='test pointer'):
        owner.close()
    owner.close()

    assert calls == [42]


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
