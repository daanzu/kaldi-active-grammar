"""Focused tests for the private dependency/FST cache implementation."""

import hashlib
import json
import os
import shutil

import pytest

import kaldi_active_grammar.utils as utils
from kaldi_active_grammar.utils import _FSTFileCache


@pytest.fixture
def model_files(tmp_path):
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
    return _FSTFileCache(str(tmp_path / 'file_cache.json'), tmp_dir=str(tmp_path),
        dependencies_dict=deps, **kwargs)


def copy_test_model(tmp_path):
    """Create a tiny model-shaped fixture; never copy the multi-GB test model."""
    model_dir = tmp_path / 'kaldi_model'
    model_dir.mkdir()
    words = b'<eps> 0\n#nonterm_begin 1\nhello 2\n'
    phones = b'<eps> 0\nSIL 1\n#nonterm_bos 2\n#nonterm_begin 3\n'
    files = {
        'KAG_VERSION': b'0.5.0\n',
        'words.base.txt': words,
        'words.txt': words,
        'phones.txt': phones,
        'align_lexicon.base.int': b'0 0 1\n',
        'align_lexicon.int': b'0 0 1\n',
        'disambig.int': b'0\n',
        'L_disambig.fst': b'fst\n',
        'tree': b'tree\n',
        'final.mdl': b'model\n',
        'user_lexicon.txt': b'',
        'left_context_phones.txt': b'1\n',
        'nonterminals.txt': b'#nonterm_begin\n',
        'wdisambig_phones.int': b'0\n',
        'wdisambig_words.int': b'0\n',
        'lexiconp_disambig.base.txt': b'hello 1.0 SIL\n',
        'lexiconp_disambig.txt': b'hello 1.0 SIL\n',
        'relabel_ilabels.int': b'2 2\n',
        'words.relabeled.txt': words,
    }
    for filename, contents in files.items():
        (model_dir / filename).write_bytes(contents)
    return model_dir


def test_fresh_cache_writes_only_authoritative_state(model_files):
    tmp_path, deps = model_files
    cache = make_cache(tmp_path, deps)
    state = json.loads((tmp_path / 'file_cache.json').read_text(encoding='utf-8'))

    assert cache.cache_is_new
    assert not cache.dirty
    assert set(state) == {'schema_version', 'version', 'dependency_ids', 'records', 'dependencies_hash'}
    assert set(cache._state['dependency_ids']) == set(deps)
    assert cache.dependencies_hash


def test_reloaded_cache_is_warm_and_preserves_hash(model_files):
    tmp_path, deps = model_files
    first = make_cache(tmp_path, deps)
    second = make_cache(tmp_path, deps)

    assert not second.cache_is_new
    assert second.dependencies_hash == first.dependencies_hash
    assert set(second._state['records']) == set(second._state['dependency_ids'])


def test_version_change_resets_cache(model_files):
    tmp_path, deps = model_files
    make_cache(tmp_path, deps)
    cache_file = tmp_path / 'file_cache.json'
    state = json.loads(cache_file.read_text(encoding='utf-8'))
    state['version'] = '0.0.0-outdated'
    cache_file.write_text(json.dumps(state), encoding='utf-8')

    assert make_cache(tmp_path, deps).cache_is_new


def test_dependency_set_change_resets_cache(model_files):
    tmp_path, deps = model_files
    make_cache(tmp_path, deps)
    extra = tmp_path / 'phones.txt'
    extra.write_bytes(b'a 1\n')

    assert make_cache(tmp_path, dict(deps, phones=str(extra))).cache_is_new


def test_same_basename_dependencies_have_distinct_identities(tmp_path):
    first = tmp_path / 'a' / 'words.txt'
    second = tmp_path / 'b' / 'words.txt'
    first.parent.mkdir()
    second.parent.mkdir()
    first.write_bytes(b'a')
    second.write_bytes(b'b')

    cache = make_cache(tmp_path, {'first': str(first), 'second': str(second)})

    assert cache._state['schema_version'] == 2
    assert cache._state['dependency_ids'] == ['a/words.txt', 'b/words.txt']
    assert cache._state['records']['a/words.txt']['digest'] != cache._state['records']['b/words.txt']['digest']


def test_persisted_identity_falls_back_to_absolute_when_relpath_fails(tmp_path, monkeypatch):
    path = tmp_path / 'dependency.txt'
    path.write_bytes(b'dependency')
    monkeypatch.setattr(os.path, 'relpath', lambda *args, **kwargs: (_ for _ in ()).throw(ValueError('different drives')))

    cache = make_cache(tmp_path, {'dep': str(path)})
    identity = cache._state['dependency_ids'][0]
    expected = os.path.normcase(os.path.realpath(os.path.abspath(str(path)))).replace(os.sep, '/')
    if os.altsep:
        expected = expected.replace(os.altsep, '/')

    assert os.path.isabs(identity)
    assert identity == expected


def test_dependency_hash_is_order_independent(tmp_path):
    first = tmp_path / 'first.txt'
    second = tmp_path / 'second.txt'
    first.write_bytes(b'first')
    second.write_bytes(b'second')

    one = _FSTFileCache(str(tmp_path / 'one.json'), dependencies_dict={'one': str(first), 'two': str(second)})
    two = _FSTFileCache(str(tmp_path / 'two.json'), dependencies_dict={'two': str(second), 'one': str(first)})

    assert one.dependencies_hash == two.dependencies_hash


def test_content_change_resets_once_then_warms(tmp_path):
    path = tmp_path / 'dependency.txt'
    path.write_bytes(b'old')
    first = make_cache(tmp_path, {'dep': str(path)})
    old_hash = first.dependencies_hash
    path.write_bytes(b'new content')

    reset = make_cache(tmp_path, {'dep': str(path)})
    warm = make_cache(tmp_path, {'dep': str(path)})

    assert reset.cache_is_new
    assert reset.dependencies_hash != old_hash
    assert not warm.cache_is_new
    assert warm.dependencies_hash == reset.dependencies_hash


def test_touching_dependency_refreshes_metadata_without_changing_hash(tmp_path):
    path = tmp_path / 'dependency.txt'
    path.write_bytes(b'unchanged')
    first = make_cache(tmp_path, {'dep': str(path)})
    old_hash = first.dependencies_hash
    old_stat = path.stat()
    os.utime(path, ns=(old_stat.st_atime_ns, old_stat.st_mtime_ns + 1000000))

    second = make_cache(tmp_path, {'dep': str(path)})

    assert not second.cache_is_new
    assert second.dependencies_hash == old_hash
    assert second._state['records']['dependency.txt']['mtime_ns'] == path.stat().st_mtime_ns


def test_schema_v2_compatibility_fields_are_dropped_on_save(tmp_path):
    path = tmp_path / 'dependency.txt'
    path.write_bytes(b'dependency')
    make_cache(tmp_path, {'dep': str(path)})
    cache_file = tmp_path / 'file_cache.json'
    state = json.loads(cache_file.read_text(encoding='utf-8'))
    state.update({'entries': {'old': 'entry'}, 'dependencies_list': ['dependency.txt'],
        'dependency.txt': hashlib.md5(b'dependency').hexdigest()})
    cache_file.write_text(json.dumps(state), encoding='utf-8')

    reloaded = make_cache(tmp_path, {'dep': str(path)})
    saved = json.loads(cache_file.read_text(encoding='utf-8'))

    assert not reloaded.cache_is_new
    assert set(saved) == {'schema_version', 'version', 'dependency_ids', 'records', 'dependencies_hash'}


def test_duplicate_logical_names_hash_one_physical_file(tmp_path, monkeypatch):
    path = tmp_path / 'shared.txt'
    path.write_bytes(b'shared')
    calls = []
    original_hash_file = _FSTFileCache._hash_file
    monkeypatch.setattr(_FSTFileCache, '_hash_file',
        lambda self, filepath: (calls.append(filepath), original_hash_file(self, filepath))[1])

    cache = make_cache(tmp_path, {'first': str(path), 'second': str(path)})

    assert len(calls) == 1
    assert cache._state['dependency_ids'] == ['shared.txt']


def test_model_keeps_aliases_out_of_dependency_state(tmp_path, monkeypatch):
    from kaldi_active_grammar.model import Model

    model_dir = copy_test_model(tmp_path)
    monkeypatch.setattr(Model, 'generate_lexicon_files', lambda self: None)
    model = Model(str(model_dir), tmp_dir_needed=False)

    assert model.files_dict['words.txt'] == model.files_dict['words_txt']
    assert model.files_dict['L_disambig.fst'] == model.files_dict['L_disambig_fst']
    assert len(model._fst_cache._state['dependency_ids']) == 18
    assert 'words_txt' not in model._fst_cache._state['dependency_ids']
    assert not hasattr(model, 'fst_cache')


def test_model_warms_when_optional_laf_files_are_absent(tmp_path, monkeypatch):
    from kaldi_active_grammar.model import Model

    model_dir = copy_test_model(tmp_path)
    for filename in ('relabel_ilabels.int', 'words.relabeled.txt'):
        (model_dir / filename).unlink()
    generated = []
    monkeypatch.setattr(Model, 'generate_lexicon_files', lambda self: generated.append(self.model_dir))

    first = Model(str(model_dir), tmp_dir_needed=False)
    second = Model(str(model_dir), tmp_dir_needed=False)

    assert first._fst_cache.cache_is_new
    assert not second._fst_cache.cache_is_new
    assert len(generated) == 1
    assert 'words.relabeled.txt' in first._fst_cache._state['dependency_ids']
    assert first._fst_cache._state['records']['words.relabeled.txt'] == {'absent': True}


def test_model_records_generated_laf_file(tmp_path, monkeypatch):
    from kaldi_active_grammar.model import Model

    model_dir = copy_test_model(tmp_path)
    (model_dir / 'words.relabeled.txt').unlink()
    generated = []
    monkeypatch.setattr(Model, 'generate_lexicon_files', lambda self: None)

    def generate_relabeled(words_filename, relabel_filename, output_filename):
        generated.append(output_filename)
        shutil.copyfile(words_filename, output_filename)

    monkeypatch.setattr(Model, 'generate_words_relabeled_file', staticmethod(generate_relabeled))
    first = Model(str(model_dir), tmp_dir_needed=False)
    second = Model(str(model_dir), tmp_dir_needed=False)

    assert first._fst_cache.cache_is_new
    assert not second._fst_cache.cache_is_new
    assert len(generated) == 1
    assert 'words.relabeled.txt' in first._fst_cache._state['records']


def test_model_warms_after_optional_laf_dependency_appears(tmp_path, monkeypatch):
    from kaldi_active_grammar.model import Model

    model_dir = copy_test_model(tmp_path)
    relabel_path = model_dir / 'relabel_ilabels.int'
    words_relabeled_path = model_dir / 'words.relabeled.txt'
    relabel_path.unlink()
    words_relabeled_path.unlink()
    lexicon_regenerations = []
    relabeled_generations = []
    monkeypatch.setattr(Model, 'generate_lexicon_files',
        lambda self: lexicon_regenerations.append(self.model_dir))

    first = Model(str(model_dir), tmp_dir_needed=False)
    absent_warm = Model(str(model_dir), tmp_dir_needed=False)
    relabel_path.write_bytes(b'2 2\n')

    def generate_relabeled(words_filename, relabel_filename, output_filename):
        relabeled_generations.append(output_filename)
        shutil.copyfile(words_filename, output_filename)

    monkeypatch.setattr(Model, 'generate_words_relabeled_file', staticmethod(generate_relabeled))
    reset = Model(str(model_dir), tmp_dir_needed=False)
    present_warm = Model(str(model_dir), tmp_dir_needed=False)

    assert first._fst_cache.cache_is_new
    assert not absent_warm._fst_cache.cache_is_new
    assert reset._fst_cache.cache_is_new
    assert not present_warm._fst_cache.cache_is_new
    assert len(lexicon_regenerations) == 2
    assert relabeled_generations == [str(words_relabeled_path)]
    assert reset._fst_cache._state['records']['relabel_ilabels.int']['digest']
    assert reset._fst_cache._state['records']['words.relabeled.txt']['digest']


def test_warm_model_stats_each_physical_dependency_once(tmp_path, monkeypatch):
    from kaldi_active_grammar.model import Model

    model_dir = copy_test_model(tmp_path)
    monkeypatch.setattr(Model, 'generate_lexicon_files', lambda self: None)
    Model(str(model_dir), tmp_dir_needed=False)
    stat_paths = []
    original_stat_file = _FSTFileCache._stat_file
    monkeypatch.setattr(_FSTFileCache, '_stat_file',
        lambda self, filepath: (stat_paths.append(self._canonical_path(filepath)), original_stat_file(self, filepath))[1])

    second = Model(str(model_dir), tmp_dir_needed=False)

    assert len(second._fst_cache._state['dependency_ids']) == 18
    assert len(stat_paths) == 18
    assert len(set(stat_paths)) == 18


def test_warm_model_hashes_each_dependency_once_in_strict_mode(tmp_path, monkeypatch):
    from kaldi_active_grammar.model import Model

    model_dir = copy_test_model(tmp_path)
    monkeypatch.setattr(Model, 'generate_lexicon_files', lambda self: None)
    Model(str(model_dir), tmp_dir_needed=False)
    hash_paths = []
    original_hash_file = _FSTFileCache._hash_file
    monkeypatch.setattr(_FSTFileCache, '_hash_file',
        lambda self, filepath: (hash_paths.append(self._canonical_path(filepath)), original_hash_file(self, filepath))[1])

    Model(str(model_dir), tmp_dir_needed=False, strict_content_validation=True)

    assert len(hash_paths) == 18
    assert len(set(hash_paths)) == 18


def test_deleted_dependency_resets_once_then_warms(tmp_path):
    path = tmp_path / 'dependency.txt'
    path.write_bytes(b'present')
    make_cache(tmp_path, {'dep': str(path)})
    path.unlink()

    reset = make_cache(tmp_path, {'dep': str(path)})
    warm = make_cache(tmp_path, {'dep': str(path)})

    assert reset.cache_is_new
    assert reset._state['records']['dependency.txt'] == {'absent': True}
    assert not warm.cache_is_new


def test_absent_dependency_appearing_resets_once_then_warms(tmp_path):
    path = tmp_path / 'dependency.txt'
    first = make_cache(tmp_path, {'dep': str(path)})
    absent_hash = first.dependencies_hash
    path.write_bytes(b'present')

    reset = make_cache(tmp_path, {'dep': str(path)})
    warm = make_cache(tmp_path, {'dep': str(path)})

    assert reset.cache_is_new
    assert reset._state['records']['dependency.txt']['digest']
    assert reset.dependencies_hash != absent_hash
    assert not warm.cache_is_new


def test_unchanged_dependencies_use_stat_only(model_files, monkeypatch):
    tmp_path, deps = model_files
    make_cache(tmp_path, deps)
    monkeypatch.setattr(_FSTFileCache, '_hash_file',
        lambda self, filepath: pytest.fail('unchanged dependency was hashed'))

    cache = make_cache(tmp_path, deps)

    assert not cache.cache_is_new


def test_mtime_change_hashes_once_and_stays_warm(model_files, monkeypatch):
    tmp_path, deps = model_files
    make_cache(tmp_path, deps)
    old_stat = os.stat(deps['words.txt'])
    os.utime(deps['words.txt'], ns=(old_stat.st_atime_ns, old_stat.st_mtime_ns + 1000000))
    calls = []
    original_hash_file = _FSTFileCache._hash_file
    monkeypatch.setattr(_FSTFileCache, '_hash_file',
        lambda self, filepath: (calls.append(filepath), original_hash_file(self, filepath))[1])

    cache = make_cache(tmp_path, deps)

    assert not cache.cache_is_new
    assert len(calls) == 1


def test_same_size_same_mtime_replacement_is_normal_mode_limitation(tmp_path):
    path = tmp_path / 'dependency.txt'
    path.write_bytes(b'old!')
    make_cache(tmp_path, {'dep': str(path)})
    original_stat = path.stat()
    path.write_bytes(b'new!')
    os.utime(path, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))

    assert not make_cache(tmp_path, {'dep': str(path)}).cache_is_new


def test_strict_mode_detects_same_size_same_mtime_replacement(tmp_path):
    path = tmp_path / 'dependency.txt'
    path.write_bytes(b'old!')
    make_cache(tmp_path, {'dep': str(path)})
    original_stat = path.stat()
    path.write_bytes(b'new!')
    os.utime(path, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))

    assert make_cache(tmp_path, {'dep': str(path)}, strict_content_validation=True).cache_is_new


def test_hashing_rejects_file_changed_during_read(tmp_path, monkeypatch):
    path = tmp_path / 'dependency.txt'
    path.write_bytes(b'content')
    make_cache(tmp_path, {'dep': str(path)})
    current = path.stat()
    os.utime(path, ns=(current.st_atime_ns, current.st_mtime_ns + 1000000))
    original_hash_file = _FSTFileCache._hash_file
    changed = [False]

    def hash_and_touch(self, filepath):
        digest = original_hash_file(self, filepath)
        if not changed[0]:
            changed[0] = True
            stat_result = os.stat(filepath)
            os.utime(filepath, ns=(stat_result.st_atime_ns, stat_result.st_mtime_ns + 1000000))
        return digest

    monkeypatch.setattr(_FSTFileCache, '_hash_file', hash_and_touch)

    assert make_cache(tmp_path, {'dep': str(path)}).cache_is_new


def test_atomic_save_replaces_after_closing_temporary_file(tmp_path, monkeypatch):
    cache = make_cache(tmp_path, {})
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


def test_model_invalidation_clears_fsts_and_next_start_is_warm(tmp_path, monkeypatch):
    from kaldi_active_grammar.model import Model

    model_dir = copy_test_model(tmp_path)
    tmp_dir = tmp_path / 'fst-cache'
    generated = []

    def regenerate(self):
        generated.append(self.model_dir)
        self._clear_cached_fsts()

    monkeypatch.setattr(Model, 'generate_lexicon_files', regenerate)
    Model(str(model_dir), str(tmp_dir), tmp_dir_needed=True)
    stale_fst = tmp_dir / 'stale.fst'
    stale_fst.write_bytes(b'fst')
    warm = Model(str(model_dir), str(tmp_dir), tmp_dir_needed=True)
    assert not warm._fst_cache.cache_is_new
    assert stale_fst.exists()

    invalidated = Model(str(model_dir), str(tmp_dir), tmp_dir_needed=True, invalidate=True)

    assert invalidated._fst_cache.cache_is_new
    assert not stale_fst.exists()
    assert len(generated) == 2


def test_compiler_invalidation_rebuilds_once_and_clears_fsts(monkeypatch, tmp_path):
    import importlib

    compiler_module = importlib.import_module('kaldi_active_grammar.compiler')
    from kaldi_active_grammar.compiler import Compiler
    from kaldi_active_grammar.model import Model

    model_dir = copy_test_model(tmp_path)
    tmp_dir = tmp_path / 'fst-cache'
    generated = []

    def regenerate(self):
        generated.append(self.model_dir)
        self._clear_cached_fsts()

    monkeypatch.setattr(Model, 'generate_lexicon_files', regenerate)
    monkeypatch.setattr(compiler_module.NativeWFST, 'init_class', lambda *args, **kwargs: None)

    first = Compiler(model_dir=model_dir, tmp_dir=tmp_dir, framework='laf')
    stale_fst = tmp_dir / 'stale.fst'
    stale_fst.write_bytes(b'fst')
    warm = Compiler(model_dir=model_dir, tmp_dir=tmp_dir, framework='laf', invalidate=False)

    assert stale_fst.exists()
    assert not warm.model._fst_cache.cache_is_new
    warm.close()

    invalidated = Compiler(model_dir=model_dir, tmp_dir=tmp_dir, framework='laf', invalidate=True)

    assert invalidated.model._fst_cache.cache_is_new
    assert not stale_fst.exists()
    assert len(generated) == 2
    assert not hasattr(first, 'fst_cache')
    first.close()
    invalidated.close()


def test_cache_and_rule_cache_are_not_public():
    import importlib
    compiler_module = importlib.import_module('kaldi_active_grammar.compiler')

    assert not hasattr(utils, 'FSTFileCache')
    assert not hasattr(compiler_module.Compiler, 'fst_cache')
    assert not hasattr(compiler_module.KaldiRule, 'fst_cache')


def test_fst_filename_seed_is_stable_between_warm_starts(model_files):
    tmp_path, deps = model_files
    first = make_cache(tmp_path, deps)
    first_name = first.hash_data('rule text', mix_dependencies=True)
    second = make_cache(tmp_path, deps)

    assert second.hash_data('rule text', mix_dependencies=True) == first_name
