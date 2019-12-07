#
# This file is part of kaldi-active-grammar.
# (c) Copyright 2019 by David Zurow
# Licensed under the AGPL-3.0, with exceptions; see LICENSE.txt file.
#

from . import _log, KaldiError
from .model import Model
from .wrapper import KaldiPlainNNet3Decoder

_log = _log.getChild('plain_dictation')


class PlainDictationRecognizer(object):

    def __init__(self, model_dir=None, tmp_dir=None, fst_file=None):
        """
        Args:
            model_dir (str): optional path to model directory
            tmp_dir (str): optional path to temporary directory
            fst_file (str): optional path to model's HCLG.fst file to use
        """
        self.model = Model(model_dir, tmp_dir)
        self.decoder = KaldiPlainNNet3Decoder(self.model.model_dir, self.model.tmp_dir, fst_file=fst_file)

    def decode_utterance(self, samples_data):
        """
        Decodes an entire utterance at once,
        taking as input *samples_data* (*bytes-like* in `int16` format),
        and returning a tuple of (output (*text*), likelihood (*float*)).
        """
        self.decoder.decode(samples_data, True)
        output_str, likelihood = self.decoder.get_output()
        return (output_str, likelihood)
