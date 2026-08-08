"""Focused tests for Python symbol-table loading and lookup."""

import pytest

import kaldi_active_grammar.utils as utils
from kaldi_active_grammar import KaldiError
from kaldi_active_grammar.model import Model
from kaldi_active_grammar.wfst import SymbolTable


def test_symbol_table_reload_preserves_maps_and_duplicate_behavior(tmp_path):
    first = tmp_path / 'first.txt'
    first.write_text(
        '<eps> 0\n'
        'r\N{LATIN SMALL LETTER E WITH ACUTE}sum\N{LATIN SMALL LETTER E WITH ACUTE} 1\n'
        'alias 1\n'
        'r\N{LATIN SMALL LETTER E WITH ACUTE}sum\N{LATIN SMALL LETTER E WITH ACUTE} 3\n'
        '#nonterm_begin 100\n'
        '#nonterm:rule0 101\n',
        encoding='utf-8')
    second = tmp_path / 'second.txt'
    second.write_text(
        '<eps> 0\n'
        'replacement 2\n'
        '#nonterm_begin 100\n',
        encoding='utf-8')

    table = SymbolTable(str(first))
    word_to_id_map = table.word_to_id_map
    id_to_word_map = table.id_to_word_map

    assert table.word_to_id_map['r\N{LATIN SMALL LETTER E WITH ACUTE}sum\N{LATIN SMALL LETTER E WITH ACUTE}'] == 3
    assert table.id_to_word_map[1] == 'alias'
    assert table.id_to_word_map[3] == 'r\N{LATIN SMALL LETTER E WITH ACUTE}sum\N{LATIN SMALL LETTER E WITH ACUTE}'
    assert table.max_term_word_id == 3
    assert table.longest_word == '#nonterm_begin'

    table.load_text_file(str(second))

    assert table.word_to_id_map is word_to_id_map
    assert table.id_to_word_map is id_to_word_map
    assert 'alias' not in table.word_to_id_map
    assert 1 not in table.id_to_word_map
    assert table.word_to_id_map['replacement'] == 2
    assert table.max_term_word_id == 2
    assert table.longest_word == '#nonterm_begin'


@pytest.mark.parametrize('contents, message', [
    ('', 'empty symbol table'),
    ('word\n', 'expected 2 fields'),
    ('word 1 extra\n', 'expected 2 fields'),
    ('word not-an-id\n', 'invalid symbol ID'),
])
def test_symbol_table_rejects_malformed_entries(tmp_path, contents, message):
    filename = tmp_path / 'words.txt'
    filename.write_text(contents, encoding='utf-8')

    with pytest.raises(ValueError, match=message):
        SymbolTable(str(filename))


def test_symbol_table_failed_reload_does_not_replace_existing_maps(tmp_path):
    valid = tmp_path / 'valid.txt'
    valid.write_text('<eps> 0\nword 1\n', encoding='utf-8')
    invalid = tmp_path / 'invalid.txt'
    invalid.write_text('broken\n', encoding='utf-8')
    table = SymbolTable(str(valid))
    original_forward = dict(table.word_to_id_map)
    original_reverse = dict(table.id_to_word_map)

    with pytest.raises(ValueError):
        table.load_text_file(str(invalid))

    assert table.word_to_id_map == original_forward
    assert table.id_to_word_map == original_reverse


def test_symbol_table_lookup_many_reads_once_and_populates_single_lookup_cache(
        tmp_path, monkeypatch):
    filename = tmp_path / 'phones.txt'
    filename.write_text(
        '<eps> 0\n'
        '#nonterm_bos 10\n'
        '#nonterm:dictation 11\n'
        '#nonterm:rule0 12\n'
        'text-value symbolic\n',
        encoding='utf-8')
    utils.symbol_table_lookup_cache.clear()
    real_open = utils.open
    opened = []

    def counted_open(*args, **kwargs):
        opened.append(args[0])
        return real_open(*args, **kwargs)

    monkeypatch.setattr(utils, 'open', counted_open)
    values = utils.symbol_table_lookup_many(str(filename), (
        '#nonterm_bos', '#nonterm:rule0', '#nonterm:dictation', 'missing'))

    assert values == {
        '#nonterm_bos': 10,
        '#nonterm:rule0': 12,
        '#nonterm:dictation': 11,
        'missing': None,
    }
    assert opened == [str(filename)]
    assert utils.symbol_table_lookup(str(filename), '#nonterm_bos') == 10
    assert opened == [str(filename)]


def test_base_word_info_combines_terminal_max_and_nonterminal_lookup(tmp_path):
    filename = tmp_path / 'words.base.txt'
    filename.write_text(
        '<eps> 0\n'
        'word 7\n'
        '#0 8\n'
        '#nonterm_begin 100\n'
        '#nonterm:rule0 101\n',
        encoding='utf-8')

    assert Model._read_base_word_info(str(filename)) == (8, 100)


def test_load_words_validates_base_and_final_nonterminal_offsets(tmp_path):
    filename = tmp_path / 'words.txt'
    filename.write_text(
        '<eps> 0\nword 1\n#nonterm_begin 101\n', encoding='utf-8')
    model = Model.__new__(Model)
    model.words_table = SymbolTable()
    model.files_dict = {'words.txt': str(filename)}
    model.nonterm_words_offset = 100

    with pytest.raises(KaldiError, match='nonterminal offset mismatch'):
        model.load_words()
