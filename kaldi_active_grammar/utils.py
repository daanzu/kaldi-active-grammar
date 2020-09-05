#
# This file is part of kaldi-active-grammar.
# (c) Copyright 2019 by David Zurow
# Licensed under the AGPL-3.0; see LICENSE.txt file.
#

import logging, sys, time
import fnmatch, os
import functools
import hashlib, json
import threading
from contextlib import contextmanager
from io import open

import six
from six import PY2, binary_type, text_type, print_

from . import _log, _name, __version__


########################################################################################################################

_donation_message_enabled = True
_donation_message = ("Kaldi-Active-Grammar v%s: \n"
    "    If this free, open source engine is valuable to you, please consider donating \n"
    "    https://github.com/daanzu/kaldi-active-grammar \n"
    "    Disable message by calling `kaldi_active_grammar.disable_donation_message()`") % __version__

def show_donation_message():
    if _donation_message_enabled:
        print_(_donation_message)
        disable_donation_message()

def disable_donation_message():
    global _donation_message_enabled
    _donation_message_enabled = False


########################################################################################################################

debug_timer_enabled = True

class ThreadLocalData(threading.local):
    def __init__(self):
        self._debug_timer_stack = []
thread_local_data = ThreadLocalData()

@contextmanager
def debug_timer(log, desc, enabled=True, independent=False):
    """
    Contextmanager that outputs timing to ``log`` with ``desc``.
    :param independent: if True, tracks entire time spent inside context, rather than subtracting time within inner ``debug_timer`` instances
    """
    _debug_timer_stack = thread_local_data._debug_timer_stack
    start_time = time.time()
    if not independent: _debug_timer_stack.append(start_time)
    spent_time_func = lambda: time.time() - start_time
    yield spent_time_func
    if not independent: start_time_adjusted = _debug_timer_stack.pop()
    else: start_time_adjusted = 0
    if enabled:
        if debug_timer_enabled:
            log("%s %d ms" % (desc, (time.time() - start_time_adjusted) * 1000))
        if _debug_timer_stack and not independent:
            _debug_timer_stack[-1] += spent_time_func()


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
    # compile_graph = shell(os.path.join(exec_dir, 'compile-graph'))
    compile_graph_agf = shell(os.path.join(exec_dir, 'compile-graph-agf'))
    # compile_graph_agf_debug = shell(os.path.join(exec_dir, 'compile-graph-agf-debug'))

    make_lexicon_fst = shell([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'kaldi', 'make_lexicon_fst%s.py' % ('_py2' if PY2 else ''))])

    @staticmethod
    def get_formatter(format_kwargs):
        return lambda *args: [arg.format(**format_kwargs) for arg in args]

    @staticmethod
    def get_debug_stderr_kwargs(log):
        return (dict() if log.isEnabledFor(logging.DEBUG) else dict(stderr=six.BytesIO()))

    @staticmethod
    def execute_command_safely(commands, log):
        """ Executes given `ush` command, redirecting stderr appropriately: either logging, or storing to output upon error. """
        stderr = six.BytesIO()
        for command in commands.commands:
            command.opts['stderr'] = stderr
        try:
            result = commands()
        except Exception as e:
            log.error("Error running command. Printing stderr as follows...\n%s", stderr.getvalue().decode('utf-8'))
            raise e
        return result


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

def touch_file(filename):
    with open(filename, 'ab'):
        os.utime(filename, None)  # Update timestamps

def clear_file(filename):
    with open(filename, 'wb'):
        pass

symbol_table_lookup_cache = dict()

def symbol_table_lookup(filename, input):
    """
    Returns the RHS corresponding to LHS == ``input`` in symbol table in ``filename``.
    """
    cached = symbol_table_lookup_cache.get((filename, input))
    if cached is not None:
        return cached
    with open(filename, 'r', encoding='utf-8') as f:
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
    with open(filename, 'r', encoding='utf-8') as f:
        return [[int(token) if token.isdigit() else token for token in line.strip().split()] for line in f]

def find_file(directory, filename, required=False, default=False):
    matches = []
    for root, dirnames, filenames in os.walk(directory):
        for filename in fnmatch.filter(filenames, filename):
            matches.append(os.path.join(root, filename))
    if matches:
        matches.sort(key=len)
        _log.debug("%s: find_file found file %r", _name, matches[0])
        return matches[0]
    else:
        _log.debug("%s: find_file cannot find file %r in %r (or subdirectories)", _name, filename, directory)
        if required:
            raise IOError("cannot find file %r in %r" % (filename, directory))
        if default == True:
            return os.path.join(directory, filename)
        return None

def is_file_up_to_date(filename, *parent_filenames):
    if not os.path.exists(filename): return False
    for parent_filename in parent_filenames:
        if not os.path.exists(parent_filename): return False
        if os.path.getmtime(filename) < os.path.getmtime(parent_filename): return False
    return True


########################################################################################################################

class FSTFileCache(object):

    def __init__(self, cache_filename, dependencies_dict=None, invalidate=False):
        """
        Stores mapping filename -> hash of its contents/data, to detect when recalculaion is necessary. Assumes file is in model_dir.
        FST files are a special case: filename -> hash of its dependencies' hashes, since filename itself is a hash of its text source. Assumes file is in tmp_dir.
        Also stores an entry ``dependencies_list`` listing filenames of all dependencies.
        If ``invalidate``, then initialize a fresh cache.
        """

        self.cache_filename = cache_filename
        if dependencies_dict is None: dependencies_dict = dict()
        self.dependencies_dict = dependencies_dict
        self.lock = threading.Lock()

        try:
            self._load()
        except Exception as e:
            _log.info("%s: failed to load cache from %r", self, cache_filename)
            self.cache = None

        must_reset_cache = False
        if invalidate:
            _log.debug("%s: forced invalidate", self)
            must_reset_cache = True
        elif self.cache is None:
            _log.debug("%s: could not load cache", self)
            must_reset_cache = True
        elif self.cache.get('version') != __version__:
            _log.debug("%s: version changed", self)
            must_reset_cache = True
        elif sorted(self.cache.get('dependencies_list', list())) != sorted(dependencies_dict.keys()):
            _log.debug("%s: list of dependencies has changed", self)
            must_reset_cache = True
        elif any(not self.file_is_current(path)
                for (name, path) in dependencies_dict.items()
                if path and os.path.isfile(path)):
            _log.debug("%s: any of the dependencies files' contents (as stored in cache) has changed", self)
            must_reset_cache = True

        if must_reset_cache:
            # Then reset cache
            _log.info("%s: version or dependencies did not match cache from %r; initializing empty", self, cache_filename)
            self.cache = dict({ 'version': text_type(__version__) })
            self.cache_is_new = True
            self.update_dependencies()
            self.save()

    def _load(self):
        with open(self.cache_filename, 'r', encoding='utf-8') as f:
            self.cache = json.load(f)
        self.cache_is_new = False
        self.dirty = False

    def save(self):
        with open(self.cache_filename, 'w', encoding='utf-8') as f:
            # https://stackoverflow.com/a/14870531
            f.write(json.dumps(self.cache, ensure_ascii=False))
        self.dirty = False

    def update_dependencies(self):
        dependencies_dict = self.dependencies_dict
        for (name, path) in dependencies_dict.items():
            if path and os.path.isfile(path):
                self.add_file(path)
        self.cache['dependencies_list'] = sorted(dependencies_dict.keys())  # list
        self.cache['dependencies_hash'] = self.hash_data([self.cache.get(path) for (key, path) in sorted(dependencies_dict.items())])

    def invalidate(self, filename=None):
        if filename is None:
            _log.info("%s: invalidating all file entries in cache", self)
            # Does not invalidate dependencies!
            self.cache = { key: self.cache[key]
                for key in ['version', 'dependencies_list', 'dependencies_hash'] + self.cache['dependencies_list']
                if key in self.cache }
        elif filename in self.cache:
            _log.info("%s: invalidating cache entry for %r", self, filename)
            del self.cache[filename]
            self.dirty = True

    def hash_data(self, data):
        if not isinstance(data, binary_type):
            if not isinstance(data, text_type):
                data = text_type(data)
            data = data.encode('utf-8')
        return text_type(hashlib.sha1(data).hexdigest())

    def add_file(self, filepath, data=None):
        if data is None:
            with open(filepath, 'rb') as f:
                data = f.read()
        filename = os.path.basename(filepath)
        self.cache[filename] = self.hash_data(data)
        self.dirty = True

    def add_fst(self, filepath):
        filename = os.path.basename(filepath)
        self.cache[filename] = self.cache['dependencies_hash']
        self.dirty = True

    def contains(self, filename, data):
        return (filename in self.cache) and (self.cache[filename] == self.hash_data(data))

    def file_is_current(self, filepath, data=None):
        """Returns bool whether generic filepath file exists and the cache contains the given data (or the file's current data if none given)."""
        filename = os.path.basename(filepath)
        if self.cache_is_new and filename in self.cache.get('dependencies_list', list()):
            return False
        if not os.path.isfile(filepath):
            return False
        if data is None:
            with open(filepath, 'rb') as f:
                data = f.read()
        return self.contains(filename, data)

    def fst_is_current(self, filepath):
        """Returns bool whether FST file for fst_text in directory path exists and matches current dependencies."""
        filename = os.path.basename(filepath)
        return (filename in self.cache) and (self.cache[filename] == self.cache['dependencies_hash']) and os.path.isfile(filepath)

    def get_fst_filename(self, fst_text):
        hash = self.hash_data(fst_text)
        return hash + '.fst'
