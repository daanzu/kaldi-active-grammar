#
# This file is part of kaldi-active-grammar.
# (c) Copyright 2019 by David Zurow
# Licensed under the AGPL-3.0; see LICENSE.txt file.
#

"""
FFI classes for Kaldi
"""

import os, re

from cffi import FFI

from .utils import exec_dir, platform

_ffi = FFI()
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

    @classmethod
    def init_ffi(cls):
        cls._lib = _ffi.init_once(cls._init_ffi, cls.__name__ + '._init_ffi')

    @classmethod
    def _init_ffi(cls):
        _ffi.cdef(_c_source_ignore_regex.sub(' ', cls._library_header_text))
        return _ffi.dlopen(_library_binary_path)
