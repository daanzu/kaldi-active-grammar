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

    def __init__(self, model_dir=None, tmp_dir=None):
        self.model = Model(model_dir, tmp_dir)
        self.decoder = KaldiPlainNNet3Decoder(self.model.model_dir, self.model.tmp_dir)

    def decode_full_utterance(self, frames):
        self.decoder.decode(frames, True)
        output_str, likelihood = self.decoder.get_output()
        return (output_str, likelihood)

    def decode_full_utterance_chunkwise(self, frames):
        chunk_size = 2 * 16000 / 50
        for i in range(0, len(frames), chunk_size):
            is_last = bool(i+chunk_size >= len(frames))
            self.decoder.decode(frames[i : i+chunk_size], is_last)
        output_str, likelihood = self.decoder.get_output()
        return (output_str, likelihood)
