#
# This file is part of kaldi-active-grammar.
# (c) Copyright 2019 by David Zurow
# Licensed under the AGPL-3.0; see LICENSE.txt file.
#

from . import _log, KaldiError
from .model import Model
from .compiler import Compiler, remove_nonterms_in_text
from .wrapper import KaldiPlainNNet3Decoder, KaldiAgfNNet3Decoder
from .utils import show_donation_message

_log = _log.getChild('plain_dictation')


class PlainDictationRecognizer(object):

    def __init__(self, model_dir=None, tmp_dir=None, fst_file=None, config=None):
        """
        Recognizes plain dictation only. If `fst_file` is specified, uses that
        HCLG.fst file; otherwise, uses KaldiAG but dictation only.

        Args:
            model_dir (str): optional path to model directory
            tmp_dir (str): optional path to temporary directory
            fst_file (str): optional path to model's HCLG.fst file to use
            config (dict): optional configuration for initialization of decoder
        """
        show_donation_message()

        kwargs = {}
        if config: kwargs['config'] = dict(config)

        if fst_file:
            self._model = Model(model_dir, tmp_dir)
            self.decoder = KaldiPlainNNet3Decoder(model_dir=self._model.model_dir, tmp_dir=self._model.tmp_dir,
                fst_file=fst_file, **kwargs)

        else:
            self._compiler = Compiler(model_dir, tmp_dir, cache_fsts=False)
            top_fst_rule = self._compiler.compile_top_fst_dictation_only()
            dictation_fst_file = self._compiler.dictation_fst_filepath
            self.decoder = KaldiAgfNNet3Decoder(model_dir=self._compiler.model_dir, tmp_dir=self._compiler.tmp_dir,
                top_fst=top_fst_rule.fst_wrapper, dictation_fst_file=dictation_fst_file, **kwargs)


    def decode_utterance(self, samples_data, chunk_size=None):
        """
        Decodes an entire utterance at once,
        taking as input *samples_data* (*bytes-like* in `int16` format),
        and returning a tuple of (output (*text*), likelihood (*float*)).
        Optionally takes *chunk_size* (*int* in number of samples) for decoding.
        """
        if chunk_size:
            chunk_size *= 2  # Compensate for int16 format
            for i in range(0, len(samples_data), chunk_size):
                self.decoder.decode(samples_data[i : i + chunk_size], False)
            self.decoder.decode(bytes(), True)
        else:
            self.decoder.decode(samples_data, True)
        output_str, info = self.decoder.get_output()
        output_str = remove_nonterms_in_text(output_str)
        return (output_str, info)
