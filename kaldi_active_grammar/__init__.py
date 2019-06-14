#
# This file is part of kaldi-active-grammar.
# (c) Copyright 2019 by David Zurow
# Licensed under the AGPL-3.0, with exceptions; see LICENSE.txt file.
#

_name = "kaldi_active_grammar"
__version__ = "0.4.0"
required_model_version = "0.4.0"

import logging
_log = logging.getLogger("kaldi")

class KaldiError(Exception):
    pass

from .utils import FileCache
from .wfst import WFST
from .compiler import Compiler, KaldiRule
from .wrapper import KaldiAgfNNet3Decoder
