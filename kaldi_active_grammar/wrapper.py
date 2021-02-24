#
# This file is part of kaldi-active-grammar.
# (c) Copyright 2019 by David Zurow
# Licensed under the AGPL-3.0; see LICENSE.txt file.
#

"""
Wrapper classes for Kaldi
"""

import argparse, json, os.path, sys
from io import open, StringIO

from six.moves import zip
import numpy as np

from . import _log, KaldiError
from .ffi import FFIObject, _ffi, decode as de, encode as en
from .utils import clock, find_file, show_donation_message, symbol_table_lookup
from .wfst import NativeWFST
import kaldi_active_grammar.defaults as defaults

_log = _log.getChild('wrapper')
_log_library = _log.getChild('library')


########################################################################################################################

class KaldiDecoderBase(FFIObject):
    """docstring for KaldiDecoderBase"""

    def __init__(self):
        super(KaldiDecoderBase, self).__init__()

        show_donation_message()

        self.sample_rate = 16000
        self.num_channels = 1
        self.bytes_per_kaldi_frame = self.kaldi_frame_num_to_audio_bytes(1)

        self._reset_decode_time()

    def _reset_decode_time(self):
        self._decode_time = 0
        self._decode_real_time = 0
        self._decode_times = []

    def _start_decode_time(self, num_frames):
        self.decode_start_time = clock()
        self._decode_real_time += 1000.0 * num_frames / self.sample_rate

    def _stop_decode_time(self, finalize=False):
        this = (clock() - self.decode_start_time) * 1000.0
        self._decode_time += this
        self._decode_times.append(this)
        if finalize:
            rtf = 1.0 * self._decode_time / self._decode_real_time if self._decode_real_time != 0 else float('nan')
            pct = 100.0 * this / self._decode_time if self._decode_time != 0 else 100
            _log.log(15, "decoded at %.2f RTF, for %d ms audio, spending %d ms, of which %d ms (%.0f%%) in finalization",
                rtf, self._decode_real_time, self._decode_time, this, pct)
            _log.log(13, "    decode times: %s", ' '.join("%d" % t for t in self._decode_times))
            self._reset_decode_time()

    def kaldi_frame_num_to_audio_bytes(self, kaldi_frame_num):
        kaldi_frame_length_ms = 30
        sample_size_bytes = 2 * self.num_channels
        return int(kaldi_frame_num * kaldi_frame_length_ms * self.sample_rate / 1000 * sample_size_bytes)

    def audio_bytes_to_s(self, audio_bytes):
        sample_size_bytes = 2 * self.num_channels
        return 1.0 * audio_bytes // sample_size_bytes / self.sample_rate


########################################################################################################################

class KaldiGmmDecoder(KaldiDecoderBase):
    """docstring for KaldiGmmDecoder"""

    _library_header_text = """
        void* gmm__init(float beam, int32_t max_active, int32_t min_active, float lattice_beam,
            char* word_syms_filename_cp, char* fst_in_str_cp, char* config_cp);
        bool gmm__decode(void* model_vp, float samp_freq, int32_t num_frames, float* frames, bool finalize);
        bool gmm__get_output(void* model_vp, char* output, int32_t output_length, double* likelihood_p);
    """

    def __init__(self, graph_dir=None, words_file=None, graph_file=None, model_conf_file=None):
        super(KaldiGmmDecoder, self).__init__()

        if words_file is None and graph_dir is not None: words_file = graph_dir + r"graph\words.txt"
        if graph_file is None and graph_dir is not None: graph_file = graph_dir + r"graph\HCLG.fst"
        self.words_file = os.path.normpath(words_file)
        self.graph_file = os.path.normpath(graph_file)
        self.model_conf_file = os.path.normpath(model_conf_file)
        self._model = self._lib.gmm__init(7.0, 7000, 200, 8.0, words_file, graph_file, model_conf_file)
        if not self._model: raise KaldiError("failed gmm__init")
        self.sample_rate = 16000

    def decode(self, frames, finalize, grammars_activity=None):
        if not isinstance(frames, np.ndarray): frames = np.frombuffer(frames, np.int16)
        frames = frames.astype(np.float32)
        frames_char = _ffi.from_buffer(frames)
        frames_float = _ffi.cast('float *', frames_char)

        self._start_decode_time(len(frames))
        result = self._lib.gmm__decode(self._model, self.sample_rate, len(frames), frames_float, finalize)
        self._stop_decode_time(finalize)

        if not result:
            raise RuntimeError("decoding error")
        return finalize

    def get_output(self, output_max_length=4*1024):
        output_p = _ffi.new('char[]', output_max_length)
        likelihood_p = _ffi.new('double *')
        result = self._lib.gmm__get_output(self._model, output_p, output_max_length, likelihood_p)
        output_str = _ffi.string(output_p)
        info = {
            'likelihood': likelihood_p[0],
        }
        return output_str, info


########################################################################################################################

class KaldiOtfGmmDecoder(KaldiDecoderBase):
    """docstring for KaldiOtfGmmDecoder"""

    _library_header_text = """
        void* gmm_otf__init(float beam, int32_t max_active, int32_t min_active, float lattice_beam,
            char* word_syms_filename_cp, char* config_cp,
            char* hcl_fst_filename_cp, char** grammar_fst_filenames_cp, int32_t grammar_fst_filenames_len);
        bool gmm_otf__add_grammar_fst(void* model_vp, char* grammar_fst_filename_cp);
        bool gmm_otf__decode(void* model_vp, float samp_freq, int32_t num_frames, float* frames, bool finalize,
            bool* grammars_activity, int32_t grammars_activity_size);
        bool gmm_otf__get_output(void* model_vp, char* output, int32_t output_length, double* likelihood_p);
    """

    def __init__(self, graph_dir=None, words_file=None, model_conf_file=None, hcl_fst_file=None, grammar_fst_files=None):
        super(KaldiOtfGmmDecoder, self).__init__()

        if words_file is None and graph_dir is not None: words_file = graph_dir + r"graph\words.txt"
        if hcl_fst_file is None and graph_dir is not None: hcl_fst_file = graph_dir + r"graph\HCLr.fst"
        if grammar_fst_files is None and graph_dir is not None: grammar_fst_files = [graph_dir + r"graph\Gr.fst"]
        self.words_file = os.path.normpath(words_file)
        self.model_conf_file = os.path.normpath(model_conf_file)
        self.hcl_fst_file = os.path.normpath(hcl_fst_file)
        grammar_fst_filenames_cps = [_ffi.new('char[]', os.path.normpath(f)) for f in grammar_fst_files]
        grammar_fst_filenames_cp = _ffi.new('char*[]', grammar_fst_filenames_cps)
        self._model = self._lib.gmm_otf__init(7.0, 7000, 200, 8.0, words_file, model_conf_file,
            hcl_fst_file, _ffi.cast('char**', grammar_fst_filenames_cp), len(grammar_fst_files))
        if not self._model: raise KaldiError("failed gmm_otf__init")
        self.sample_rate = 16000
        self.num_grammars = len(grammar_fst_files)

    def add_grammar_fst(self, grammar_fst_file):
        grammar_fst_file = os.path.normpath(grammar_fst_file)
        _log.log(8, "%s: adding grammar_fst_file: %s", self, grammar_fst_file)
        result = self._lib.gmm_otf__add_grammar_fst(self._model, grammar_fst_file)
        if not result:
            raise KaldiError("error adding grammar")
        self.num_grammars += 1

    def decode(self, frames, finalize, grammars_activity=None):
        # grammars_activity = [True] * self.num_grammars
        # grammars_activity = np.random.choice([True, False], len(grammars_activity)).tolist(); print grammars_activity; time.sleep(5)
        if grammars_activity is None: grammars_activity = []
        else: _log.debug("decode: grammars_activity = %s", ''.join('1' if a else '0' for a in grammars_activity))
        # if len(grammars_activity) != self.num_grammars:
        #     raise KaldiError("wrong len(grammars_activity)")

        if not isinstance(frames, np.ndarray): frames = np.frombuffer(frames, np.int16)
        frames = frames.astype(np.float32)
        frames_char = _ffi.from_buffer(frames)
        frames_float = _ffi.cast('float *', frames_char)

        self._start_decode_time(len(frames))
        result = self._lib.gmm_otf__decode(self._model, self.sample_rate, len(frames), frames_float, finalize,
            grammars_activity, len(grammars_activity))
        self._stop_decode_time(finalize)

        if not result:
            raise KaldiError("decoding error")
        return finalize

    def get_output(self, output_max_length=4*1024):
        output_p = _ffi.new('char[]', output_max_length)
        likelihood_p = _ffi.new('double *')
        result = self._lib.gmm_otf__get_output(self._model, output_p, output_max_length, likelihood_p)
        output_str = _ffi.string(output_p)
        info = {
            'likelihood': likelihood_p[0],
        }
        return output_str, info


########################################################################################################################

class KaldiNNet3Decoder(KaldiDecoderBase):
    """ Abstract base class for nnet3 decoders. """

    _library_header_text = """
        DRAGONFLY_API bool nnet3_base__load_lexicon(void* model_vp, char* word_syms_filename_cp, char* word_align_lexicon_filename_cp);
        DRAGONFLY_API bool nnet3_base__save_adaptation_state(void* model_vp);
        DRAGONFLY_API bool nnet3_base__reset_adaptation_state(void* model_vp);
        DRAGONFLY_API bool nnet3_base__get_word_align(void* model_vp, int32_t* times_cp, int32_t* lengths_cp, int32_t num_words);
        DRAGONFLY_API bool nnet3_base__decode(void* model_vp, float samp_freq, int32_t num_samples, float* samples, bool finalize, bool save_adaptation_state);
        DRAGONFLY_API bool nnet3_base__get_output(void* model_vp, char* output, int32_t output_max_length,
                float* likelihood_p, float* am_score_p, float* lm_score_p, float* confidence_p, float* expected_error_rate_p);
        DRAGONFLY_API bool nnet3_base__set_lm_prime_text(void* model_vp, char* prime_cp);
    """

    def __init__(self, model_dir, tmp_dir, words_file=None, word_align_lexicon_file=None, max_num_rules=None, save_adaptation_state=False):
        super(KaldiNNet3Decoder, self).__init__()

        model_dir = os.path.normpath(model_dir)
        if words_file is None: words_file = find_file(model_dir, 'words.txt')
        if word_align_lexicon_file is None: word_align_lexicon_file = find_file(model_dir, 'align_lexicon.int', required=False)
        mfcc_conf_file = find_file(model_dir, 'mfcc_hires.conf')
        if mfcc_conf_file is None: mfcc_conf_file = find_file(model_dir, 'mfcc.conf')  # FIXME: warning?
        model_file = find_file(model_dir, 'final.mdl')

        self.model_dir = model_dir
        self.words_file = os.path.normpath(words_file)
        self.word_align_lexicon_file = os.path.normpath(word_align_lexicon_file) if word_align_lexicon_file is not None else None
        self.mfcc_conf_file = os.path.normpath(mfcc_conf_file)
        self.model_file = os.path.normpath(model_file)
        self.ie_config = self._read_ie_conf_file(model_dir, find_file(model_dir, 'ivector_extractor.conf'))
        self.verbosity = (10 - _log_library.getEffectiveLevel()) if _log_library.isEnabledFor(10) else -1
        self.max_num_rules = int(max_num_rules) if max_num_rules is not None else None
        self._saving_adaptation_state = save_adaptation_state

        self.config_dict = {
            'model_dir': self.model_dir,
            'mfcc_config_filename': self.mfcc_conf_file,
            'ivector_extraction_config_json': self.ie_config,
            'model_filename': self.model_file,
            'word_syms_filename': self.words_file,
            'word_align_lexicon_filename': self.word_align_lexicon_file or '',
            }
        if self.max_num_rules is not None: self.config_dict.update(max_num_rules=self.max_num_rules)

    def _read_ie_conf_file(self, model_dir, old_filename, search=True):
        """ Read ivector_extractor.conf file, converting relative paths to absolute paths for current configuration, returning dict of config. """
        options_with_path = {
            '--splice-config':      'conf/splice.conf',
            '--cmvn-config':        'conf/online_cmvn.conf',
            '--lda-matrix':         'ivector_extractor/final.mat',
            '--global-cmvn-stats':  'ivector_extractor/global_cmvn.stats',
            '--diag-ubm':           'ivector_extractor/final.dubm',
            '--ivector-extractor':  'ivector_extractor/final.ie',
        }
        def convert_path(key, value):
            if not search:
                return os.path.join(model_dir, options_with_path[key])
            else:
                return find_file(model_dir, os.path.basename(options_with_path[key]), required=True)
        options_converters = {
            '--splice-config':          convert_path,
            '--cmvn-config':            convert_path,
            '--lda-matrix':             convert_path,
            '--global-cmvn-stats':      convert_path,
            '--diag-ubm':               convert_path,
            '--ivector-extractor':      convert_path,
            '--ivector-period':         lambda key, value: (float(value) if '.' in value else int(value)),
            '--max-count':              lambda key, value: (float(value) if '.' in value else int(value)),
            '--max-remembered-frames':  lambda key, value: (float(value) if '.' in value else int(value)),
            '--min-post':               lambda key, value: (float(value) if '.' in value else int(value)),
            '--num-gselect':            lambda key, value: (float(value) if '.' in value else int(value)),
            '--posterior-scale':        lambda key, value: (float(value) if '.' in value else int(value)),
            '--online-cmvn-iextractor': lambda key, value: (True if value in ['true'] else False),
        }
        config = dict()
        with open(old_filename, 'r', encoding='utf-8') as old_file:
            for line in old_file:
                key, value = line.strip().split('=', 1)
                value = options_converters[key](key, value)
                assert key.startswith('--')
                key = key[2:]
                config[key] = value
        return config

    saving_adaptation_state = property(lambda self: self._saving_adaptation_state, doc="Whether currently to save updated adaptation state at end of utterance")
    @saving_adaptation_state.setter
    def saving_adaptation_state(self, value): self._saving_adaptation_state = value

    def load_lexicon(self, words_file=None, word_align_lexicon_file=None):
        """ Only necessary when you update the lexicon after initialization. """
        if words_file is None: words_file = self.words_file
        if word_align_lexicon_file is None: word_align_lexicon_file = self.word_align_lexicon_file
        result = self._lib.nnet3_base__load_lexicon(self._model, en(words_file), en(word_align_lexicon_file))
        if not result:
            raise KaldiError("error loading lexicon (%r, %r)" % (words_file, word_align_lexicon_file))

    def save_adaptation_state(self):
        result = self._lib.nnet3_base__save_adaptation_state(self._model)
        if not result:
            raise KaldiError("save_adaptation_state error")

    def reset_adaptation_state(self):
        result = self._lib.nnet3_base__reset_adaptation_state(self._model)
        if not result:
            raise KaldiError("reset_adaptation_state error")

    def get_output(self, output_max_length=4*1024):
        output_p = _ffi.new('char[]', output_max_length)
        likelihood_p = _ffi.new('float *')
        am_score_p = _ffi.new('float *')
        lm_score_p = _ffi.new('float *')
        confidence_p = _ffi.new('float *')
        expected_error_rate_p = _ffi.new('float *')
        result = self._lib.nnet3_base__get_output(self._model, output_p, output_max_length, likelihood_p, am_score_p, lm_score_p, confidence_p, expected_error_rate_p)
        if not result:
            raise KaldiError("get_output error")
        output_str = de(_ffi.string(output_p))
        info = {
            'likelihood': likelihood_p[0],
            'am_score': am_score_p[0],
            'lm_score': lm_score_p[0],
            'confidence': confidence_p[0],
            'expected_error_rate': expected_error_rate_p[0],
        }
        _log.log(7, "get_output: %r %s", output_str, info)
        return output_str, info

    def get_word_align(self, output):
        """Returns tuple of tuples: words (including nonterminals but not eps), each's time (in bytes), and each's length (in bytes)."""
        words = output.split()
        num_words = len(words)
        kaldi_frame_times_p = _ffi.new('int32_t[]', num_words)
        kaldi_frame_lengths_p = _ffi.new('int32_t[]', num_words)
        result = self._lib.nnet3_base__get_word_align(self._model, kaldi_frame_times_p, kaldi_frame_lengths_p, num_words)
        if not result:
            raise KaldiError("get_word_align error")
        times = [kaldi_frame_num * self.bytes_per_kaldi_frame for kaldi_frame_num in kaldi_frame_times_p]
        lengths = [kaldi_frame_num * self.bytes_per_kaldi_frame for kaldi_frame_num in kaldi_frame_lengths_p]
        return tuple(zip(words, times, lengths))

    def set_lm_prime_text(self, prime_text):
        prime_text = prime_text.strip()
        result = self._lib.nnet3_base__set_lm_prime_text(self._model, en(prime_text))
        if not result:
            raise KaldiError("error setting prime text %r" % prime_text)


########################################################################################################################

class KaldiPlainNNet3Decoder(KaldiNNet3Decoder):
    """docstring for KaldiPlainNNet3Decoder"""

    _library_header_text = KaldiNNet3Decoder._library_header_text + """
        DRAGONFLY_API void* nnet3_plain__construct(char* model_dir_cp, char* config_str_cp, int32_t verbosity);
        DRAGONFLY_API bool nnet3_plain__destruct(void* model_vp);
        DRAGONFLY_API bool nnet3_plain__decode(void* model_vp, float samp_freq, int32_t num_samples, float* samples, bool finalize, bool save_adaptation_state);
    """

    def __init__(self, fst_file=None, config=None, **kwargs):
        super(KaldiPlainNNet3Decoder, self).__init__(**kwargs)

        if fst_file is None: fst_file = find_file(self.model_dir, defaults.DEFAULT_PLAIN_DICTATION_HCLG_FST_FILENAME, required=True)
        fst_file = os.path.normpath(fst_file)

        self.config_dict.update({
            'decode_fst_filename': fst_file,
            })
        if config: self.config_dict.update(config)

        _log.debug("config_dict: %s", self.config_dict)
        self._model = self._lib.nnet3_plain__construct(en(self.model_dir), en(json.dumps(self.config_dict)), self.verbosity)
        if not self._model: raise KaldiError("failed nnet3_plain__construct")

    def destroy(self):
        if self._model:
            result = self._lib.nnet3_plain__destruct(self._model)
            if not result:
                raise KaldiError("failed nnet3_plain__destruct")
            self._model = None

    def decode(self, frames, finalize):
        """Continue decoding with given new audio data."""
        if not isinstance(frames, np.ndarray): frames = np.frombuffer(frames, np.int16)
        frames = frames.astype(np.float32)
        frames_char = _ffi.from_buffer(frames)
        frames_float = _ffi.cast('float *', frames_char)

        self._start_decode_time(len(frames))
        result = self._lib.nnet3_plain__decode(self._model, self.sample_rate, len(frames), frames_float, finalize, self._saving_adaptation_state)
        self._stop_decode_time(finalize)

        if not result:
            raise KaldiError("decoding error")
        return finalize


########################################################################################################################

class KaldiAgfNNet3Decoder(KaldiNNet3Decoder):
    """docstring for KaldiAgfNNet3Decoder"""

    _library_header_text = KaldiNNet3Decoder._library_header_text + """
        DRAGONFLY_API void* nnet3_agf__construct(char* model_dir_cp, char* config_str_cp, int32_t verbosity);
        DRAGONFLY_API bool nnet3_agf__destruct(void* model_vp);
        DRAGONFLY_API int32_t nnet3_agf__add_grammar_fst(void* model_vp, void* grammar_fst_cp);
        DRAGONFLY_API int32_t nnet3_agf__add_grammar_fst_file(void* model_vp, char* grammar_fst_filename_cp);
        DRAGONFLY_API bool nnet3_agf__reload_grammar_fst_(void* model_vp, int32_t grammar_fst_index, void* grammar_fst_cp);
        DRAGONFLY_API bool nnet3_agf__reload_grammar_fst_file(void* model_vp, int32_t grammar_fst_index, char* grammar_fst_filename_cp);
        DRAGONFLY_API bool nnet3_agf__remove_grammar_fst(void* model_vp, int32_t grammar_fst_index);
        DRAGONFLY_API bool nnet3_agf__decode(void* model_vp, float samp_freq, int32_t num_frames, float* frames, bool finalize,
            bool* grammars_activity_cp, int32_t grammars_activity_cp_size, bool save_adaptation_state);
    """

    def __init__(self, *, top_fst=None, dictation_fst_file=None, config=None, **kwargs):
        super(KaldiAgfNNet3Decoder, self).__init__(**kwargs)

        phones_file = find_file(self.model_dir, 'phones.txt')
        nonterm_phones_offset = symbol_table_lookup(phones_file, '#nonterm_bos')
        if nonterm_phones_offset is None:
            raise KaldiError("cannot find #nonterm_bos symbol in phones.txt")
        rules_phones_offset = symbol_table_lookup(phones_file, '#nonterm:rule0')
        if rules_phones_offset is None:
            raise KaldiError("cannot find #nonterm:rule0 symbol in phones.txt")
        dictation_phones_offset = symbol_table_lookup(phones_file, '#nonterm:dictation')
        if dictation_phones_offset is None:
            raise KaldiError("cannot find #nonterm:dictation symbol in phones.txt")

        self.config_dict.update({
            'nonterm_phones_offset': nonterm_phones_offset,
            'rules_phones_offset': rules_phones_offset,
            'dictation_phones_offset': dictation_phones_offset,
            'dictation_fst_filename': os.path.normpath(dictation_fst_file) if dictation_fst_file is not None else '',
            })
        if isinstance(top_fst, NativeWFST): self.config_dict.update({'top_fst': int(_ffi.cast("uint64_t", top_fst.compiled_native_obj))})
        elif isinstance(top_fst, str): self.config_dict.update({'top_fst_filename': os.path.normpath(top_fst)})
        else: raise KaldiError("unrecognized top_fst type")
        if config: self.config_dict.update(config)

        _log.debug("config_dict: %s", self.config_dict)
        self._model = self._lib.nnet3_agf__construct(en(self.model_dir), en(json.dumps(self.config_dict)), self.verbosity)
        if not self._model: raise KaldiError("failed nnet3_agf__construct")
        self.num_grammars = 0

    def destroy(self):
        if self._model:
            result = self._lib.nnet3_agf__destruct(self._model)
            if not result:
                raise KaldiError("failed nnet3_agf__destruct")
            self._model = None

    def add_grammar_fst(self, grammar_fst):
        _log.log(8, "%s: adding grammar_fst: %r", self, grammar_fst)
        if isinstance(grammar_fst, NativeWFST):
            grammar_fst_index = self._lib.nnet3_agf__add_grammar_fst(self._model, grammar_fst.compiled_native_obj)
        elif isinstance(grammar_fst, str):
            grammar_fst_index = self._lib.nnet3_agf__add_grammar_fst_file(self._model, en(os.path.normpath(grammar_fst)))
        else: raise KaldiError("unrecognized grammar_fst type")
        if grammar_fst_index < 0:
            raise KaldiError("error adding grammar %r" % grammar_fst)
        assert grammar_fst_index == self.num_grammars, "add_grammar_fst allocated invalid grammar_fst_index"
        self.num_grammars += 1
        return grammar_fst_index

    def reload_grammar_fst(self, grammar_fst_index, grammar_fst):
        _log.debug("%s: reloading grammar_fst_index: #%s %r", self, grammar_fst_index, grammar_fst)
        if isinstance(grammar_fst, NativeWFST):
            result = self._lib.nnet3_agf__reload_grammar_fst(self._model, grammar_fst_index, grammar_fst.compiled_native_obj)
        elif isinstance(grammar_fst, str):
            result = self._lib.nnet3_agf__reload_grammar_fst_file(self._model, grammar_fst_index, en(os.path.normpath(grammar_fst)))
        else: raise KaldiError("unrecognized grammar_fst type")
        if not result:
            raise KaldiError("error reloading grammar #%s %r" % (grammar_fst_index, grammar_fst))

    def remove_grammar_fst(self, grammar_fst_index):
        _log.debug("%s: removing grammar_fst_index: %s", self, grammar_fst_index)
        result = self._lib.nnet3_agf__remove_grammar_fst(self._model, grammar_fst_index)
        if not result:
            raise KaldiError("error removing grammar #%s" % grammar_fst_index)
        self.num_grammars -= 1

    def decode(self, frames, finalize, grammars_activity=None):
        """Continue decoding with given new audio data."""
        # grammars_activity = [True] * self.num_grammars
        # grammars_activity = np.random.choice([True, False], len(grammars_activity)).tolist(); print grammars_activity; time.sleep(5)
        if grammars_activity is None:
            grammars_activity = []
        else:
            # Start of utterance
            _log.log(5, "decode: grammars_activity = %s", ''.join('1' if a else '0' for a in grammars_activity))
            if len(grammars_activity) != self.num_grammars:
                _log.error("wrong len(grammars_activity) = %d != %d = num_grammars" % (len(grammars_activity), self.num_grammars))

        if not isinstance(frames, np.ndarray): frames = np.frombuffer(frames, np.int16)
        frames = frames.astype(np.float32)
        frames_char = _ffi.from_buffer(frames)
        frames_float = _ffi.cast('float *', frames_char)

        self._start_decode_time(len(frames))
        result = self._lib.nnet3_agf__decode(self._model, self.sample_rate, len(frames), frames_float, finalize,
            grammars_activity, len(grammars_activity), self._saving_adaptation_state)
        self._stop_decode_time(finalize)

        if not result:
            raise KaldiError("decoding error")
        return finalize


########################################################################################################################

class KaldiAgfCompiler(FFIObject):

    _library_header_text = """
        DRAGONFLY_API void* nnet3_agf__construct_compiler(char* config_str_cp);
        DRAGONFLY_API bool nnet3_agf__destruct_compiler(void* compiler_vp);
        DRAGONFLY_API void* nnet3_agf__compile_graph(void* compiler_vp, char* config_str_cp, void* grammar_fst_cp, bool return_graph);
        DRAGONFLY_API void* nnet3_agf__compile_graph_text(void* compiler_vp, char* config_str_cp, char* grammar_fst_text_cp, bool return_graph);
        DRAGONFLY_API void* nnet3_agf__compile_graph_file(void* compiler_vp, char* config_str_cp, char* grammar_fst_filename_cp, bool return_graph);
    """

    def __init__(self, config):
        super(KaldiAgfCompiler, self).__init__()
        self._compiler = self._lib.nnet3_agf__construct_compiler(en(json.dumps(config)))
        if not self._compiler: raise KaldiError("failed nnet3_agf__construct_compiler")

    def destroy(self):
        if self._compiler:
            result = self._lib.nnet3_agf__destruct_compiler(self._compiler)
            if not result:
                raise KaldiError("failed nnet3_agf__destruct_compiler")
            self._compiler = None

    def compile_graph(self, config, grammar_fst=None, grammar_fst_text=None, grammar_fst_file=None, return_graph=False):
        if 1 != sum(int(g is not None) for g in [grammar_fst, grammar_fst_text, grammar_fst_file]):
            raise ValueError("must pass exactly one grammar")
        if grammar_fst is not None:
            _log.log(5, "compile_graph:\n    config=%r\n    grammar_fst=%r", config, grammar_fst)
            result = self._lib.nnet3_agf__compile_graph(self._compiler, en(json.dumps(config)), grammar_fst.native_obj, return_graph)
            return result
        if grammar_fst_text is not None:
            _log.log(5, "compile_graph:\n    config=%r\n    grammar_fst_text:\n%s", config, grammar_fst_text)
            result = self._lib.nnet3_agf__compile_graph_text(self._compiler, en(json.dumps(config)), en(grammar_fst_text), return_graph)
            return result
        if grammar_fst_file is not None:
            _log.log(5, "compile_graph:\n    config=%r\n    grammar_fst_file=%r", config, grammar_fst_file)
            result = self._lib.nnet3_agf__compile_graph_file(self._compiler, en(json.dumps(config)), en(grammar_fst_file), return_graph)
            return result


########################################################################################################################

class KaldiLafNNet3Decoder(KaldiNNet3Decoder):
    """docstring for KaldiLafNNet3Decoder"""

    _library_header_text = KaldiNNet3Decoder._library_header_text + """
        DRAGONFLY_API void* nnet3_laf__construct(char* model_dir_cp, char* config_str_cp, int32_t verbosity);
        DRAGONFLY_API bool nnet3_laf__destruct(void* model_vp);
        DRAGONFLY_API int32_t nnet3_laf__add_grammar_fst(void* model_vp, void* grammar_fst_cp);
        DRAGONFLY_API int32_t nnet3_laf__add_grammar_fst_text(void* model_vp, char* grammar_fst_cp);
        DRAGONFLY_API bool nnet3_laf__reload_grammar_fst(void* model_vp, int32_t grammar_fst_index, void* grammar_fst_cp);
        DRAGONFLY_API bool nnet3_laf__remove_grammar_fst(void* model_vp, int32_t grammar_fst_index);
        DRAGONFLY_API bool nnet3_laf__decode(void* model_vp, float samp_freq, int32_t num_frames, float* frames, bool finalize,
            bool* grammars_activity_cp, int32_t grammars_activity_cp_size, bool save_adaptation_state);
    """

    def __init__(self, dictation_fst_file=None, config=None, **kwargs):
        super(KaldiLafNNet3Decoder, self).__init__(**kwargs)

        self.config_dict.update({
            'hcl_fst_filename': find_file(self.model_dir, 'HCLr.fst'),
            'disambig_tids_filename': find_file(self.model_dir, 'disambig_tid.int'),
            'relabel_ilabels_filename': find_file(self.model_dir, 'relabel_ilabels.int'),
            'word_syms_relabeled_filename': find_file(self.model_dir, 'words.relabeled.txt', required=True),
            'dictation_fst_filename': dictation_fst_file or '',
            })
        if config: self.config_dict.update(config)

        _log.debug("config_dict: %s", self.config_dict)
        self._model = self._lib.nnet3_laf__construct(en(self.model_dir), en(json.dumps(self.config_dict)), self.verbosity)
        if not self._model: raise KaldiError("failed nnet3_laf__construct")
        self.num_grammars = 0

    def destroy(self):
        if self._model:
            result = self._lib.nnet3_laf__destruct(self._model)
            if not result:
                raise KaldiError("failed nnet3_laf__destruct")
            self._model = None

    def add_grammar_fst(self, grammar_fst):
        _log.log(8, "%s: adding grammar_fst: %r", self, grammar_fst)
        grammar_fst_index = self._lib.nnet3_laf__add_grammar_fst(self._model, grammar_fst.native_obj)
        if grammar_fst_index < 0:
            raise KaldiError("error adding grammar %r" % grammar_fst)
        assert grammar_fst_index == self.num_grammars, "add_grammar_fst allocated invalid grammar_fst_index"
        self.num_grammars += 1
        return grammar_fst_index

    def add_grammar_fst_text(self, grammar_fst_text):
        assert grammar_fst_text
        _log.log(8, "%s: adding grammar_fst_text: %r", self, grammar_fst_text[:512])
        grammar_fst_index = self._lib.nnet3_laf__add_grammar_fst_text(self._model, en(grammar_fst_text))
        if grammar_fst_index < 0:
            raise KaldiError("error adding grammar %r" % grammar_fst_text[:512])
        assert grammar_fst_index == self.num_grammars, "add_grammar_fst allocated invalid grammar_fst_index"
        self.num_grammars += 1
        return grammar_fst_index

    def reload_grammar_fst(self, grammar_fst_index, grammar_fst):
        _log.debug("%s: reloading grammar_fst_index: #%s %r", self, grammar_fst_index, grammar_fst)
        result = self._lib.nnet3_laf__reload_grammar_fst(self._model, grammar_fst_index, grammar_fst.native_obj)
        if not result:
            raise KaldiError("error reloading grammar #%s %r" % (grammar_fst_index, grammar_fst))

    def remove_grammar_fst(self, grammar_fst_index):
        _log.debug("%s: removing grammar_fst_index: %s", self, grammar_fst_index)
        result = self._lib.nnet3_laf__remove_grammar_fst(self._model, grammar_fst_index)
        if not result:
            raise KaldiError("error removing grammar #%s" % grammar_fst_index)
        self.num_grammars -= 1

    def decode(self, frames, finalize, grammars_activity=None):
        """Continue decoding with given new audio data."""
        # grammars_activity = [True] * self.num_grammars
        # grammars_activity = np.random.choice([True, False], len(grammars_activity)).tolist(); print grammars_activity; time.sleep(5)
        if grammars_activity is None:
            grammars_activity = []
        else:
            # Start of utterance
            _log.log(5, "decode: grammars_activity = %s", ''.join('1' if a else '0' for a in grammars_activity))
            if len(grammars_activity) != self.num_grammars:
                _log.error("wrong len(grammars_activity) = %d != %d = num_grammars" % (len(grammars_activity), self.num_grammars))

        if not isinstance(frames, np.ndarray): frames = np.frombuffer(frames, np.int16)
        frames = frames.astype(np.float32)
        frames_char = _ffi.from_buffer(frames)
        frames_float = _ffi.cast('float *', frames_char)

        self._start_decode_time(len(frames))
        result = self._lib.nnet3_laf__decode(self._model, self.sample_rate, len(frames), frames_float, finalize,
            grammars_activity, len(grammars_activity), self._saving_adaptation_state)
        self._stop_decode_time(finalize)

        if not result:
            raise KaldiError("decoding error")
        return finalize


########################################################################################################################

class KaldiModelBuildUtils(FFIObject):

    _library_header_text = """
        DRAGONFLY_API bool utils__build_L_disambig(char* lexicon_fst_text_cp, char* isymbols_file_cp, char* osymbols_file_cp, char* wdisambig_phones_file_cp, char* wdisambig_words_file_cp, char* fst_out_file_cp);
    """

    @classmethod
    def build_L_disambig(cls, lexicon_fst_text_bytes, phones_file, words_file, wdisambig_phones_file, wdisambig_words_file, fst_out_file):
        cls.init_ffi()
        result = cls._lib.utils__build_L_disambig(lexicon_fst_text_bytes, en(phones_file), en(words_file), en(wdisambig_phones_file), en(wdisambig_words_file), en(fst_out_file))
        if not result: raise KaldiError("failed utils__build_L_disambig")

    @staticmethod
    def make_lexicon_fst(**kwargs):
        try:
            from .kaldi.make_lexicon_fst import main
            old_stdout = sys.stdout
            sys.stdout = output = StringIO()
            main(argparse.Namespace(**kwargs))
            return output.getvalue()
        finally:
            sys.stdout = old_stdout
