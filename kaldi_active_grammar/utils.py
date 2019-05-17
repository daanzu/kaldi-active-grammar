#
# This file is part of kaldi-active-grammar.
# (c) Copyright 2019 by David Zurow
# Licensed under the AGPL-3.0, with exceptions; see LICENSE.txt file.
#

import logging, sys, time
import fnmatch, os
import hashlib, json
from contextlib import contextmanager

from . import _log, _name


########################################################################################################################

debug_timer_enabled = True
_debug_timer_stack = []

@contextmanager
def debug_timer(log, desc, enabled=True, independent=False):
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


########################################################################################################################

symbol_table_lookup_cache = dict()

def symbol_table_lookup(filename, input):
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

class FileCache(object):

    def __init__(self, filename, dependencies_dict=dict()):
        self.filename = filename
        try:
            self.load()
        except Exception as e:
            _log.warning("%s: failed to load cache from %r; initializing empty", self, filename)
            self.cache = dict()
        if (sorted(self.cache.get('dependencies_dict', dict()).keys()) != sorted(dependencies_dict.keys())
                or any(not self.contains(key, open(path, 'rb').read()) for key, path in dependencies_dict.items() if path and os.path.isfile(path))):
            _log.warning("%s: dependencies did not match cache from %r; initializing empty", self, filename)
            self.cache = dict(dependencies_dict=dependencies_dict)
            [self.add(key, open(path, 'rb').read()) for key, path in dependencies_dict.items() if path and os.path.isfile(path)]

    def load(self):
        with open(self.filename, 'r') as f:
            self.cache = json.load(f)

    def save(self):
        with open(self.filename, 'w') as f:
            json.dump(self.cache, f)

    def hash(self, data):
        return hashlib.md5(data).hexdigest()

    def add(self, filename, data):
        self.cache[filename] = self.hash(data)

    def contains(self, filename, data):
        return (filename in self.cache) and (self.cache[filename] == self.hash(data))

    def invalidate(self, filename=None):
        if filename is None:
            _log.info("%s: invalidating whole cache", self)
            self.cache.clear()
        elif filename in self.cache:
            _log.info("%s: invalidating cache entry for %r", self, filename)
            del self.cache[filename]

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
