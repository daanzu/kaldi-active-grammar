#
# This file is part of kaldi-active-grammar.
# (c) Copyright 2019 by David Zurow
# Licensed under the AGPL-3.0, with exceptions; see LICENSE.txt file.
#

import logging, os.path, shutil
import six

from . import _log, _name
from .utils import debug_timer, find_file
from .compiler import Compiler
from .kaldi import augment_phones_txt, augment_words_txt

def compile_dictation_graph(data_dir, tmp_dir, g_filepath=None):
    compiler = Compiler(data_dir, tmp_dir)
    if g_filepath is None: g_filepath = compiler.default_dictation_g_filepath
    with debug_timer(six.print_, "graph compilation", independent=True):
        compiler.compile_dictation_fst(g_filepath)

def convert_generic_model_to_agf(src_dir, data_dir):
    filenames = [
        'words.txt',
        'phones.txt',
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
            _log.error("cannot find %r in %r", filename, data_dir)
            continue
        _log.info("copying %r to %r", path, data_dir)
        shutil.copy(path, data_dir)

    _log.info("converting %r in %r", 'phones.txt', data_dir)
    lines, highest_symbol = augment_phones_txt.read_phones_txt(os.path.join(data_dir, 'phones.txt'))
    augment_phones_txt.write_phones_txt(lines, highest_symbol, nonterminals, os.path.join(data_dir, 'phones.txt'))

    _log.info("converting %r in %r", 'words.txt', data_dir)
    lines, highest_symbol = augment_words_txt.read_words_txt(os.path.join(data_dir, 'words.txt'))
    # FIXME: leave space for adding words later
    augment_words_txt.write_words_txt(lines, highest_symbol, nonterminals, os.path.join(data_dir, 'words.txt'))

    with open(os.path.join(data_dir, 'nonterminals.txt'), 'wb') as f:
        f.writelines(nonterm + '\n' for nonterm in nonterminals)
    
    # fix L_disambig.fst

def main():
    import argparse
    parser = argparse.ArgumentParser(prog='python -m %s' % _name)
    parser.add_argument('-v', '--verbose', action='store_true')
    parser.add_argument('-d', '--data_dir')
    parser.add_argument('-t', '--tmp_dir')
    parser.add_argument('command', choices=['compile_dictation_graph', 'convert_generic_model_to_agf'])
    parser.add_argument('file', nargs='?')
    # parser.add_argument('file')
    # FIXME: helps
    # args = parser.parse_args()
    args, unknown = parser.parse_known_args()
    if not args.file and unknown: args.file = unknown.pop(0)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)
    if args.command == 'compile_dictation_graph':
        if not args.data_dir: parser.error("DATA_DIR required for compile_dictation_graph")
        compile_dictation_graph(args.data_dir, args.tmp_dir, args.file)
    if args.command == 'convert_generic_model_to_agf':
        if not args.data_dir: parser.error("DATA_DIR required for convert_generic_model_to_agf")
        convert_generic_model_to_agf(args.file, args.data_dir)

if __name__ == '__main__':
    main()
