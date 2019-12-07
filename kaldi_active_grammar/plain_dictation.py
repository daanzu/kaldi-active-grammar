#
# This file is part of kaldi-active-grammar.
# (c) Copyright 2019 by David Zurow
# Licensed under the AGPL-3.0, with exceptions; see LICENSE.txt file.
#

from . import _log, KaldiError
from .model import Model
from .compiler import Compiler, remove_nonterms_in_text
from .wrapper import KaldiPlainNNet3Decoder, KaldiAgfNNet3Decoder

_log = _log.getChild('plain_dictation')


class PlainDictationRecognizer(object):

    def __init__(self, model_dir=None, tmp_dir=None, fst_file=None):
        """
        Recognizes plain dictation only. If `fst_file` is specified, uses that
        HCLG.fst file; otherwise, uses KaldiAG but dictation only.

        Args:
            model_dir (str): optional path to model directory
            tmp_dir (str): optional path to temporary directory
            fst_file (str): optional path to model's HCLG.fst file to use
        """
        if fst_file:
            self._model = Model(model_dir, tmp_dir)
            self.decoder = KaldiPlainNNet3Decoder(self._model.model_dir, self._model.tmp_dir, fst_file=fst_file)

        else:
            self._compiler = Compiler(model_dir, tmp_dir)
            top_fst = self._compiler.compile_top_fst_dictation_only()
            dictation_fst_file = self._compiler.dictation_fst_filepath
            self.decoder = KaldiAgfNNet3Decoder(model_dir=self._compiler.model_dir, tmp_dir=self._compiler.tmp_dir,
                top_fst_file=top_fst.filepath, dictation_fst_file=dictation_fst_file)


    def decode_utterance(self, samples_data):
        """
        Decodes an entire utterance at once,
        taking as input *samples_data* (*bytes-like* in `int16` format),
        and returning a tuple of (output (*text*), likelihood (*float*)).
        """
        self.decoder.decode(samples_data, True)
        output_str, likelihood = self.decoder.get_output()
        output_str = remove_nonterms_in_text(output_str)
        return (output_str, likelihood)
