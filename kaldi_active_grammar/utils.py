#
# This file is part of kaldi-active-grammar.
# (c) Copyright 2019 by David Zurow
# Licensed under the AGPL-3.0, with exceptions; see LICENSE.txt file.
#

import logging, sys, time
import fnmatch, os
import functools
import hashlib, json
from contextlib import contextmanager

from . import _log, _name


########################################################################################################################

debug_timer_enabled = True
_debug_timer_stack = []

@contextmanager
def debug_timer(log, desc, enabled=True, independent=False):
    """
    Contextmanager that outputs timing to ``log`` with ``desc``.
    :param independent: if True, tracks entire time spent inside context, rather than subtracting time within inner ``debug_timer`` instances
    """
    start_time = time.clock()
    if not independent: _debug_timer_stack.append(start_time)
    spent_time_func = lambda: time.clock() - start_time
    yield spent_time_func
    start_time_adjusted = _debug_timer_stack.pop() if not independent else 0
    if enabled:
        if debug_timer_enabled:
            log("%s %d ms" % (desc, (time.clock() - start_time_adjusted) * 1000))
        if _debug_timer_stack and not independent:
            _debug_timer_stack[-1] += spent_time_func()

class CodeTimer(object):
    def __init__(self, name=None):
        self.name = name
    def __enter__(self):
        self.start = time.clock()
    def __exit__(self, exc_type, exc_value, traceback):
        self.took = (time.clock() - self.start) * 1000.0
        logging.debug("code spent %s ms in block %s", self.took, self.name)


########################################################################################################################

if sys.platform.startswith('win'): platform = 'windows'
elif sys.platform.startswith('linux'): platform = 'linux'
elif sys.platform.startswith('darwin'): platform = 'macos'
else: raise KaldiError("unknown sys.platform")

exec_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'exec', platform)
library_extension = dict(windows='.dll', linux='.so', macos='.dylib')[platform]
subprocess_seperator = '^&' if platform == 'windows' else ';'

import ush

class ExternalProcess(object):

    shell = ush.Shell(raise_on_error=True)

    fstcompile = shell(os.path.join(exec_dir, 'fstcompile'))
    fstarcsort = shell(os.path.join(exec_dir, 'fstarcsort'))
    fstaddselfloops = shell(os.path.join(exec_dir, 'fstaddselfloops'))
    fstinfo = shell(os.path.join(exec_dir, 'fstinfo'))
    compile_graph = shell(os.path.join(exec_dir, 'compile-graph'))
    compile_graph_agf = shell(os.path.join(exec_dir, 'compile-graph-agf'))
    compile_graph_agf_debug = shell(os.path.join(exec_dir, 'compile-graph-agf-debug'))

    make_lexicon_fst = shell(['python', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'kaldi', 'make_lexicon_fst_py2.py')])

    @staticmethod
    def get_formatter(format_kwargs):
        return lambda *args: [arg.format(**format_kwargs) for arg in args]


########################################################################################################################

def lazy_readonly_property(func):
    # From https://stackoverflow.com/questions/3012421/python-memoising-deferred-lookup-property-decorator
    attr_name = '_lazy_' + func.__name__

    @property
    @functools.wraps(func)
    def _lazyprop(self):
        if not hasattr(self, attr_name):
            setattr(self, attr_name, func(self))
        return getattr(self, attr_name)

    return _lazyprop

class lazy_settable_property(object):
    '''
    meant to be used for lazy evaluation of an object attribute.
    property should represent non-mutable data, as it replaces itself.
    '''
    # From https://stackoverflow.com/questions/3012421/python-memoising-deferred-lookup-property-decorator

    def __init__(self, fget):
        self.fget = fget
        # copy the getter function's docstring and other attributes
        functools.update_wrapper(self, fget)

    def __get__(self, obj, cls):
        if obj is None:
            return self
        value = self.fget(obj)
        setattr(obj, self.fget.__name__, value)
        return value


########################################################################################################################

def touch(filename):
    with open(filename, 'a'):
        pass

symbol_table_lookup_cache = dict()

def symbol_table_lookup(filename, input):
    """
    Returns the RHS corresponding to LHS == ``input`` in symbol table in ``filename``.
    """
    cached = symbol_table_lookup_cache.get((filename, input))
    if cached is not None:
        return cached
    with open(filename) as f:
        for line in f:
            tokens = line.strip().split()
            if len(tokens) >= 2 and input == tokens[0]:
                try:
                    symbol_table_lookup_cache[(filename, input)] = int(tokens[1])
                    return int(tokens[1])
                except Exception as e:
                    symbol_table_lookup_cache[(filename, input)] = tokens[1]
                    return tokens[1]
        return None

def load_symbol_table(filename):
    with open(filename) as f:
        return [[int(token) if token.isdigit() else token for token in line.strip().split()] for line in f]

def find_file(directory, filename):
    matches = []
    for root, dirnames, filenames in os.walk(directory):
        for filename in fnmatch.filter(filenames, filename):
            matches.append(os.path.join(root, filename))
    if matches:
        matches.sort(key=len)
        _log.debug("%s: find_file found file %r", _name, matches[0])
        return matches[0]
    else:
        _log.debug("%s: find_file cannot find file %r in %r", _name, filename, directory)
        return None

def is_file_up_to_date(filename, *parent_filenames):
    if not os.path.exists(filename): return False
    for parent_filename in parent_filenames:
        if not os.path.exists(parent_filename): return False
        if os.path.getmtime(filename) < os.path.getmtime(parent_filename): return False
    return True

class FileCache(object):

    def __init__(self, cache_filename, dependencies_dict=None):
        """
        Stores mapping filepath -> hash of its contents/data, to detect when recalculaion is necessary.
        Also stores an entry ``dependencies_dict`` itself mapping filepath -> hash of its contents/data, for detecting changes in our dependencies.
        """

        self.cache_filename = cache_filename
        if dependencies_dict is None: dependencies_dict = dict()
        self.cache_is_new = False

        try:
            self.load()
        except Exception as e:
            _log.info("%s: failed to load cache from %r; initializing empty", self, cache_filename)
            self.cache = dict()
            self.cache_is_new = True

        if (
            # If list of dependencies has changed
            sorted(self.cache.get('dependencies_dict', dict()).keys()) != sorted(dependencies_dict.keys())
            or
            # If any of the dependencies files' contents (as stored in cache) has changed
            any(not self.is_current(path)
                for (name, path) in dependencies_dict.items()
                if path and os.path.isfile(path))
            ):
            # Then reset cache
            _log.info("%s: dependencies did not match cache from %r; initializing empty", self, cache_filename)
            self.cache = dict(dependencies_dict=dependencies_dict)
            for (name, path) in dependencies_dict.items():
                if path and os.path.isfile(path):
                    self.add(path)
            self.cache_is_new = True

    def load(self):
        with open(self.cache_filename, 'r') as f:
            self.cache = json.load(f)

    def save(self):
        with open(self.cache_filename, 'w') as f:
            json.dump(self.cache, f)

    def hash_data(self, data):
        return hashlib.md5(data).hexdigest()

    def add(self, filepath, data=None):
        if data is None:
            with open(filepath, 'rb') as f:
                data = f.read()
        self.cache[filepath] = self.hash_data(data)

    def contains(self, filepath, data):
        return (filepath in self.cache) and (self.cache[filepath] == self.hash_data(data))

    def is_current(self, filepath, data=None):
        """Returns bool whether filepath file exists and the cache contains the given data (or the file's current data if none given)."""
        if self.cache_is_new and filepath in self.cache.get('dependencies_dict', dict()).values():
            return False
        if not os.path.isfile(filepath):
            return False
        if data is None:
            with open(filepath, 'rb') as f:
                data = f.read()
        return self.contains(filepath, data)

    def invalidate(self, filepath=None):
        if filepath is None:
            _log.info("%s: invalidating whole cache", self)
            self.cache.clear()
        elif filepath in self.cache:
            _log.info("%s: invalidating cache entry for %r", self, filepath)
            del self.cache[filepath]
