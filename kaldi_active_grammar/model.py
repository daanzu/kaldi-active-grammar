#
# This file is part of kaldi-active-grammar.
# (c) Copyright 2019 by David Zurow
# Licensed under the AGPL-3.0; see LICENSE.txt file.
#

import os, re, shutil
from io import open

from six import PY2, text_type
import requests

try:
    # g2p_en==2.0.0
    import g2p_en
except ImportError:
    g2p_en = None

from . import _log, KaldiError, REQUIRED_MODEL_VERSION
from .utils import ExternalProcess, find_file, load_symbol_table, show_donation_message, symbol_table_lookup
import kaldi_active_grammar.defaults as defaults
import kaldi_active_grammar.utils as utils

_log = _log.getChild('model')


########################################################################################################################

class Lexicon(object):

    def __init__(self, phones):
        """ phones: list of strings, each being a phone """
        self.phone_set = set(self.make_position_independent(phones))

    # XSAMPA phones are 1-letter each, so 2-letter below represent 2 separate phones.
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
    def cmu_to_xsampa_generic(cls, phones, lexicon_phones=None):
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

            new_phone = ("'" if stress else '') + phone
            if (lexicon_phones is not None) and (new_phone in lexicon_phones):
                # Add entire possibly-2-letter phone
                new_phones.append(new_phone)
            else:
                # Add each individual 1-letter phone
                for match in re.finditer(r"('?).", new_phone):
                    new_phones.append(match.group(0))

        return new_phones

    def cmu_to_xsampa(self, phones):
        return self.cmu_to_xsampa_generic(phones, self.phone_set)

    @classmethod
    def make_position_dependent(cls, phones):
        if len(phones) == 0: return []
        elif len(phones) == 1: return [phones[0]+'_S']
        else: return [phones[0]+'_B'] + [phone+'_I' for phone in phones[1:-1]] + [phones[-1]+'_E']

    @classmethod
    def make_position_independent(cls, phones):
        return [re.sub(r'_[SBIE]', '', phone) for phone in phones]

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
                        _log.debug("generated pronunciation with cloud-cmudict for %r: CMU phones are %r" % (word, phones))
                        pronunciations.append(phones)
                    return pronunciations
            except Exception as e:
                _log.exception("generate_pronunciations exception accessing www.speech.cs.cmu.edu")

        raise KaldiError("cannot generate word pronunciation")


########################################################################################################################

class Model(object):
    def __init__(self, model_dir=None, tmp_dir=None):
        show_donation_message()

        self.exec_dir = os.path.join(utils.exec_dir, '')
        self.model_dir = os.path.join(model_dir or defaults.DEFAULT_MODEL_DIR, '')
        self.tmp_dir = os.path.join(tmp_dir or (os.path.normpath(self.model_dir) + defaults.DEFAULT_TMP_DIR_SUFFIX), '')

        if not os.path.isdir(self.exec_dir):
            raise KaldiError("cannot find exec_dir: %r" % self.exec_dir,
                "are you sure you installed kaldi-active-grammar correctly?")
        if not os.path.isdir(self.model_dir):
            raise KaldiError("cannot find model_dir: %r" % self.model_dir)
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

        self.create_missing_files()
        self.check_user_lexicon()

        self.files_dict = {
            'exec_dir': self.exec_dir,
            'model_dir': self.model_dir,
            'tmp_dir': self.tmp_dir,
            'words.txt': find_file(self.model_dir, 'words.txt', default=True),
            'words.base.txt': find_file(self.model_dir, 'words.base.txt', default=True),
            'phones.txt': find_file(self.model_dir, 'phones.txt', default=True),
            'align_lexicon.int': find_file(self.model_dir, 'align_lexicon.int', default=True),
            'align_lexicon.base.int': find_file(self.model_dir, 'align_lexicon.base.int', default=True),
            'disambig.int': find_file(self.model_dir, 'disambig.int', default=True),
            'L_disambig.fst': find_file(self.model_dir, 'L_disambig.fst', default=True),
            'tree': find_file(self.model_dir, 'tree', default=True),
            'final.mdl': find_file(self.model_dir, 'final.mdl', default=True),
            # 'g.irelabel': find_file(self.model_dir, 'g.irelabel', default=True),  # otf
            'user_lexicon.txt': find_file(self.model_dir, 'user_lexicon.txt', default=True),
            'left_context_phones.txt': find_file(self.model_dir, 'left_context_phones.txt', default=True),
            'nonterminals.txt': find_file(self.model_dir, 'nonterminals.txt', default=True),
            'wdisambig_phones.int': find_file(self.model_dir, 'wdisambig_phones.int', default=True),
            'wdisambig_words.int': find_file(self.model_dir, 'wdisambig_words.int', default=True),
            'lexiconp_disambig.txt': find_file(self.model_dir, 'lexiconp_disambig.txt', default=True),
            'lexiconp_disambig.base.txt': find_file(self.model_dir, 'lexiconp_disambig.base.txt', default=True),
        }
        self.files_dict.update({ k: '"%s"' % v for (k, v) in self.files_dict.items() if v and ' ' in v })  # Handle spaces in paths
        self.files_dict.update({ k.replace('.', '_'): v for (k, v) in self.files_dict.items() })  # For named placeholder access in str.format()
        self.fst_cache = utils.FSTFileCache(os.path.join(self.tmp_dir, defaults.FILE_CACHE_FILENAME), dependencies_dict=self.files_dict)

        self.phone_to_int_dict = { phone: i for phone, i in load_symbol_table(self.files_dict['phones.txt']) }
        self.lexicon = Lexicon(self.phone_to_int_dict.keys())
        self.nonterm_phones_offset = self.phone_to_int_dict.get('#nonterm_bos')
        if self.nonterm_phones_offset is None: raise KaldiError("missing nonterms in 'phones.txt'")
        self.nonterm_words_offset = symbol_table_lookup(self.files_dict['words.base.txt'], '#nonterm_begin')
        if self.nonterm_words_offset is None: raise KaldiError("missing nonterms in 'words.base.txt'")

        # Update files if needed, before loading words
        files = ['user_lexicon.txt', 'words.txt', 'align_lexicon.int', 'lexiconp_disambig.txt', 'L_disambig.fst',]
        if self.fst_cache.cache_is_new or not all(self.fst_cache.file_is_current(self.files_dict[file]) for file in files):
            self.generate_lexicon_files()
            self.fst_cache.update_dependencies()
            self.fst_cache.save()

        self.load_words(self.files_dict['words.txt'])  # sets self.lexicon_words, self.longest_word

    def load_words(self, words_file=None):
        if words_file is None: words_file = self.files_dict['words.txt']
        _log.debug("loading words from %r", words_file)
        invalid_words = "<eps> !SIL <UNK> #0 <s> </s>".lower().split()

        with open(words_file, 'r', encoding='utf-8') as file:
            word_id_pairs = [line.strip().split() for line in file]
        self.lexicon_words = set([word for word, id in word_id_pairs
            if word.lower() not in invalid_words and not word.startswith('#nonterm')])
        assert self.lexicon_words, "Empty lexicon from %r" % words_file
        self.longest_word = max(self.lexicon_words, key=len)

        return self.lexicon_words

    def read_user_lexicon(self, filename=None):
        if filename is None: filename = self.files_dict['user_lexicon.txt']
        with open(filename, 'r', encoding='utf-8') as file:
            entries = [line.split() for line in file if line.split()]
            for tokens in entries:
                # word lowercase
                tokens[0] = tokens[0].lower()
        return entries

    def write_user_lexicon(self, entries, filename=None):
        if filename is None: filename = self.files_dict['user_lexicon.txt']
        lines = [' '.join(tokens) + '\n' for tokens in entries]
        lines.sort()
        with open(filename, 'w', encoding='utf-8', newline='\n') as file:
            file.writelines(lines)

    def add_word(self, word, phones=None, lazy_compilation=False):
        word = word.strip().lower()
        if phones is None:
            pronunciations = Lexicon.generate_pronunciations(word)
            pronunciations = sum([self.add_word(word, phones, lazy_compilation=True) for phones in pronunciations], [])
            if not lazy_compilation:
                self.generate_lexicon_files()
            return pronunciations
            # FIXME: refactor this function

        phones = self.lexicon.cmu_to_xsampa(phones)
        new_entry = [word] + phones

        entries = self.read_user_lexicon()
        if any(new_entry == entry for entry in entries):
            _log.warning("word & pronunciation already in user_lexicon")
            return [phones]
        for tokens in entries:
            if word == tokens[0]:
                _log.warning("word (with different pronunciation) already in user_lexicon: %s" % tokens[1:])

        entries.append(new_entry)
        self.write_user_lexicon(entries)

        if lazy_compilation:
            self.lexicon_words.add(word)
        else:
            self.generate_lexicon_files()

        return [phones]

    def create_missing_files(self):
        utils.touch_file(os.path.join(self.model_dir, 'user_lexicon.txt'))
        def check_file(filename, src_filename):
            # Create missing file from its base file
            if not find_file(self.model_dir, filename):
                src = find_file(self.model_dir, src_filename)
                dst = src.replace(src_filename, filename)
                shutil.copyfile(src, dst)
        check_file('words.txt', 'words.base.txt')
        check_file('align_lexicon.int', 'align_lexicon.base.int')
        check_file('lexiconp_disambig.txt', 'lexiconp_disambig.base.txt')

    def check_user_lexicon(self):
        cwd_user_lexicon_filename = os.path.abspath('user_lexicon.txt')
        model_user_lexicon_filename = os.path.abspath(os.path.join(self.model_dir, 'user_lexicon.txt'))
        if (cwd_user_lexicon_filename != model_user_lexicon_filename) and os.path.isfile(cwd_user_lexicon_filename):
            model_user_lexicon_entries = set(tuple(tokens) for tokens in self.read_user_lexicon(filename=model_user_lexicon_filename))
            cwd_user_lexicon_entries = set(tuple(tokens) for tokens in self.read_user_lexicon(filename=cwd_user_lexicon_filename))
            new_user_lexicon_entries = cwd_user_lexicon_entries - model_user_lexicon_entries
            if new_user_lexicon_entries:
                _log.info("adding new user lexicon entries from %r", cwd_user_lexicon_filename)
                entries = model_user_lexicon_entries | cwd_user_lexicon_entries
                self.write_user_lexicon(entries, filename=model_user_lexicon_filename)

    def generate_lexicon_files(self):
        """ Generates: words.txt, align_lexicon.int, lexiconp_disambig.txt, L_disambig.fst """
        _log.info("generating lexicon files")
        max_word_id = max(word_id for word, word_id in load_symbol_table(base_filepath(self.files_dict['words.txt'])) if word_id < self.nonterm_words_offset)

        user_lexicon_entries = []
        with open(self.files_dict['user_lexicon.txt'], 'r', encoding='utf-8') as user_lexicon:
            for line in user_lexicon:
                tokens = line.split()
                if len(tokens) >= 2:
                    word, phones = tokens[0], tokens[1:]
                    phones = Lexicon.make_position_dependent(phones)
                    unknown_phones = [phone for phone in phones if phone not in self.phone_to_int_dict]
                    if unknown_phones:
                        raise KaldiError("word %r has unknown phone(s) %r" % (word, unknown_phones))
                        # _log.critical("word %r has unknown phone(s) %r so using junk phones!!!", word, unknown_phones)
                        # phones = [phone if phone not in self.phone_to_int_dict else self.noise_phone for phone in phones]
                        # continue
                    max_word_id += 1
                    user_lexicon_entries.append((word, max_word_id, phones))

        def generate_file_from_base(filename, write_func):
            filepath = self.files_dict[filename]
            with open(base_filepath(filepath), 'r', encoding='utf-8') as file:
                base_data = file.read()
            with open(filepath, 'w', encoding='utf-8', newline='\n') as file:
                file.write(base_data)
                for word, word_id, phones in user_lexicon_entries:
                    file.write(write_func(word, word_id, phones) + '\n')

        generate_file_from_base('words.txt', lambda word, word_id, phones:
            str_space_join([word, word_id]))
        generate_file_from_base('align_lexicon.int', lambda word, word_id, phones:
            str_space_join([word_id, word_id] + [self.phone_to_int_dict[phone] for phone in phones]))
        generate_file_from_base('lexiconp_disambig.txt', lambda word, word_id, phones:
            '%s\t1.0 %s' % (word, ' '.join(phones)))

        format = ExternalProcess.get_formatter(self.files_dict)
        command = ExternalProcess.make_lexicon_fst(*format(
            '--left-context-phones={left_context_phones_txt}',
            '--nonterminals={nonterminals_txt}',
            '--sil-prob=0.5',
            '--sil-phone=SIL',
            '--sil-disambig=#14',  # FIXME: lookup correct value
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
    if PY2:
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
