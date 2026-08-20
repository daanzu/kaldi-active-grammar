import importlib.util
from pathlib import Path

import pytest


_ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    'kag_build_versioning', _ROOT / 'building' / 'versioning.py')
versioning = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(versioning)


def _write_version_file(root, base='3.3.0'):
    package_dir = root / 'kaldi_active_grammar'
    package_dir.mkdir()
    (package_dir / '_version.py').write_text(
        "__version_base__ = %r\n" % base, encoding='utf-8')


def test_development_version_contains_timestamp_revision_and_dirty_state(
        tmp_path, monkeypatch):
    _write_version_file(tmp_path)

    def git_output(root, *arguments):
        if arguments[:2] == ('rev-parse', '--show-toplevel'):
            return str(tmp_path)
        if arguments[:2] == ('tag', '--points-at'):
            return ''
        if arguments[0] == 'rev-parse':
            return 'ABCDEF12'
        if arguments[0] == 'status':
            return ' M setup.py'
        raise AssertionError(arguments)

    monkeypatch.setattr(versioning, '_git_output', git_output)
    actual = versioning.resolve_build_version(
        str(tmp_path), environ={}, timestamp='20260816153042')
    assert actual == '3.3.0.dev20260816153042+gabcdef12.dirty'


def test_explicit_version_override(tmp_path, monkeypatch):
    _write_version_file(tmp_path)
    monkeypatch.setattr(versioning, '_git_output', lambda root, *arguments: '')
    assert versioning.resolve_build_version(
        str(tmp_path), environ={'KALDIAG_BUILD_VERSION': '3.3.0.dev42'}) == (
            '3.3.0.dev42')


def test_clean_release_tag_produces_exact_version(tmp_path, monkeypatch):
    _write_version_file(tmp_path)

    def git_output(root, *arguments):
        if arguments[:2] == ('rev-parse', '--show-toplevel'):
            return str(tmp_path)
        if arguments[:2] == ('tag', '--points-at'):
            return 'v3.3.0'
        if arguments[0] == 'status':
            return ''
        raise AssertionError(arguments)

    monkeypatch.setattr(versioning, '_git_output', git_output)
    assert versioning.resolve_build_version(str(tmp_path), environ={}) == '3.3.0'


def test_release_tag_must_target_base_version(tmp_path, monkeypatch):
    _write_version_file(tmp_path)

    def git_output(root, *arguments):
        if arguments[:2] == ('rev-parse', '--show-toplevel'):
            return str(tmp_path)
        return 'v3.2.0' if arguments[0] == 'tag' else ''

    monkeypatch.setattr(versioning, '_git_output', git_output)
    with pytest.raises(RuntimeError, match='does not target base version'):
        versioning.resolve_build_version(str(tmp_path), environ={})


def test_build_timestamp_must_be_utc_timestamp_shape(tmp_path, monkeypatch):
    _write_version_file(tmp_path)
    monkeypatch.setattr(versioning, '_git_output', lambda root, *arguments: '')
    with pytest.raises(RuntimeError, match='14-digit UTC timestamp'):
        versioning.resolve_build_version(
            str(tmp_path), environ={'KALDIAG_BUILD_TIMESTAMP': 'not-a-date'})
