#
# This file is part of kaldi-active-grammar.
# (c) Copyright 2019 by David Zurow
# Licensed under the AGPL-3.0, with exceptions; see LICENSE.txt file.
#

import os, re
from io import open

from six import text_type
import requests

try:
    # g2p_en==2.0.0
    import g2p_en
except ImportError:
    g2p_en = None

from . import _log, KaldiError, DEFAULT_MODEL_DIR, DEFAULT_TMP_DIR_SUFFIX, FILE_CACHE_FILENAME, REQUIRED_MODEL_VERSION
from .utils import ExternalProcess, find_file, load_symbol_table, symbol_table_lookup
import kaldi_active_grammar.utils as utils

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
    def generate_pronunciations(cls, word):
        """returns CMU/arpabet phones"""
        if g2p_en:
            try:
                if not cls.g2p_en:
                    cls.g2p_en = g2p_en.G2p()
                phones = cls.g2p_en(word)
                _log.debug("generated pronunciation with g2p_en for %r: %r" % (word, phones))
                return phones
            except Exception as e:
                _log.exception("generate_pronunciations exception using g2p_en")

        if True:
            try:
                files = {'wordfile': ('wordfile', word)}
                req = requests.post('http://www.speech.cs.cmu.edu/cgi-bin/tools/logios/lextool.pl', files=files)
                req.raise_for_status()
                # FIXME: handle network failures
                match = re.search(r'<!-- DICT (.*)  -->', req.text)
                if match:
                    url = match.group(1)
                    req = requests.get(url)
                    req.raise_for_status()
                    entries = req.text.strip().split('\n')
                    pronunciations = []
                    for entry in entries:
                        tokens = entry.strip().split()
                        assert re.match(word + r'(\(\d\))?', tokens[0], re.I)  # 'SEMI-COLON' or 'SEMI-COLON(2)'
                        phones = tokens[1:]
                        _log.debug("generated pronunciation with cloud-cmudict for %r: %r" % (word, phones))
                        pronunciations.append(phones)
                    return pronunciations
            except Exception as e:
                _log.exception("generate_pronunciations exception accessing www.speech.cs.cmu.edu")

        raise KaldiError("cannot generate word pronunciation")


########################################################################################################################

class Model(object):
    def __init__(self, model_dir=None, tmp_dir=None):
        self.exec_dir = os.path.join(utils.exec_dir, '')
        self.model_dir = os.path.join(model_dir or DEFAULT_MODEL_DIR, '')
        self.tmp_dir = os.path.join(tmp_dir or (os.path.normpath(self.model_dir) + DEFAULT_TMP_DIR_SUFFIX), '')

        if not os.path.isdir(self.exec_dir): raise KaldiError("cannot find exec_dir: %r" % self.exec_dir)
        if not os.path.isdir(self.model_dir): raise KaldiError("cannot find model_dir: %r" % self.model_dir)
        if not os.path.exists(self.tmp_dir):
            _log.warning("%s: creating tmp dir: %r" % (self, self.tmp_dir))
            os.mkdir(self.tmp_dir)
            utils.touch_file(os.path.join(self.tmp_dir, "FILES_ARE_SAFE_TO_DELETE"))
        if os.path.isfile(self.tmp_dir): raise KaldiError("please specify an available tmp_dir, or remove %r" % self.tmp_dir)

        version_file = os.path.join(self.model_dir, 'KAG_VERSION')
        if os.path.isfile(version_file):
            with open(version_file, 'r', encoding='utf-8') as f:
                model_version = f.read().strip()
                if model_version != REQUIRED_MODEL_VERSION:
                    raise KaldiError("invalid model_dir version! please download a compatible model")
        else:
            _log.warning("model_dir has no version information; errors below may indicate an incompatible model")

        utils.touch_file(os.path.join(self.model_dir, 'user_lexicon.txt'))
        self.files_dict = {
            'exec_dir': self.exec_dir,
            'model_dir': self.model_dir,
            'tmp_dir': self.tmp_dir,
            'words.txt': find_file(self.model_dir, 'words.txt'),
            'phones.txt': find_file(self.model_dir, 'phones.txt'),
            'align_lexicon.int': find_file(self.model_dir, 'align_lexicon.int'),
            'disambig.int': find_file(self.model_dir, 'disambig.int'),
            'L_disambig.fst': find_file(self.model_dir, 'L_disambig.fst'),
            'tree': find_file(self.model_dir, 'tree'),
            '1.mdl': find_file(self.model_dir, '1.mdl'),
            'final.mdl': find_file(self.model_dir, 'final.mdl'),
            'g.irelabel': find_file(self.model_dir, 'g.irelabel'),  # otf
            'user_lexicon.txt': find_file(self.model_dir, 'user_lexicon.txt'),
            'left_context_phones.txt': find_file(self.model_dir, 'left_context_phones.txt'),
            'nonterminals.txt': find_file(self.model_dir, 'nonterminals.txt'),
            'wdisambig_phones.int': find_file(self.model_dir, 'wdisambig_phones.int'),
            'wdisambig_words.int': find_file(self.model_dir, 'wdisambig_words.int'),
            'lexiconp_disambig.txt': find_file(self.model_dir, 'lexiconp_disambig.txt'),
        }
        self.files_dict.update({ k: '"%s"' % v for (k, v) in self.files_dict.items() if v and ' ' in v })  # Handle spaces in paths
        self.files_dict.update({ k.replace('.', '_'): v for (k, v) in self.files_dict.items() })  # For named placeholder access in str.format()
        self.fst_cache = utils.FSTFileCache(os.path.join(self.tmp_dir, FILE_CACHE_FILENAME), dependencies_dict=self.files_dict)

        self.phone_to_int_dict = { phone: i for phone, i in load_symbol_table(self.files_dict['phones.txt']) }
        self.nonterm_phones_offset = self.phone_to_int_dict['#nonterm_bos']
        self.nonterm_words_offset = symbol_table_lookup(self.files_dict['words.txt'], '#nonterm_begin')

        # Update files if needed, before loading words
        if not self.fst_cache.file_is_current(self.files_dict['user_lexicon.txt']):
            self.generate_lexicon_files()

        self.load_words(self.files_dict['words.txt'])  # sets self.lexicon_words, self.longest_word

    def load_words(self, words_file=None):
        if words_file is None: words_file = self.files_dict['words.txt']
        _log.debug("loading words from %r", words_file)
        invalid_words = "<eps> !SIL <UNK> #0 <s> </s>".lower().split()

        with open(words_file, 'r', encoding='utf-8') as file:
            word_id_pairs = [line.strip().split() for line in file]
        self.lexicon_words = set([word for word, id in word_id_pairs
            if word.lower() not in invalid_words and not word.startswith('#nonterm')])
        self.longest_word = max(self.lexicon_words, key=len)

        return self.lexicon_words

    def read_user_lexicon(self):
        with open(self.files_dict['user_lexicon.txt'], 'r', encoding='utf-8') as file:
            entries = [line.split() for line in file if line.split()]
            for tokens in entries:
                # word lowercase
                tokens[0] = tokens[0].lower()
        return entries

    def add_word(self, word, phones=None, lazy_compilation=False):
        word = word.strip().lower()
        if phones is None:
            pronunciations = Lexicon.generate_pronunciations(word)
            pronunciations = sum([self.add_word(word, phones, lazy_compilation=True) for phones in pronunciations], [])
            if not lazy_compilation:
                self.generate_lexicon_files()
            return pronunciations
        phones = Lexicon.cmu_to_xsampa(phones)
        new_entry = [word] + phones

        entries = self.read_user_lexicon()
        if any(new_entry == entry for entry in entries):
            _log.warning("word & pronunciation already in user_lexicon")
            return [phones]
        for tokens in entries:
            if word == tokens[0]:
                _log.warning("word (with different pronunciation) already in user_lexicon: %s" % tokens[1:])

        entries.append(new_entry)
        lines = [' '.join(tokens) + '\n' for tokens in entries]
        with open(self.files_dict['user_lexicon.txt'], 'w', encoding='utf-8', newline='\n') as file:
            file.writelines(lines)

        if lazy_compilation:
            self.lexicon_words.add(word)
        else:
            self.generate_lexicon_files()

        return [phones]

    def generate_lexicon_files(self):
        _log.debug("generating lexicon files")
        max_word_id = max(word_id for word, word_id in load_symbol_table(base_filepath(self.files_dict['words.txt'])) if word_id < self.nonterm_words_offset)

        entries = []
        with open(self.files_dict['user_lexicon.txt'], 'r', encoding='utf-8') as user_lexicon:
            for line in user_lexicon:
                tokens = line.split()
                if len(tokens) >= 2:
                    word, phones = tokens[0], tokens[1:]
                    phones = Lexicon.make_position_dependent(phones)
                    max_word_id += 1
                    entries.append((word, max_word_id, phones))

        def generate_file(filename, write_func):
            filepath = self.files_dict[filename]
            with open(base_filepath(filepath), 'r', encoding='utf-8') as file:
                base_data = file.read()
            with open(filepath, 'w', encoding='utf-8', newline='\n') as file:
                file.write(base_data)
                for word, word_id, phones in entries:
                    file.write(write_func(word, word_id, phones) + '\n')

        generate_file('words.txt', lambda word, word_id, phones:
            str_space_join([word, word_id]))
        generate_file('align_lexicon.int', lambda word, word_id, phones:
            str_space_join([word_id, word_id] + [self.phone_to_int_dict[phone] for phone in phones]))
        generate_file('lexiconp_disambig.txt', lambda word, word_id, phones:
            '%s\t1.0 %s' % (word, ' '.join(phones)))

        format = ExternalProcess.get_formatter(self.files_dict)
        command = ExternalProcess.make_lexicon_fst(*format(
            '--left-context-phones={left_context_phones_txt}',
            '--nonterminals={nonterminals_txt}',
            '--sil-prob=0.5',
            '--sil-phone=SIL',
            '--sil-disambig=#14',  # FIXME
            '{lexiconp_disambig_txt}',
        ))
        command |= ExternalProcess.fstcompile(*format(
            '--isymbols={phones_txt}',
            '--osymbols={words_txt}',
            '--keep_isymbols=false',
            '--keep_osymbols=false',
        ))
        command |= ExternalProcess.fstaddselfloops(*format('{wdisambig_phones_int}', '{wdisambig_words_int}'), **ExternalProcess.get_debug_stderr_kwargs(_log))
        command |= ExternalProcess.fstarcsort(*format('--sort_type=olabel'))
        command |= self.files_dict['L_disambig.fst']
        command()

    def reset_user_lexicon(self):
        utils.clear_file(self.files_dict['user_lexicon.txt'])
        self.generate_lexicon_files()


########################################################################################################################

def convert_generic_model_to_agf(src_dir, model_dir):
    from .compiler import Compiler
    if six.PY2:
        from .kaldi import augment_phones_txt_py2 as augment_phones_txt, augment_words_txt_py2 as augment_words_txt
    else:
        from .kaldi import augment_phones_txt, augment_words_txt

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

    with open(os.path.join(model_dir, 'nonterminals.txt'), 'w', encoding='utf-8', newline='\n') as f:
        f.writelines(nonterm + '\n' for nonterm in nonterminals)

    # add nonterminals to align_lexicon.int
    
    # fix L_disambig.fst: construct lexiconp_disambig.txt ...


########################################################################################################################

def str_space_join(iterable):
    return u' '.join(text_type(elem) for elem in iterable)

def base_filepath(filepath):
    root, ext = os.path.splitext(filepath)
    return root + '.base' + ext

def verify_files_exist(*filenames):
    return False
