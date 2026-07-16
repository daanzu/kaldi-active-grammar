#
# This file is part of kaldi-active-grammar.
# (c) Copyright 2019 by David Zurow
# Licensed under the AGPL-3.0; see LICENSE.txt file.
#

"""
FFI classes for Kaldi
"""

import logging, os, re

from cffi import FFI

from .utils import exec_dir, platform

_ffi = FFI()
_log = logging.getLogger('kaldi.ffi')
_library_binary_path = os.path.join(exec_dir, dict(windows='kaldi-dragonfly.dll', linux='libkaldi-dragonfly.so', macos='libkaldi-dragonfly.dylib')[platform])
_c_source_ignore_regex = re.compile(r'(\b(extern|DRAGONFLY_API)\b)|("C")|(//.*$)', re.MULTILINE)  # Pattern for extraneous stuff to be removed

def encode(text):
    """ For C interop: encode unicode text -> binary utf-8. """
    return text.encode('utf-8')
def decode(binary):
    """ For C interop: decode binary utf-8 -> unicode text. """
    return binary.decode('utf-8')

class FFIObject(object):

    def __init__(self):
        self.init_ffi()

    @staticmethod
    def _finalizer(destructor, description):
        """Build a finalizer without retaining the Python owner."""
        def finalize(pointer):
            try:
                if not destructor(pointer):
                    _log.error("Native destructor failed for %s", description)
            except Exception:
                # Exceptions from a garbage-collection callback cannot be usefully
                # propagated.  Explicit close() still reports destructor failures.
                _log.exception("Native destructor raised for %s", description)
        return finalize

    def _own_native(self, pointer, destructor, description):
        """Return *pointer* with its native destructor registered with CFFI."""
        if pointer == _ffi.NULL:
            return pointer
        return _ffi.gc(pointer, self._finalizer(destructor, description))

    def _release_native(self, attribute, destructor, description):
        """Synchronously release an owned pointer, once."""
        pointer = getattr(self, attribute, None)
        if pointer is None or pointer == _ffi.NULL:
            setattr(self, attribute, None)
            return

        # Clear the attribute first so re-entrant or repeated close calls are safe.
        setattr(self, attribute, None)
        _ffi.gc(pointer, None)
        if not destructor(pointer):
            from . import KaldiError
            raise KaldiError("Native destructor failed for %s" % description)

    @staticmethod
    def _require_native(pointer, description):
        if pointer is None or pointer == _ffi.NULL:
            from . import KaldiError
            raise KaldiError("Cannot use closed %s" % description)
        return pointer

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    @classmethod
    def init_ffi(cls):
        cls._lib = _ffi.init_once(cls._init_ffi, cls.__name__ + '._init_ffi')

    @classmethod
    def _init_ffi(cls):
        _ffi.cdef(_c_source_ignore_regex.sub(' ', cls._library_header_text))
        return _ffi.dlopen(_library_binary_path)
