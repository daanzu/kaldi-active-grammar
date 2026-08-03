"""Characterization tests for FSTFileCache: pin down the currency-checking,
reset, and invalidation semantics that any caching optimization must preserve."""

import json
import os
import hashlib

import pytest

from kaldi_active_grammar.utils import FSTFileCache


@pytest.fixture
def model_files(tmp_path):
    """A fake model dir with two dependency files, keyed by basename as Model does."""
    deps = {}
    for name, content in [
        ('words.txt', b'<eps> 0\none 1\ntwo 2\n'),
        ('final.mdl', b'MODELDATA' * 1000),
    ]:
        path = tmp_path / name
        path.write_bytes(content)
        deps[name] = str(path)
    return tmp_path, deps


def make_cache(tmp_path, deps, **kwargs):
    return FSTFileCache(str(tmp_path / 'file_cache.json'), tmp_dir=str(tmp_path),
        dependencies_dict=deps, **kwargs)


def test_fresh_cache_initializes_and_saves(model_files):
    tmp_path, deps = model_files
    cache = make_cache(tmp_path, deps)
    assert cache.cache_is_new
    assert not cache.dirty  # save() during init cleared it
    assert (tmp_path / 'file_cache.json').is_file()
    assert cache.cache['dependencies_list'] == sorted(deps.keys())
    assert cache.dependencies_hash
    for name in deps:
        assert name in cache.cache


def test_fresh_cache_reports_dependencies_stale(model_files):
    # On a brand-new cache, dependency files must be reported stale, so Model
    # regenerates the lexicon files.
    tmp_path, deps = model_files
    cache = make_cache(tmp_path, deps)
    assert not cache.file_is_current(deps['words.txt'])


def test_reloaded_cache_reports_dependencies_current(model_files):
    tmp_path, deps = model_files
    make_cache(tmp_path, deps)
    cache = make_cache(tmp_path, deps)
    assert not cache.cache_is_new
    for path in deps.values():
        assert cache.file_is_current(path)


def test_repeated_currency_checks_are_stable(model_files):
    # Model init checks the same files several times (necessary + non-lazy lists,
    # plus underscore-alias keys); every check must agree.
    tmp_path, deps = model_files
    make_cache(tmp_path, deps)
    cache = make_cache(tmp_path, deps)
    for _ in range(3):
        assert cache.file_is_current(deps['words.txt'])


def test_content_change_is_detected_within_instance(model_files):
    tmp_path, deps = model_files
    make_cache(tmp_path, deps)
    cache = make_cache(tmp_path, deps)
    assert cache.file_is_current(deps['words.txt'])
    with open(deps['words.txt'], 'ab') as f:
        f.write(b'three 3\n')
    assert not cache.file_is_current(deps['words.txt'])


def test_changed_dependency_resets_cache_on_load(model_files):
    tmp_path, deps = model_files
    make_cache(tmp_path, deps)
    with open(deps['final.mdl'], 'wb') as f:
        f.write(b'DIFFERENT MODEL DATA')
    cache = make_cache(tmp_path, deps)
    assert cache.cache_is_new


def test_missing_file_is_not_current(model_files):
    tmp_path, deps = model_files
    make_cache(tmp_path, deps)
    cache = make_cache(tmp_path, deps)
    assert not cache.file_is_current(str(tmp_path / 'nonexistent.txt'))


def test_non_dependency_file_add_and_check(model_files):
    tmp_path, deps = model_files
    cache = make_cache(tmp_path, deps)
    extra = tmp_path / 'extra.txt'
    extra.write_bytes(b'extra data')
    assert not cache.file_is_current(str(extra))
    cache.add_file(str(extra))
    assert cache.dirty
    assert cache.file_is_current(str(extra))
    # Currency is also visible to a reloaded instance once saved
    cache.save()
    assert not cache.dirty
    cache2 = make_cache(tmp_path, deps)
    assert cache2.file_is_current(str(extra))


def test_contains_with_explicit_data(model_files):
    tmp_path, deps = model_files
    cache = make_cache(tmp_path, deps)
    cache.add_file(str(tmp_path / 'words.txt'))
    with open(deps['words.txt'], 'rb') as f:
        data = f.read()
    assert cache.contains('words.txt', data)
    assert not cache.contains('words.txt', data + b'changed')
    assert not cache.contains('unknown.txt', data)


def test_version_change_resets_cache(model_files):
    tmp_path, deps = model_files
    make_cache(tmp_path, deps)
    cache_file = tmp_path / 'file_cache.json'
    contents = json.loads(cache_file.read_text(encoding='utf-8'))
    contents['version'] = '0.0.0-outdated'
    cache_file.write_text(json.dumps(contents), encoding='utf-8')
    cache = make_cache(tmp_path, deps)
    assert cache.cache_is_new


def test_dependencies_list_change_resets_cache(model_files):
    tmp_path, deps = model_files
    make_cache(tmp_path, deps)
    extra = tmp_path / 'phones.txt'
    extra.write_bytes(b'a 1\n')
    new_deps = dict(deps, **{'phones.txt': str(extra)})
    cache = make_cache(tmp_path, new_deps)
    assert cache.cache_is_new


def test_forced_invalidate_resets_cache(model_files):
    tmp_path, deps = model_files
    make_cache(tmp_path, deps)
    cache = make_cache(tmp_path, deps, invalidate=True)
    assert cache.cache_is_new


def test_invalidate_single_entry(model_files):
    tmp_path, deps = model_files
    cache = make_cache(tmp_path, deps)
    extra = tmp_path / 'extra.txt'
    extra.write_bytes(b'extra data')
    cache.add_file(str(extra))
    cache.save()
    cache.invalidate('extra.txt')
    assert cache.dirty
    assert not cache.file_is_current(str(extra))


def test_invalidate_all_clears_entries_and_fst_files(model_files):
    tmp_path, deps = model_files
    make_cache(tmp_path, deps)
    cache = make_cache(tmp_path, deps)
    extra = tmp_path / 'extra.txt'
    extra.write_bytes(b'extra data')
    cache.add_file(str(extra))
    fst_file = tmp_path / 'deadbeef.fst'
    fst_file.write_bytes(b'fst data')
    cache.invalidate()
    assert not fst_file.exists()
    assert not cache.file_is_current(str(extra))
    # Version and dependency bookkeeping survive
    assert 'version' in cache.cache
    assert cache.cache['dependencies_list'] == sorted(deps.keys())


def test_fst_is_current_checks_existence_only(model_files):
    tmp_path, deps = model_files
    cache = make_cache(tmp_path, deps)
    fst_file = tmp_path / 'cafef00d.fst'
    assert not cache.fst_is_current(str(fst_file), touch=False)
    fst_file.write_bytes(b'fst data')
    assert cache.fst_is_current(str(fst_file), touch=False)


def test_hash_data_accepts_text_and_bytes(model_files):
    tmp_path, deps = model_files
    cache = make_cache(tmp_path, deps)
    assert cache.hash_data(u'abc') == cache.hash_data(b'abc')
    assert cache.hash_data(u'abc') != cache.hash_data(b'abcd')
    # mix_dependencies changes the hash
    assert cache.hash_data(u'abc', mix_dependencies=True) != cache.hash_data(u'abc')


def test_schema_v2_records_use_distinct_persisted_identities(tmp_path):
    first = tmp_path / 'a' / 'words.txt'
    second = tmp_path / 'b' / 'words.txt'
    first.parent.mkdir()
    second.parent.mkdir()
    first.write_bytes(b'a')
    second.write_bytes(b'b')

    cache = make_cache(tmp_path, {'first': str(first), 'second': str(second)})

    assert cache.cache['schema_version'] == 2
    assert cache.cache['dependency_ids'] == ['a/words.txt', 'b/words.txt']
    assert set(cache.cache['records']) == set(cache.cache['dependency_ids'])
    assert cache.cache['records']['a/words.txt']['digest'] != cache.cache['records']['b/words.txt']['digest']


def test_dependency_hash_is_order_independent(tmp_path):
    first = tmp_path / 'first.txt'
    second = tmp_path / 'second.txt'
    first.write_bytes(b'first')
    second.write_bytes(b'second')

    one = FSTFileCache(str(tmp_path / 'one.json'), dependencies_dict={
        'one': str(first), 'two': str(second)})
    two = FSTFileCache(str(tmp_path / 'two.json'), dependencies_dict={
        'two': str(second), 'one': str(first)})

    assert one.dependencies_hash == two.dependencies_hash


def test_dependency_hash_changes_when_content_changes(tmp_path):
    path = tmp_path / 'dependency.txt'
    path.write_bytes(b'old')
    first = FSTFileCache(str(tmp_path / 'cache.json'), dependencies_dict={'dep': str(path)})
    old_hash = first.dependencies_hash
    path.write_bytes(b'new content')

    second = FSTFileCache(str(tmp_path / 'cache.json'), dependencies_dict={'dep': str(path)})

    assert second.cache_is_new
    assert second.dependencies_hash != old_hash


def test_touching_dependency_does_not_change_content_hash(tmp_path):
    path = tmp_path / 'dependency.txt'
    path.write_bytes(b'unchanged')
    first = FSTFileCache(str(tmp_path / 'cache.json'), dependencies_dict={'dep': str(path)})
    old_hash = first.dependencies_hash
    old_stat = path.stat()
    os.utime(path, ns=(old_stat.st_atime_ns, old_stat.st_mtime_ns + 1000000))

    second = FSTFileCache(str(tmp_path / 'cache.json'), dependencies_dict={'dep': str(path)})

    assert not second.cache_is_new
    assert second.dependencies_hash == old_hash
    assert second.cache['records']['dependency.txt']['mtime_ns'] == path.stat().st_mtime_ns


def test_legacy_cache_is_reset_once(tmp_path, monkeypatch):
    path = tmp_path / 'dependency.txt'
    path.write_bytes(b'dependency')
    cache_file = tmp_path / 'cache.json'
    cache_file.write_text(json.dumps({
        'version': '3.2.0',
        'dependencies_list': ['dependency.txt'],
        'dependencies_hash': 'legacy',
        'dependency.txt': hashlib.md5(b'dependency').hexdigest(),
    }), encoding='utf-8')

    calls = []
    original_hash_file = FSTFileCache._hash_file
    monkeypatch.setattr(FSTFileCache, '_hash_file',
        lambda self, filepath: (calls.append(filepath), original_hash_file(self, filepath))[1])
    migrated = FSTFileCache(str(cache_file), dependencies_dict={'dep': str(path)})
    assert migrated.cache_is_new
    assert len(calls) == 1

    calls[:] = []
    reloaded = FSTFileCache(str(cache_file), dependencies_dict={'dep': str(path)})
    assert not reloaded.cache_is_new
    assert calls == []


def test_invalidate_keeps_dependency_records_but_clears_entries_and_fsts(model_files):
    tmp_path, deps = model_files
    cache = make_cache(tmp_path, deps)
    cache.add_file(str(tmp_path / 'extra.txt'), b'extra')
    fst_file = tmp_path / 'cached.fst'
    fst_file.write_bytes(b'fst')
    records = json.loads(json.dumps(cache.cache['records']))

    cache.invalidate()

    assert cache.cache['records'] == records
    assert cache.cache['entries'] == {}
    assert not fst_file.exists()


def test_duplicate_logical_names_hash_one_physical_file(tmp_path, monkeypatch):
    path = tmp_path / 'shared.txt'
    path.write_bytes(b'shared')
    calls = []
    original_hash_file = FSTFileCache._hash_file
    monkeypatch.setattr(FSTFileCache, '_hash_file',
        lambda self, filepath: (calls.append(filepath), original_hash_file(self, filepath))[1])

    cache = make_cache(tmp_path, {'first': str(path), 'second': str(path)})

    assert len(calls) == 1
    assert cache.cache['dependency_ids'] == ['shared.txt']


def test_model_keeps_aliases_out_of_dependency_state():
    from kaldi_active_grammar.model import Model

    model = Model('tests/kaldi_model', tmp_dir_needed=False)

    assert model.files_dict['words.txt'] == model.files_dict['words_txt']
    assert model.files_dict['L_disambig.fst'] == model.files_dict['L_disambig_fst']
    assert len(model.fst_cache.cache['dependency_ids']) == 18
    assert len(model.fst_cache.cache['dependencies_list']) == 18
    assert 'words_txt' not in model.fst_cache.cache['dependencies_list']


def test_none_directory_and_missing_dependency_values_are_explicit(tmp_path):
    directory = tmp_path / 'directory'
    directory.mkdir()
    missing = tmp_path / 'missing.txt'
    cache = make_cache(tmp_path, {
        'optional': None,
        'directory': str(directory),
        'missing': str(missing),
    })

    assert 'optional' not in cache.cache['dependencies_list']
    assert not cache.file_is_current(str(directory))
    assert not cache.file_is_current(str(missing))
    assert 'directory' in cache.cache['dependency_ids']
    assert 'missing.txt' in cache.cache['dependency_ids']
    assert 'directory' not in cache.cache['records']
    assert 'missing.txt' not in cache.cache['records']


def test_deleted_dependency_is_stale_and_resets(tmp_path):
    path = tmp_path / 'dependency.txt'
    path.write_bytes(b'present')
    make_cache(tmp_path, {'dep': str(path)})
    path.unlink()

    cache = make_cache(tmp_path, {'dep': str(path)})

    assert cache.cache_is_new
    assert not cache.file_is_current(str(path))


def test_metadata_fast_path_does_not_open_unchanged_dependency(model_files, monkeypatch):
    tmp_path, deps = model_files
    make_cache(tmp_path, deps)
    cache = make_cache(tmp_path, deps)
    monkeypatch.setattr(cache, '_hash_file', lambda filepath: pytest.fail('unchanged file was hashed'))

    assert cache.file_is_current(deps['words.txt'])


def test_size_change_hashes_and_is_stale(model_files, monkeypatch):
    tmp_path, deps = model_files
    make_cache(tmp_path, deps)
    cache = make_cache(tmp_path, deps)
    calls = []
    original_hash_file = cache._hash_file
    monkeypatch.setattr(cache, '_hash_file',
        lambda filepath: (calls.append(filepath), original_hash_file(filepath))[1])
    with open(deps['words.txt'], 'ab') as f:
        f.write(b'changed')

    assert not cache.file_is_current(deps['words.txt'])
    assert len(calls) == 1


def test_mtime_only_change_hashes_once_and_refreshes_metadata(model_files, monkeypatch):
    tmp_path, deps = model_files
    make_cache(tmp_path, deps)
    old_mtime_ns = os.stat(deps['words.txt']).st_mtime_ns
    os.utime(deps['words.txt'], ns=(old_mtime_ns, old_mtime_ns + 1000000))
    calls = []
    original_hash_file = FSTFileCache._hash_file
    monkeypatch.setattr(FSTFileCache, '_hash_file',
        lambda self, filepath: (calls.append(filepath), original_hash_file(self, filepath))[1])

    cache = make_cache(tmp_path, deps)

    assert not cache.cache_is_new
    assert len(calls) == 1
    assert cache.cache['records']['words.txt']['mtime_ns'] == os.stat(deps['words.txt']).st_mtime_ns


def test_same_size_same_mtime_replacement_is_normal_mode_limitation(tmp_path):
    path = tmp_path / 'dependency.txt'
    path.write_bytes(b'old!')
    make_cache(tmp_path, {'dep': str(path)})
    original_stat = path.stat()
    path.write_bytes(b'new!')
    os.utime(path, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))

    cache = make_cache(tmp_path, {'dep': str(path)})

    assert not cache.cache_is_new
    assert cache.file_is_current(str(path))


def test_strict_mode_detects_same_size_same_mtime_replacement(tmp_path):
    path = tmp_path / 'dependency.txt'
    path.write_bytes(b'old!')
    make_cache(tmp_path, {'dep': str(path)})
    original_stat = path.stat()
    path.write_bytes(b'new!')
    os.utime(path, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))

    cache = make_cache(tmp_path, {'dep': str(path)}, strict_content_validation=True)

    assert cache.cache_is_new


def test_content_change_updates_dependency_hash(tmp_path):
    path = tmp_path / 'dependency.txt'
    path.write_bytes(b'old')
    first = make_cache(tmp_path, {'dep': str(path)})
    old_hash = first.dependencies_hash
    path.write_bytes(b'new content')

    second = make_cache(tmp_path, {'dep': str(path)})

    assert second.dependencies_hash != old_hash


def test_hashing_rejects_file_changed_during_read(tmp_path, monkeypatch):
    path = tmp_path / 'dependency.txt'
    path.write_bytes(b'content')
    make_cache(tmp_path, {'dep': str(path)})
    cache = make_cache(tmp_path, {'dep': str(path)})
    original_hash_file = cache._hash_file
    changed = [False]

    def hash_and_touch(filepath):
        digest = original_hash_file(filepath)
        if not changed[0]:
            changed[0] = True
            current = os.stat(filepath)
            os.utime(filepath, ns=(current.st_atime_ns, current.st_mtime_ns + 1000000))
        return digest

    monkeypatch.setattr(cache, '_hash_file', hash_and_touch)
    current = os.stat(path)
    os.utime(path, ns=(current.st_atime_ns, current.st_mtime_ns + 1000000))

    assert not cache.file_is_current(str(path))


def test_reloading_refreshed_metadata_returns_to_stat_only_path(tmp_path, monkeypatch):
    path = tmp_path / 'dependency.txt'
    path.write_bytes(b'content')
    make_cache(tmp_path, {'dep': str(path)})
    old_stat = path.stat()
    os.utime(path, ns=(old_stat.st_atime_ns, old_stat.st_mtime_ns + 1000000))
    make_cache(tmp_path, {'dep': str(path)})
    cache = make_cache(tmp_path, {'dep': str(path)})
    monkeypatch.setattr(cache, '_hash_file', lambda filepath: pytest.fail('refreshed file was hashed'))

    assert cache.file_is_current(str(path))


def test_save_replaces_cache_after_closing_temporary_file(tmp_path, monkeypatch):
    cache = make_cache(tmp_path, {})
    cache.cache['entries']['entry.txt'] = cache.hash_data(b'entry')
    cache.dirty = True
    replacements = []
    original_replace = os.replace

    def replace(source, destination):
        assert source != destination
        with open(source, 'rb') as temporary:
            temporary.read()
        replacements.append(source)
        return original_replace(source, destination)

    monkeypatch.setattr(os, 'replace', replace)
    cache.save()

    assert replacements
    assert not os.path.exists(replacements[0])
    assert not cache.dirty
