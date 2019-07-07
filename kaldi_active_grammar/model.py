#
# This file is part of kaldi-active-grammar.
# (c) Copyright 2019 by David Zurow
# Licensed under the AGPL-3.0, with exceptions; see LICENSE.txt file.
#

import os, re

import requests

try:
    # g2p_en==2.0.0
    import g2p_en
except ImportError:
    g2p_en = None

from . import _log, KaldiError
from .utils import find_file, load_symbol_table, symbol_table_lookup, touch
from .compiler import Compiler
from .kaldi import augment_phones_txt, augment_words_txt

_log = _log.getChild('model')


########################################################################################################################

class Lexicon(object):

    CMU_to_XSAMPA_dict = {
        "'"   : "'",
        'AA'  : 'A',
        'AE'  : '{',
        'AH'  : 'V',  ##
        'AO'  : 'O',  ##
        'AW'  : 'aU',
        'AY'  : 'aI',
        'B'   : 'b',
        'CH'  : 'tS',
        'D'   : 'd',
        'DH'  : 'D',
        'EH'  : 'E',
        'ER'  : '3',
        'EY'  : 'eI',
        'F'   : 'f',
        'G'   : 'g',
        'HH'  : 'h',
        'IH'  : 'I',
        'IY'  : 'i',
        'JH'  : 'dZ',
        'K'   : 'k',
        'L'   : 'l',
        'M'   : 'm',
        'NG'  : 'N',
        'N'   : 'n',
        'OW'  : 'oU',
        'OY'  : 'OI', ##
        'P'   : 'p',
        'R'   : 'r',
        'SH'  : 'S',
        'S'   : 's',
        'TH'  : 'T',
        'T'   : 't',
        'UH'  : 'U',
        'UW'  : 'u',
        'V'   : 'v',
        'W'   : 'w',
        'Y'   : 'j',
        'ZH'  : 'Z',
        'Z'   : 'z',
    }
    CMU_to_XSAMPA_dict.update({'AX': '@'})
    del CMU_to_XSAMPA_dict["'"]
    XSAMPA_to_CMU_dict = { v: k for k,v in CMU_to_XSAMPA_dict.items() }  # FIXME: handle double-entries

    @classmethod
    def cmu_to_xsampa(cls, phones):
        new_phones = []
        for phone in phones:
            stress = False
            if phone.endswith('1'):
                phone = phone[:-1]
                stress = True
            elif phone.endswith(('0', '2')):
                phone = phone[:-1]
            phone = cls.CMU_to_XSAMPA_dict[phone]
            assert 1 <= len(phone) <= 2
            while len(phone):
                new_phones.append(("'" if stress else '') + phone[:1])
                stress = False
                phone = phone[1:]
        return new_phones

    @classmethod
    def make_position_dependent(cls, phones):
        if len(phones) == 0: return []
        elif len(phones) == 1: return [phones[0]+'_S']
        else: return [phones[0]+'_B'] + [phone+'_I' for phone in phones[1:-1]] + [phones[-1]+'_E']

    g2p_en = None

    @classmethod
    def generate_pronunciation(cls, word):
        """returns CMU/arpabet phones"""
        if g2p_en:
            if not cls.g2p_en:
                cls.g2p_en = g2p_en.G2p()
            phones = cls.g2p_en(word)
            _log.debug("generated pronunciation with g2p_en for %r: %r" % (word, phones))
            return phones

        else:
            files = {'wordfile': ('wordfile', word)}
            req = requests.post('http://www.speech.cs.cmu.edu/cgi-bin/tools/logios/lextool.pl', files=files)
            match = re.search(r'<!-- DICT (.*)  -->', req.text)
            if match:
                url = match.group(1)
                req = requests.get(url)
                results = req.text.split()
                assert results[0].lower() == word
                phones = results[1:]
                _log.debug("generated pronunciation with cloud-cmudict for %r: %r" % (word, phones))
                return phones

        raise KaldiError("cannot generate word pronunciation")


########################################################################################################################

class Model(object):
    def __init__(self, model_dir):
        self.model_dir = os.path.join(model_dir, '')

        touch(os.path.join(self.model_dir, 'user_lexicon.txt'))
        self.files_dict = {
            'words.txt': find_file(self.model_dir, 'words.txt'),
            'phones.txt': find_file(self.model_dir, 'phones.txt'),
            'align_lexicon.int': find_file(model_dir, 'align_lexicon.int'),
            'disambig.int': find_file(self.model_dir, 'disambig.int'),
            'L_disambig.fst': find_file(self.model_dir, 'L_disambig.fst'),
            'tree': find_file(self.model_dir, 'tree'),
            '1.mdl': find_file(self.model_dir, '1.mdl'),
            'final.mdl': find_file(self.model_dir, 'final.mdl'),
            'g.irelabel': find_file(self.model_dir, 'g.irelabel'),  # otf
            'user_lexicon.txt': find_file(self.model_dir, 'user_lexicon.txt'),
            'lexiconp_disambig.txt': find_file(self.model_dir, 'lexiconp_disambig.txt'),
        }
        self.files_dict.update({ k.replace('.', '_'): v for k, v in self.files_dict.items() })  # for named placeholder access in str.format()

        self.phone_to_int_dict = { phone: i for phone, i in load_symbol_table(self.files_dict['phones.txt']) }
        self.nonterm_words_offset = symbol_table_lookup(self.files_dict['words.txt'], '#nonterm_begin')

    def add_word(self, word, phones=None):
        word = word.strip().lower()
        if phones is None:
            phones = Lexicon.generate_pronunciation(word)
        phones = Lexicon.cmu_to_xsampa(phones)
        entry = ' '.join([word] + phones)

        # If not already in user_lexicon, add it and regenerate
        with open(self.files_dict['user_lexicon.txt'], 'rb') as file:
            entry_tokens = entry.split()
            for line in file:
                line_tokens = line.split()
                if line_tokens == entry_tokens:
                    _log.warning("word & pronunciation already in user_lexicon")
                    return phones
                if line_tokens[0] == word:
                    _log.warning("word (with different pronunciation) already in user_lexicon")
        with open(self.files_dict['user_lexicon.txt'], 'ab') as file:
            file.write(entry + '\n')
        self.generate_lexicon_files()

        return phones

    def generate_lexicon_files(self):
        max_word_id = max(word_id for word, word_id in load_symbol_table(base_filepath(self.files_dict['words.txt'])) if word_id < self.nonterm_words_offset)

        entries = []
        with open(self.files_dict['user_lexicon.txt'], 'rb') as user_lexicon:
            for line in user_lexicon:
                tokens = line.split()
                if len(tokens) >= 2:
                    word, phones = tokens[0], tokens[1:]
                    phones = Lexicon.make_position_dependent(phones)
                    max_word_id += 1
                    entries.append((word, max_word_id, phones))

        def generate_file(filename, write_func):
            filepath = self.files_dict[filename]
            with open(base_filepath(filepath), 'rb') as file:
                base_data = file.read()
            with open(filepath, 'wb') as file:
                file.write(base_data)
                for word, word_id, phones in entries:
                    file.write(write_func(word, word_id, phones) + '\n')

        generate_file('words.txt', lambda word, word_id, phones:
            str_space_join([word, word_id]))
        generate_file('align_lexicon.int', lambda word, word_id, phones:
            str_space_join([word_id, word_id] + [str(self.phone_to_int_dict[phone]) for phone in phones]))
        generate_file('lexiconp_disambig.txt', lambda word, word_id, phones:
            '%s\t1.0 %s' % (word, ' '.join(phones)))


def convert_generic_model_to_agf(src_dir, model_dir):
    filenames = [
        'words.txt',
        'phones.txt',
        'align_lexicon.int',
        'disambig.int',
        # 'L_disambig.fst',
        'tree',
        'final.mdl',
        'lexiconp.txt',
        'word_boundary.txt',
        'optional_silence.txt',
        'silence.txt',
        'nonsilence.txt',
        'wdisambig_phones.int',
        'wdisambig_words.int',
        'mfcc_hires.conf',
        'mfcc.conf',
        'ivector_extractor.conf',
        'splice.conf',
        'online_cmvn.conf',
        'final.mat',
        'global_cmvn.stats',
        'final.dubm',
        'final.ie',
    ]
    nonterminals = list(Compiler.nonterminals)

    for filename in filenames:
        path = find_file(src_dir, filename)
        if path is None:
            _log.error("cannot find %r in %r", filename, model_dir)
            continue
        _log.info("copying %r to %r", path, model_dir)
        shutil.copy(path, model_dir)

    _log.info("converting %r in %r", 'phones.txt', model_dir)
    lines, highest_symbol = augment_phones_txt.read_phones_txt(os.path.join(model_dir, 'phones.txt'))
    augment_phones_txt.write_phones_txt(lines, highest_symbol, nonterminals, os.path.join(model_dir, 'phones.txt'))

    _log.info("converting %r in %r", 'words.txt', model_dir)
    lines, highest_symbol = augment_words_txt.read_words_txt(os.path.join(model_dir, 'words.txt'))
    # FIXME: leave space for adding words later
    augment_words_txt.write_words_txt(lines, highest_symbol, nonterminals, os.path.join(model_dir, 'words.txt'))

    with open(os.path.join(model_dir, 'nonterminals.txt'), 'wb') as f:
        f.writelines(nonterm + '\n' for nonterm in nonterminals)

    # add nonterminals to align_lexicon.int
    
    # fix L_disambig.fst: construct lexiconp_disambig.txt ...


########################################################################################################################

def str_space_join(iterable):
    return ' '.join(str(elem) for elem in iterable)

def base_filepath(filepath):
    root, ext = os.path.splitext(filepath)
    return root + '.base' + ext

def verify_files_exist(*filenames):
    return False
