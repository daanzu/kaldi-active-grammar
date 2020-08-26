#
# This file is part of kaldi-active-grammar.
# (c) Copyright 2019 by David Zurow
# Licensed under the AGPL-3.0; see LICENSE.txt file.
#

"""
Wrapper classes for Kaldi
"""

import json, logging, os.path, re, time
from io import open

from six import PY3
from six.moves import zip
from cffi import FFI
import numpy as np

from . import _log, KaldiError
from .utils import exec_dir, find_file, platform, show_donation_message, symbol_table_lookup
import kaldi_active_grammar.defaults as defaults

_log = _log.getChild('wrapper')
_log_library = _log.getChild('library')

_ffi = FFI()
_c_source_regex = re.compile(r'(\b(extern|DRAGONFLY_API)\b)|("C")')

def en(text):
    """ For C interop: encode unicode text -> binary utf-8. """
    return text.encode('utf-8')
def de(binary):
    """ For C interop: decode binary utf-8 -> unicode text. """
    return binary.decode('utf-8')

if PY3:
    def clock():
        return time.perf_counter()
else:
    def clock():
        return time.clock()


########################################################################################################################

class KaldiDecoderBase(object):
    """docstring for KaldiDecoderBase"""

    def __init__(self):
        show_donation_message()

        self._lib = _ffi.init_once(self._init_ffi, self.__class__.__name__ + '._init_ffi')

        self.sample_rate = 16000
        self.num_channels = 1
        self.bytes_per_kaldi_frame = self.kaldi_frame_num_to_audio_bytes(1)

        self._reset_decode_time()

    _library_binary_path = os.path.join(exec_dir,
        dict(windows='kaldi-dragonfly.dll', linux='libkaldi-dragonfly.so', macos='libkaldi-dragonfly.dylib')[platform])

    @classmethod
    def _init_ffi(cls):
        _ffi.cdef(_c_source_regex.sub(' ', cls._library_header_text))
        return _ffi.dlopen(cls._library_binary_path)

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
        void* init_gmm(float beam, int32_t max_active, int32_t min_active, float lattice_beam,
            char* word_syms_filename_cp, char* fst_in_str_cp, char* config_cp);
        bool decode_gmm(void* model_vp, float samp_freq, int32_t num_frames, float* frames, bool finalize);
        bool get_output_gmm(void* model_vp, char* output, int32_t output_length, double* likelihood_p);
    """

    def __init__(self, graph_dir=None, words_file=None, graph_file=None, model_conf_file=None):
        super(KaldiGmmDecoder, self).__init__()

        if words_file is None and graph_dir is not None: words_file = graph_dir + r"graph\words.txt"
        if graph_file is None and graph_dir is not None: graph_file = graph_dir + r"graph\HCLG.fst"
        self.words_file = os.path.normpath(words_file)
        self.graph_file = os.path.normpath(graph_file)
        self.model_conf_file = os.path.normpath(model_conf_file)
        self._model = self._lib.init_gmm(7.0, 7000, 200, 8.0, words_file, graph_file, model_conf_file)
        self.sample_rate = 16000

    def decode(self, frames, finalize, grammars_activity=None):
        if not isinstance(frames, np.ndarray): frames = np.frombuffer(frames, np.int16)
        frames = frames.astype(np.float32)
        frames_char = _ffi.from_buffer(frames)
        frames_float = _ffi.cast('float *', frames_char)

        self._start_decode_time(len(frames))
        result = self._lib.decode_gmm(self._model, self.sample_rate, len(frames), frames_float, finalize)
        self._stop_decode_time(finalize)

        if not result:
            raise RuntimeError("decoding error")
        return finalize

    def get_output(self, output_max_length=4*1024):
        output_p = _ffi.new('char[]', output_max_length)
        likelihood_p = _ffi.new('double *')
        result = self._lib.get_output_gmm(self._model, output_p, output_max_length, likelihood_p)
        output_str = _ffi.string(output_p)
        info = {
            'likelihood': likelihood_p[0],
        }
        return output_str, info


########################################################################################################################

class KaldiOtfGmmDecoder(KaldiDecoderBase):
    """docstring for KaldiOtfGmmDecoder"""

    _library_header_text = """
        void* init_otf_gmm(float beam, int32_t max_active, int32_t min_active, float lattice_beam,
            char* word_syms_filename_cp, char* config_cp,
            char* hcl_fst_filename_cp, char** grammar_fst_filenames_cp, int32_t grammar_fst_filenames_len);
        bool add_grammar_fst_otf_gmm(void* model_vp, char* grammar_fst_filename_cp);
        bool decode_otf_gmm(void* model_vp, float samp_freq, int32_t num_frames, float* frames, bool finalize,
            bool* grammars_activity, int32_t grammars_activity_size);
        bool get_output_otf_gmm(void* model_vp, char* output, int32_t output_length, double* likelihood_p);
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
        self._model = self._lib.init_otf_gmm(7.0, 7000, 200, 8.0, words_file, model_conf_file,
            hcl_fst_file, _ffi.cast('char**', grammar_fst_filenames_cp), len(grammar_fst_files))
        self.sample_rate = 16000
        self.num_grammars = len(grammar_fst_files)

    def add_grammar_fst(self, grammar_fst_file):
        grammar_fst_file = os.path.normpath(grammar_fst_file)
        _log.log(8, "%s: adding grammar_fst_file: %s", self, grammar_fst_file)
        result = self._lib.add_grammar_fst_otf_gmm(self._model, grammar_fst_file)
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
        result = self._lib.decode_otf_gmm(self._model, self.sample_rate, len(frames), frames_float, finalize,
            grammars_activity, len(grammars_activity))
        self._stop_decode_time(finalize)

        if not result:
            raise KaldiError("decoding error")
        return finalize

    def get_output(self, output_max_length=4*1024):
        output_p = _ffi.new('char[]', output_max_length)
        likelihood_p = _ffi.new('double *')
        result = self._lib.get_output_otf_gmm(self._model, output_p, output_max_length, likelihood_p)
        output_str = _ffi.string(output_p)
        info = {
            'likelihood': likelihood_p[0],
        }
        return output_str, info


########################################################################################################################

class KaldiNNet3Decoder(KaldiDecoderBase):
    """ Abstract base class for nnet3 decoders. """

    def __init__(self):
        super(KaldiNNet3Decoder, self).__init__()

    def _convert_ie_conf_file(self, model_dir, old_filename, new_filename, search=True):
        """ Rewrite ivector_extractor.conf file, converting relative paths to absolute paths for current configuration. """
        options_with_path = {
            '--splice-config':      'conf/splice.conf',
            '--cmvn-config':        'conf/online_cmvn.conf',
            '--lda-matrix':         'ivector_extractor/final.mat',
            '--global-cmvn-stats':  'ivector_extractor/global_cmvn.stats',
            '--diag-ubm':           'ivector_extractor/final.dubm',
            '--ivector-extractor':  'ivector_extractor/final.ie',
        }
        with open(old_filename, 'r', encoding='utf-8') as old_file, open(new_filename, 'w', encoding='utf-8', newline='\n') as new_file:
            for line in old_file:
                key, value = line.strip().split('=', 1)
                if key in options_with_path:
                    if not search:
                        value = os.path.join(model_dir, options_with_path[key])
                    else:
                        value = find_file(model_dir, os.path.basename(options_with_path[key]), required=True)
                new_file.write("%s=%s\n" % (key, value))
        return new_filename


########################################################################################################################

class KaldiPlainNNet3Decoder(KaldiNNet3Decoder):
    """docstring for KaldiPlainNNet3Decoder"""

    _library_header_text = """
        void* init_plain_nnet3(float beam, int32_t max_active, int32_t min_active, float lattice_beam, float acoustic_scale, int32_t frame_subsampling_factor,
            char* model_dir_cp, char* mfcc_config_filename_cp, char* ie_config_filename_cp, char* model_filename_cp,
            char* word_syms_filename_cp, char* word_align_lexicon_filename_cp, char* fst_filename_cp,
            int32_t verbosity);
        bool decode_plain_nnet3(void* model_vp, float samp_freq, int32_t num_frames, float* frames, bool finalize, bool save_adaptation_state);
        bool get_output_plain_nnet3(void* model_vp, char* output, int32_t output_max_length, double* likelihood_p);
        bool get_word_align_plain_nnet3(void* model_vp, int32_t* times_cp, int32_t* lengths_cp, int32_t num_words);
        bool reset_adaptation_state_plain_nnet3(void* model_vp);
    """

    def __init__(self, model_dir, tmp_dir, words_file=None, word_align_lexicon_file=None, mfcc_conf_file=None, ie_conf_file=None,
            model_file=None, fst_file=None, save_adaptation_state=False):
        super(KaldiPlainNNet3Decoder, self).__init__()

        model_dir = os.path.normpath(model_dir)
        if words_file is None: words_file = find_file(model_dir, 'words.txt')
        if word_align_lexicon_file is None: word_align_lexicon_file = find_file(model_dir, 'align_lexicon.int', required=False)
        if mfcc_conf_file is None: mfcc_conf_file = find_file(model_dir, 'mfcc_hires.conf')
        if mfcc_conf_file is None: mfcc_conf_file = find_file(model_dir, 'mfcc.conf')  # FIXME: warning?
        if ie_conf_file is None: ie_conf_file = self._convert_ie_conf_file(model_dir,
            find_file(model_dir, 'ivector_extractor.conf'), os.path.join(tmp_dir, 'ivector_extractor.conf'))
        if model_file is None: model_file = find_file(model_dir, 'final.mdl')
        if fst_file is None: fst_file = find_file(model_dir, defaults.DEFAULT_PLAIN_DICTATION_HCLG_FST_FILENAME, required=True)

        self.model_dir = model_dir
        self.words_file = os.path.normpath(words_file)
        self.word_align_lexicon_file = os.path.normpath(word_align_lexicon_file) if word_align_lexicon_file is not None else None
        self.mfcc_conf_file = os.path.normpath(mfcc_conf_file)
        self.ie_conf_file = os.path.normpath(ie_conf_file)
        self.model_file = os.path.normpath(model_file)
        self.fst_file = os.path.normpath(fst_file)
        verbosity = (10 - _log_library.getEffectiveLevel()) if _log_library.isEnabledFor(10) else -1

        self._model = self._lib.init_plain_nnet3(
            14.0, 14000, 200, 8.0, 1.0, 3,  # chain: 7.0, 7000, 200, 8.0, 1.0, 3,
            en(model_dir), en(mfcc_conf_file), en(ie_conf_file), en(model_file),
            en(words_file), en(word_align_lexicon_file or u''), en(fst_file),
            verbosity)
        self._saving_adaptation_state = save_adaptation_state

    saving_adaptation_state = property(lambda self: self._saving_adaptation_state, doc="Whether currently to save updated adaptation state at end of utterance")
    @saving_adaptation_state.setter
    def saving_adaptation_state(self, value): self._saving_adaptation_state = value

    def decode(self, frames, finalize):
        """Continue decoding with given new audio data."""
        if not isinstance(frames, np.ndarray): frames = np.frombuffer(frames, np.int16)
        frames = frames.astype(np.float32)
        frames_char = _ffi.from_buffer(frames)
        frames_float = _ffi.cast('float *', frames_char)

        self._start_decode_time(len(frames))
        result = self._lib.decode_plain_nnet3(self._model, self.sample_rate, len(frames), frames_float, finalize, self._saving_adaptation_state)
        self._stop_decode_time(finalize)

        if not result:
            raise KaldiError("decoding error")
        return finalize

    def get_output(self, output_max_length=4*1024):
        output_p = _ffi.new('char[]', output_max_length)
        likelihood_p = _ffi.new('double *')
        result = self._lib.get_output_plain_nnet3(self._model, output_p, output_max_length, likelihood_p)
        if not result:
            raise KaldiError("get_output error")
        output_str = de(_ffi.string(output_p))
        info = {
            'likelihood': likelihood_p[0],
        }
        return output_str, info

    def get_word_align(self, output):
        """Returns list of tuples: words (including nonterminals but not eps), each's time (in bytes), and each's length (in bytes)."""
        words = output.split()
        num_words = len(words)
        kaldi_frame_times_p = _ffi.new('int32_t[]', num_words)
        kaldi_frame_lengths_p = _ffi.new('int32_t[]', num_words)
        result = self._lib.get_word_align_plain_nnet3(self._model, kaldi_frame_times_p, kaldi_frame_lengths_p, num_words)
        if not result:
            raise KaldiError("get_word_align error")
        times = [kaldi_frame_num * self.bytes_per_kaldi_frame for kaldi_frame_num in kaldi_frame_times_p]
        lengths = [kaldi_frame_num * self.bytes_per_kaldi_frame for kaldi_frame_num in kaldi_frame_lengths_p]
        return list(zip(words, times, lengths))

    def reset_adaptation_state(self):
        result = self._lib.reset_adaptation_state_plain_nnet3(self._model)
        if not result:
            raise KaldiError("reset_adaptation_state error")


########################################################################################################################

class KaldiAgfNNet3Decoder(KaldiNNet3Decoder):
    """docstring for KaldiAgfNNet3Decoder"""

    _library_header_text = """
        extern "C" DRAGONFLY_API void* init_agf_nnet3(char* model_dir_cp, char* config_str_cp, int32_t verbosity);
        extern "C" DRAGONFLY_API bool load_lexicon_agf_nnet3(void* model_vp, char* word_syms_filename_cp, char* word_align_lexicon_filename_cp);
        extern "C" DRAGONFLY_API int32_t add_grammar_fst_agf_nnet3(void* model_vp, char* grammar_fst_filename_cp);
        extern "C" DRAGONFLY_API bool reload_grammar_fst_agf_nnet3(void* model_vp, int32_t grammar_fst_index, char* grammar_fst_filename_cp);
        extern "C" DRAGONFLY_API bool remove_grammar_fst_agf_nnet3(void* model_vp, int32_t grammar_fst_index);
        extern "C" DRAGONFLY_API bool decode_agf_nnet3(void* model_vp, float samp_freq, int32_t num_frames, float* frames, bool finalize,
            bool* grammars_activity_cp, int32_t grammars_activity_cp_size, bool save_adaptation_state);
        extern "C" DRAGONFLY_API bool get_output_agf_nnet3(void* model_vp, char* output, int32_t output_max_length,
            float* likelihood_p, float* am_score_p, float* lm_score_p, float* confidence_p, float* expected_error_rate_p);
        extern "C" DRAGONFLY_API bool get_word_align_agf_nnet3(void* model_vp, int32_t* times_cp, int32_t* lengths_cp, int32_t num_words);
        extern "C" DRAGONFLY_API bool save_adaptation_state_agf_nnet3(void* model_vp);
        extern "C" DRAGONFLY_API bool reset_adaptation_state_agf_nnet3(void* model_vp);
    """

    def __init__(self, model_dir, tmp_dir, words_file=None, word_align_lexicon_file=None, mfcc_conf_file=None, ie_conf_file=None,
            model_file=None, top_fst_file=None, dictation_fst_file=None,
            save_adaptation_state=False, config=None):
        super(KaldiAgfNNet3Decoder, self).__init__()

        model_dir = os.path.normpath(model_dir)
        if words_file is None: words_file = find_file(model_dir, 'words.txt')
        if word_align_lexicon_file is None: word_align_lexicon_file = find_file(model_dir, 'align_lexicon.int')
        if mfcc_conf_file is None: mfcc_conf_file = find_file(model_dir, 'mfcc_hires.conf')
        if mfcc_conf_file is None: mfcc_conf_file = find_file(model_dir, 'mfcc.conf')  # FIXME: warning?
        if ie_conf_file is None: ie_conf_file = self._convert_ie_conf_file(model_dir,
            find_file(model_dir, 'ivector_extractor.conf'), os.path.join(tmp_dir, 'ivector_extractor.conf'))
        if model_file is None: model_file = find_file(model_dir, 'final.mdl')

        phones_file = find_file(model_dir, 'phones.txt')
        nonterm_phones_offset = symbol_table_lookup(phones_file, '#nonterm_bos')
        if nonterm_phones_offset is None:
            raise KaldiError("cannot find #nonterm_bos symbol in phones.txt")
        rules_phones_offset = symbol_table_lookup(phones_file, '#nonterm:rule0')
        if rules_phones_offset is None:
            raise KaldiError("cannot find #nonterm:rule0 symbol in phones.txt")
        dictation_phones_offset = symbol_table_lookup(phones_file, '#nonterm:dictation')
        if dictation_phones_offset is None:
            raise KaldiError("cannot find #nonterm:dictation symbol in phones.txt")

        self.model_dir = model_dir
        # FIXME
        self.words_file = os.path.normpath(words_file)
        self.word_align_lexicon_file = os.path.normpath(word_align_lexicon_file) if word_align_lexicon_file is not None else None
        self.mfcc_conf_file = os.path.normpath(mfcc_conf_file)
        self.ie_conf_file = os.path.normpath(ie_conf_file)
        self.model_file = os.path.normpath(model_file)
        self.top_fst_file = os.path.normpath(top_fst_file)
        verbosity = (10 - _log_library.getEffectiveLevel()) if _log_library.isEnabledFor(10) else -1

        config_dict = {
            'model_dir': model_dir,
            'mfcc_config_filename': mfcc_conf_file,
            'ie_config_filename': ie_conf_file,
            'model_filename': model_file,
            'nonterm_phones_offset': nonterm_phones_offset,
            'rules_phones_offset': rules_phones_offset,
            'dictation_phones_offset': dictation_phones_offset,
            'word_syms_filename': words_file,
            'word_align_lexicon_filename': word_align_lexicon_file or '',
            'top_fst_filename': top_fst_file,
            'dictation_fst_filename': dictation_fst_file or '',
            }
        if config: config_dict.update(config)
        config_json = json.dumps(config_dict)

        self._model = self._lib.init_agf_nnet3(en(model_dir), en(config_json), verbosity)
        self.num_grammars = 0
        self._saving_adaptation_state = save_adaptation_state

    saving_adaptation_state = property(lambda self: self._saving_adaptation_state, doc="Whether currently to save updated adaptation state at end of utterance")
    @saving_adaptation_state.setter
    def saving_adaptation_state(self, value): self._saving_adaptation_state = value

    def load_lexicon(self, words_file=None, word_align_lexicon_file=None):
        if words_file is None: words_file = self.words_file
        if word_align_lexicon_file is None: word_align_lexicon_file = self.word_align_lexicon_file
        result = self._lib.load_lexicon_agf_nnet3(self._model, en(words_file), en(word_align_lexicon_file))
        if not result:
            raise KaldiError("error loading lexicon (%r, %r)" % (words_file, word_align_lexicon_file))

    def add_grammar_fst(self, grammar_fst_file):
        grammar_fst_file = os.path.normpath(grammar_fst_file)
        _log.log(8, "%s: adding grammar_fst_file: %r", self, grammar_fst_file)
        grammar_fst_index = self._lib.add_grammar_fst_agf_nnet3(self._model, en(grammar_fst_file))
        if grammar_fst_index < 0:
            raise KaldiError("error adding grammar %r" % grammar_fst_file)
        assert grammar_fst_index == self.num_grammars, "add_grammar_fst allocated invalid grammar_fst_index"
        self.num_grammars += 1
        return grammar_fst_index

    def reload_grammar_fst(self, grammar_fst_index, grammar_fst_file):
        _log.debug("%s: reloading grammar_fst_index: #%s %r", self, grammar_fst_index, grammar_fst_file)
        result = self._lib.reload_grammar_fst_agf_nnet3(self._model, grammar_fst_index, en(grammar_fst_file))
        if not result:
            raise KaldiError("error reloading grammar #%s %r" % (grammar_fst_index, grammar_fst_file))

    def remove_grammar_fst(self, grammar_fst_index):
        _log.debug("%s: removing grammar_fst_index: %s", self, grammar_fst_index)
        result = self._lib.remove_grammar_fst_agf_nnet3(self._model, grammar_fst_index)
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
        result = self._lib.decode_agf_nnet3(self._model, self.sample_rate, len(frames), frames_float, finalize,
            grammars_activity, len(grammars_activity), self._saving_adaptation_state)
        self._stop_decode_time(finalize)

        if not result:
            raise KaldiError("decoding error")
        return finalize

    def get_output(self, output_max_length=4*1024):
        output_p = _ffi.new('char[]', output_max_length)
        likelihood_p = _ffi.new('float *')
        am_score_p = _ffi.new('float *')
        lm_score_p = _ffi.new('float *')
        confidence_p = _ffi.new('float *')
        expected_error_rate_p = _ffi.new('float *')
        result = self._lib.get_output_agf_nnet3(self._model, output_p, output_max_length, likelihood_p, am_score_p, lm_score_p, confidence_p, expected_error_rate_p)
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
        return output_str, info

    def get_word_align(self, output):
        """Returns list of tuples: words (including nonterminals but not eps), each's time (in bytes), and each's length (in bytes)."""
        words = output.split()
        num_words = len(words)
        kaldi_frame_times_p = _ffi.new('int32_t[]', num_words)
        kaldi_frame_lengths_p = _ffi.new('int32_t[]', num_words)
        result = self._lib.get_word_align_agf_nnet3(self._model, kaldi_frame_times_p, kaldi_frame_lengths_p, num_words)
        if not result:
            raise KaldiError("get_word_align error")
        times = [kaldi_frame_num * self.bytes_per_kaldi_frame for kaldi_frame_num in kaldi_frame_times_p]
        lengths = [kaldi_frame_num * self.bytes_per_kaldi_frame for kaldi_frame_num in kaldi_frame_lengths_p]
        return list(zip(words, times, lengths))

    def save_adaptation_state(self):
        result = self._lib.save_adaptation_state_agf_nnet3(self._model)
        if not result:
            raise KaldiError("save_adaptation_state error")

    def reset_adaptation_state(self):
        result = self._lib.reset_adaptation_state_agf_nnet3(self._model)
        if not result:
            raise KaldiError("reset_adaptation_state error")
