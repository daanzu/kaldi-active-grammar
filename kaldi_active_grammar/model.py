#
# This file is part of kaldi-active-grammar.
# (c) Copyright 2019 by David Zurow
# Licensed under the AGPL-3.0, with exceptions; see LICENSE.txt file.
#

import os, re

from .utils import find_file, load_symbol_table
from .compiler import Compiler
from .kaldi import augment_phones_txt, augment_words_txt


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


class Model(object):
    def __init__(self, model_dir):
        self.model_dir = os.path.join(model_dir, '')
        self.phone_to_int_dict = { phone: i for phone, i in load_symbol_table(os.path.join(self.model_dir, 'phones.txt')) }

    def add_word(self, word, phones):
        phones = Lexicon.cmu_to_xsampa(phones)
        phones = Lexicon.make_position_dependent(phones)
        phone_ids = [self.phone_to_int_dict[phone] for phone in phones]


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
