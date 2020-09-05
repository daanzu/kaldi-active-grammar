#
# This file is part of kaldi-active-grammar.
# (c) Copyright 2019 by David Zurow
# Licensed under the AGPL-3.0; see LICENSE.txt file.
#

_name = 'kaldi_active_grammar'
__version__ = '1.8.0'
# __dev_version__ = __version__ + '.dev0'
REQUIRED_MODEL_VERSION = '0.5.0'

import logging
_log = logging.getLogger('kaldi')
# _handler = logging.NullHandler()
# _log.addHandler(_handler)

class KaldiError(Exception):
    pass

from .compiler import Compiler, KaldiRule
from .model import Model
from .wrapper import KaldiAgfNNet3Decoder, KaldiPlainNNet3Decoder
from .wfst import WFST
from .plain_dictation import PlainDictationRecognizer
from .utils import disable_donation_message
