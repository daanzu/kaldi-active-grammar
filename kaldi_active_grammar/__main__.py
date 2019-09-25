#
# This file is part of kaldi-active-grammar.
# (c) Copyright 2019 by David Zurow
# Licensed under the AGPL-3.0, with exceptions; see LICENSE.txt file.
#

import logging, os.path, shutil

import six

from . import _name
from .utils import debug_timer
from .compiler import Compiler
from .model import Model, convert_generic_model_to_agf

def main():
    import argparse
    parser = argparse.ArgumentParser(prog='python -m %s' % _name)
    parser.add_argument('-v', '--verbose', action='store_true')
    parser.add_argument('-m', '--model_dir')
    parser.add_argument('-t', '--tmp_dir')
    parser.add_argument('command', choices=[
        'compile_dictation_graph',
        'convert_generic_model_to_agf',
        'add_word',
        'generate_lexicon_files',
        'reset_user_lexicon',
    ])
    # FIXME: helps
    # FIXME: subparsers?
    args, unknown = parser.parse_known_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)

    if args.command == 'compile_dictation_graph':
        compiler = Compiler(args.model_dir, args.tmp_dir)
        g_filepath = compiler.default_dictation_g_filepath if not unknown else unknown[0]
        six.print_("Compiling dictation graph from %r..." % g_filepath)
        with debug_timer(six.print_, "graph compilation", independent=True):
            compiler.compile_dictation_fst(g_filepath)

    if args.command == 'convert_generic_model_to_agf':
        # if not args.model_dir: parser.error("MODEL_DIR required for %s" % args.command)
        file = unknown[0]
        convert_generic_model_to_agf(file, args.model_dir)

    if args.command == 'add_word':
        word = unknown[0]
        phones = unknown[1].split() if len(unknown) >= 2 else None
        pronunciations = Model(args.model_dir).add_word(word, phones)
        for phones in pronunciations:
            six.print_("Added word %r: %r" % (word, ' '.join(phones)))

    if args.command == 'generate_lexicon_files':
        Model(args.model_dir).generate_lexicon_files()
        six.print_("Generated lexicon files")

    if args.command == 'reset_user_lexicon':
        Model(args.model_dir).reset_user_lexicon()
        six.print_("Reset user lexicon")

if __name__ == '__main__':
    main()
