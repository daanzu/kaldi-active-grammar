#
# This file is part of kaldi-active-grammar.
# (c) Copyright 2019 by David Zurow
# Licensed under the AGPL-3.0; see LICENSE.txt file.
#

import logging, sys, time
import fnmatch, glob, os
import functools
import hashlib, json
import stat
import tempfile
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

if not PY2:
    def clock():
        return time.perf_counter()
else:
    def clock():
        return time.clock()


########################################################################################################################

if sys.platform.startswith('win'): platform = 'windows'
elif sys.platform.startswith('linux'): platform = 'linux'
elif sys.platform.startswith('darwin'): platform = 'macos'
else: raise KaldiError("unknown sys.platform")

exec_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'exec', platform)

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
    def get_dict_formatter(format_kwargs):
        return lambda **kwargs: { key: value.format(**format_kwargs) for (key, value) in kwargs.items() }
    @staticmethod
    def get_list_formatter(format_kwargs):
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
        _log.log(8, "%s: find_file found file %r", _name, matches[0])
        return matches[0]
    else:
        _log.log(8, "%s: find_file cannot find file %r in %r (or subdirectories)", _name, filename, directory)
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

    SCHEMA_VERSION = 2
    HASH_BLOCK_SIZE = 1024 * 1024

    def __init__(self, cache_filename, tmp_dir=None, dependencies_dict=None,
            invalidate=False, strict_content_validation=False):
        """
        Stores dependency content hashes and metadata to detect when recalculation
        is necessary. Dependency identities are paths relative to the cache
        directory whenever possible, never basenames.

        ``entries`` contains the compatibility API's generic file entries.
        Dependency records live separately in ``records`` so a generic entry
        cannot collide with a dependency in another directory.

        Normal validation trusts a matching size and ``mtime_ns``. A replacement
        that preserves both values is outside that mode's guarantee; set
        ``strict_content_validation`` to hash every dependency instead.

        FST files are a special case: they aren't stored in the cache object, because their filename is itself a hash of its content mixed with a hash of its dependencies.
        If ``invalidate``, then initialize a fresh cache.
        """

        self.cache_filename = cache_filename
        self.cache_dir = self._canonical_path(os.path.dirname(os.path.abspath(cache_filename)) or os.curdir)
        self.tmp_dir = tmp_dir
        if dependencies_dict is None: dependencies_dict = dict()
        self.dependencies_dict = dependencies_dict
        self.strict_content_validation = bool(strict_content_validation)
        self.lock = threading.Lock()
        self._dependency_specs = self._make_dependency_specs()
        self._initial_validation = dict()

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
        elif self.cache.get('schema_version') != self.SCHEMA_VERSION:
            _log.debug("%s: cache schema changed or is legacy", self)
            must_reset_cache = True
        elif self.cache.get('version') != __version__:
            _log.debug("%s: version changed", self)
            must_reset_cache = True
        elif self._dependency_ids() != self._expected_dependency_ids():
            _log.debug("%s: list of dependencies has changed", self)
            must_reset_cache = True
        elif self._stored_dependencies_hash() != self._compute_dependencies_hash(
                self.cache.get('dependency_ids', []), self.cache.get('records', {})):
            _log.debug("%s: stored dependency hash is inconsistent", self)
            must_reset_cache = True
        elif not self._validate_dependencies():
            _log.debug("%s: any of the dependencies files' contents (as stored in cache) has changed", self)
            must_reset_cache = True

        if must_reset_cache:
            # Then reset cache
            _log.info("%s: version or dependencies did not match cache from %r; initializing empty", self, cache_filename)
            self.cache = self._empty_cache()
            self.cache_is_new = True
            self.update_dependencies()
            self.save()
        elif self.dirty:
            # A valid content digest with changed metadata is still current, but
            # persist the refreshed metadata for the next stat-only startup.
            self.save()

    def _load(self):
        with open(self.cache_filename, 'r', encoding='utf-8') as f:
            self.cache = json.load(f)
        self.cache_is_new = False
        self.dirty = False

    @staticmethod
    def _canonical_path(filepath):
        """Return the runtime identity used for lookup and deduplication."""
        return os.path.normcase(os.path.realpath(os.path.abspath(filepath)))

    def _persisted_identity(self, filepath):
        """Return a stable identity relative to the cache directory."""
        canonical = self._canonical_path(filepath)
        relative = os.path.relpath(canonical, self.cache_dir)
        parent = os.pardir
        if relative == parent or relative.startswith(parent + os.sep):
            identity = canonical
        else:
            identity = relative
        identity = os.path.normcase(identity)
        identity = identity.replace(os.sep, '/')
        if os.altsep:
            identity = identity.replace(os.altsep, '/')
        return identity

    def _make_dependency_specs(self):
        """Build one dependency spec per physical runtime path."""
        specs = []
        seen_runtime_paths = set()
        for name, filepath in sorted(self.dependencies_dict.items(), key=lambda item: text_type(item[0])):
            if filepath is None:
                # None is an explicitly absent optional dependency, not a path.
                continue
            runtime_path = self._canonical_path(filepath)
            if runtime_path in seen_runtime_paths:
                continue
            seen_runtime_paths.add(runtime_path)
            specs.append({
                'name': text_type(name),
                'path': filepath,
                'runtime_path': runtime_path,
                'identity': self._persisted_identity(filepath),
            })
        return specs

    def _expected_dependency_ids(self):
        return sorted(set(spec['identity'] for spec in self._dependency_specs))

    def _dependency_ids(self):
        return sorted(set(self.cache.get('dependency_ids', [])))

    def _stored_dependencies_hash(self):
        return self.cache.get('dependencies_hash')

    def _empty_cache(self):
        # dependencies_list and top-level identity keys are retained as a
        # compatibility view for older callers; authoritative state is in
        # dependency_ids/records and entries.
        return {
            'schema_version': self.SCHEMA_VERSION,
            'version': text_type(__version__),
            'dependency_ids': [],
            'records': {},
            'dependencies_hash': '',
            'entries': {},
            'dependencies_list': [],
        }

    def _dependency_name_list(self):
        return sorted(set(spec['name'] for spec in self._dependency_specs))

    @staticmethod
    def _stat_metadata(stat_result):
        mtime_ns = getattr(stat_result, 'st_mtime_ns', None)
        if mtime_ns is None:
            mtime_ns = int(stat_result.st_mtime * 1000000000)
        return int(stat_result.st_size), int(mtime_ns)

    def _stat_file(self, filepath):
        try:
            stat_result = os.stat(filepath)
        except OSError:
            return None, None
        return stat_result, self._stat_metadata(stat_result)

    def _hash_file(self, filepath):
        """Hash a file without loading the whole file into memory."""
        hasher = hashlib.md5()
        with open(filepath, 'rb') as f:
            while True:
                block = f.read(self.HASH_BLOCK_SIZE)
                if not block:
                    break
                hasher.update(block)
        return text_type(hasher.hexdigest())

    def _hash_file_safely(self, filepath, before_metadata):
        """Hash a stable snapshot, rejecting a file changed during the read."""
        digest = self._hash_file(filepath)
        after_stat, after_metadata = self._stat_file(filepath)
        if after_stat is None or after_metadata != before_metadata:
            return None, False, after_metadata
        return digest, True, after_metadata

    def _spec_for_path(self, filepath):
        runtime_path = self._canonical_path(filepath)
        for spec in self._dependency_specs:
            if spec['runtime_path'] == runtime_path:
                return spec
        return None

    def _compute_dependencies_hash(self, dependency_ids, records):
        pairs = []
        for identity in sorted(set(dependency_ids)):
            record = records.get(identity)
            digest = record.get('digest') if isinstance(record, dict) else None
            pairs.append((identity, digest))
        serialized = json.dumps(pairs, ensure_ascii=False, separators=(',', ':'))
        return self.hash_data(serialized)

    def _validate_dependency(self, spec, memo=None):
        runtime_path = spec['runtime_path']
        if memo is not None and runtime_path in memo:
            return memo[runtime_path]

        record = self.cache.get('records', {}).get(spec['identity'])
        result = {
            'spec': spec,
            'current': False,
            'regular': False,
            'metadata': None,
            'digest': None,
            'stable': True,
        }

        # A fresh cache intentionally reports its dependency files as stale to
        # preserve Model's regeneration path.
        if self.cache_is_new and spec['identity'] in self.cache.get('dependency_ids', []):
            result['current'] = False
            if memo is not None:
                memo[runtime_path] = result
            return result

        stat_result, metadata = self._stat_file(spec['path'])
        result['metadata'] = metadata
        if stat_result is None:
            if memo is not None:
                memo[runtime_path] = result
            return result
        if not stat.S_ISREG(stat_result.st_mode):
            # Directory entries are intentionally tracked by identity but have
            # no content record and never trigger an open/hash operation.
            result['current'] = True
            if memo is not None:
                memo[runtime_path] = result
            return result
        result['regular'] = True

        if not isinstance(record, dict) or not record.get('digest'):
            if memo is not None:
                memo[runtime_path] = result
            return result

        recorded_metadata = (record.get('size'), record.get('mtime_ns'))
        if (not self.strict_content_validation and
                recorded_metadata == metadata):
            result['current'] = True
            result['digest'] = record['digest']
            if memo is not None:
                memo[runtime_path] = result
            return result

        digest, stable, final_metadata = self._hash_file_safely(spec['path'], metadata)
        result['metadata'] = final_metadata or metadata
        result['digest'] = digest
        result['stable'] = stable
        result['current'] = bool(stable and digest == record.get('digest'))
        if result['current'] and result['metadata'] is not None:
            if recorded_metadata != result['metadata']:
                record['size'], record['mtime_ns'] = result['metadata']
                self.dirty = True
        if memo is not None:
            memo[runtime_path] = result
        return result

    def _validate_dependencies(self):
        self._initial_validation = dict()
        all_current = True
        for spec in self._dependency_specs:
            result = self._validate_dependency(spec, self._initial_validation)
            if not result['current']:
                all_current = False
        return all_current

    dependencies_hash = property(lambda self: self.cache['dependencies_hash'])

    def save(self):
        cache_directory = os.path.dirname(os.path.abspath(self.cache_filename)) or os.curdir
        fd, temporary_filename = tempfile.mkstemp(prefix='.file_cache.', suffix='.tmp', dir=cache_directory)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                f.write(json.dumps(self.cache, ensure_ascii=False))
            replace = getattr(os, 'replace', os.rename)
            replace(temporary_filename, self.cache_filename)
        except Exception:
            try:
                os.remove(temporary_filename)
            except OSError:
                pass
            raise
        self.dirty = False

    def update_dependencies(self):
        old_records = self.cache.get('records', {})
        records = {}
        for spec in self._dependency_specs:
            result = self._initial_validation.pop(spec['runtime_path'], None)
            if result is None:
                result = self._validate_dependency_for_update(spec, old_records.get(spec['identity']))
            if result['regular'] and result['stable'] and result['digest']:
                size, mtime_ns = result['metadata']
                records[spec['identity']] = {
                    'digest': result['digest'],
                    'size': size,
                    'mtime_ns': mtime_ns,
                }

        dependency_ids = self._expected_dependency_ids()
        new_hash = self._compute_dependencies_hash(dependency_ids, records)
        self.cache['schema_version'] = self.SCHEMA_VERSION
        self.cache['version'] = text_type(__version__)
        self.cache['dependency_ids'] = dependency_ids
        self.cache['records'] = records
        self.cache['dependencies_hash'] = new_hash
        self.cache['dependencies_list'] = self._dependency_name_list()

        # Keep the old top-level dependency digest view for callers that only
        # inspect it. It is not used for identity, validation, or hashing.
        for identity in dependency_ids:
            if identity in records:
                self.cache[identity] = records[identity]['digest']
            elif identity in self.cache:
                del self.cache[identity]
        self.cache.setdefault('entries', {})
        self.dirty = True

    def _validate_dependency_for_update(self, spec, old_record):
        """Validate a dependency while rebuilding without duplicate hashing."""
        result = {
            'spec': spec,
            'current': False,
            'regular': False,
            'metadata': None,
            'digest': None,
            'stable': True,
        }
        stat_result, metadata = self._stat_file(spec['path'])
        result['metadata'] = metadata
        if stat_result is None:
            return result
        if not stat.S_ISREG(stat_result.st_mode):
            result['current'] = True
            return result
        result['regular'] = True

        if (not self.cache_is_new and isinstance(old_record, dict) and
                old_record.get('digest') and
                not self.strict_content_validation and
                (old_record.get('size'), old_record.get('mtime_ns')) == metadata):
            result['current'] = True
            result['digest'] = old_record['digest']
            return result

        digest, stable, final_metadata = self._hash_file_safely(spec['path'], metadata)
        result['metadata'] = final_metadata or metadata
        result['digest'] = digest
        result['stable'] = stable
        result['current'] = stable
        return result

    def invalidate(self, filename=None):
        if filename is None:
            _log.info("%s: invalidating all file entries in cache", self)
            # Does not invalidate dependencies or their records.
            self.cache['entries'] = {}
            self.dirty = True
            if self.tmp_dir is not None:
                for filename in glob.glob(os.path.join(self.tmp_dir, '*.fst')):
                    os.remove(filename)
        else:
            entry_identity = self._entry_identity(filename)
            if entry_identity not in self.cache.get('entries', {}):
                return
            _log.info("%s: invalidating cache entry for %r", self, filename)
            del self.cache['entries'][entry_identity]
            self.dirty = True

    def hash_data(self, data, mix_dependencies=False):
        if not isinstance(data, binary_type):
            if not isinstance(data, text_type):
                data = text_type(data)
            data = data.encode('utf-8')
        hasher = hashlib.md5()
        if mix_dependencies:
            hasher.update(self.dependencies_hash.encode('utf-8'))
        hasher.update(data)
        return text_type(hasher.hexdigest())

    def add_file(self, filepath, data=None):
        # Generic entries are separate from dependency records.
        if data is None:
            data = self._read_file(filepath)
        filename = self._persisted_identity(filepath)
        self.cache.setdefault('entries', {})[filename] = self.hash_data(data)
        self.dirty = True

    def contains(self, filename, data):
        entries = self.cache.get('entries', {})
        identity = filename if filename in entries else self._entry_identity(filename)
        return (identity in entries) and (entries[identity] == self.hash_data(data))

    def _entry_identity(self, filename):
        if filename in self.cache.get('entries', {}):
            return filename
        # A relative compatibility key is interpreted relative to the cache
        # directory; absolute paths still use their canonical persisted ID.
        if not os.path.isabs(filename):
            candidate = os.path.join(self.cache_dir, filename)
        else:
            candidate = filename
        return self._persisted_identity(candidate)

    @staticmethod
    def _read_file(filepath):
        with open(filepath, 'rb') as f:
            return f.read()

    def file_is_current(self, filepath, data=None):
        """Returns bool whether generic filepath file exists and the cache contains the given data (or the file's current data if none given)."""
        spec = self._spec_for_path(filepath)
        if spec is not None:
            if data is not None:
                record = self.cache.get('records', {}).get(spec['identity'])
                return (not self.cache_is_new and isinstance(record, dict) and
                        record.get('digest') == self.hash_data(data))
            result = self._validate_dependency(spec)
            return bool(result['current'] and result['regular'])

        if not os.path.isfile(filepath):
            return False
        if data is None:
            data = self._read_file(filepath)
        return self.contains(self._persisted_identity(filepath), data)

    def fst_is_current(self, filepath, touch=True):
        """Returns bool whether FST file in directory path exists."""
        result = os.path.isfile(filepath)
        if result and touch:
            touch_file(filepath)
        return result
