#
# This file is part of kaldi-active-grammar.
# (c) Copyright 2019 by David Zurow
# Licensed under the AGPL-3.0, with exceptions; see LICENSE.txt file.
#

"""
Wrapper classes for Kaldi
"""

import logging, os.path, time

import numpy as np
from cffi import FFI

from . import _log, KaldiError
from .utils import exec_dir, find_file, platform, symbol_table_lookup

_log = _log.getChild('wrapper')


########################################################################################################################

class KaldiDecoderBase(object):
    """docstring for KaldiDecoderBase"""

    def __init__(self):
        self._reset_decode_time()

    _library_binary = os.path.join(exec_dir, dict(windows='kaldi-dragonfly.dll', linux='libkaldi-dragonfly.so', macos='libkaldi-dragonfly.dylib')[platform])

    def _reset_decode_time(self):
        self._decode_time = 0
        self._decode_real_time = 0
        self._decode_times = []

    def _start_decode_time(self, num_frames):
        self.decode_start_time = time.clock()
        self._decode_real_time += 1000.0 * num_frames / self.sample_rate

    def _stop_decode_time(self, finalize=False):
        this = (time.clock() - self.decode_start_time) * 1000.0
        self._decode_time += this
        self._decode_times.append(this)
        if finalize:
            rtf = 1.0 * self._decode_time / self._decode_real_time
            pct = 100.0 * this / self._decode_time
            _log.debug("decoded at %.2f RTF, for %d ms audio, spending %d ms, of which %d ms (%d%%) in finalization",
                rtf, self._decode_real_time, self._decode_time, this, pct)
            _log.debug("    decode times: %s", ' '.join("%d" % t for t in self._decode_times))
            self._reset_decode_time()


########################################################################################################################

class KaldiGmmDecoder(KaldiDecoderBase):
    """docstring for KaldiGmmDecoder"""

    def __init__(self, graph_dir=None, words_file=None, graph_file=None, model_conf_file=None):
        super(KaldiGmmDecoder, self).__init__()
        self._ffi = FFI()
        self._ffi.cdef("""
            void* init_gmm(float beam, int32_t max_active, int32_t min_active, float lattice_beam,
                char* word_syms_filename_cp, char* fst_in_str_cp, char* config_cp);
            bool decode_gmm(void* model_vp, float samp_freq, int32_t num_frames, float* frames, bool finalize);
            bool get_output_gmm(void* model_vp, char* output, int32_t output_length, double* likelihood_p);
        """)
        self._lib = self._ffi.dlopen(self._library_binary)

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
        frames_char = self._ffi.from_buffer(frames)
        frames_float = self._ffi.cast('float *', frames_char)

        self._start_decode_time(len(frames))
        result = self._lib.decode_gmm(self._model, self.sample_rate, len(frames), frames_float, finalize)
        self._stop_decode_time(finalize)

        if not result:
            raise RuntimeError("decoding error")
        return finalize

    def get_output(self, max_output_length=1024):
        output_p = self._ffi.new('char[]', max_output_length)
        likelihood_p = self._ffi.new('double *')
        result = self._lib.get_output_gmm(self._model, output_p, max_output_length, likelihood_p)
        output_str = self._ffi.string(output_p)
        likelihood = likelihood_p[0]
        return output_str, likelihood


########################################################################################################################

class KaldiOtfGmmDecoder(KaldiDecoderBase):
    """docstring for KaldiOtfGmmDecoder"""

    def __init__(self, graph_dir=None, words_file=None, model_conf_file=None, hcl_fst_file=None, grammar_fst_files=None):
        super(KaldiOtfGmmDecoder, self).__init__()
        self._ffi = FFI()
        self._ffi.cdef("""
            void* init_otf_gmm(float beam, int32_t max_active, int32_t min_active, float lattice_beam,
                char* word_syms_filename_cp, char* config_cp,
                char* hcl_fst_filename_cp, char** grammar_fst_filenames_cp, int32_t grammar_fst_filenames_len);
            bool add_grammar_fst_otf_gmm(void* model_vp, char* grammar_fst_filename_cp);
            bool decode_otf_gmm(void* model_vp, float samp_freq, int32_t num_frames, float* frames, bool finalize,
                bool* grammars_activity, int32_t grammars_activity_size);
            bool get_output_otf_gmm(void* model_vp, char* output, int32_t output_length, double* likelihood_p);
        """)
        self._lib = self._ffi.dlopen(self._library_binary)

        if words_file is None and graph_dir is not None: words_file = graph_dir + r"graph\words.txt"
        if hcl_fst_file is None and graph_dir is not None: hcl_fst_file = graph_dir + r"graph\HCLr.fst"
        if grammar_fst_files is None and graph_dir is not None: grammar_fst_files = [graph_dir + r"graph\Gr.fst"]
        self.words_file = os.path.normpath(words_file)
        self.model_conf_file = os.path.normpath(model_conf_file)
        self.hcl_fst_file = os.path.normpath(hcl_fst_file)
        grammar_fst_filenames_cps = [self._ffi.new('char[]', os.path.normpath(f)) for f in grammar_fst_files]
        grammar_fst_filenames_cp = self._ffi.new('char*[]', grammar_fst_filenames_cps)
        self._model = self._lib.init_otf_gmm(7.0, 7000, 200, 8.0, words_file, model_conf_file,
            hcl_fst_file, self._ffi.cast('char**', grammar_fst_filenames_cp), len(grammar_fst_files))
        self.sample_rate = 16000
        self.num_grammars = len(grammar_fst_files)

    def add_grammar_fst(self, grammar_fst_file):
        grammar_fst_file = os.path.normpath(grammar_fst_file)
        _log.debug("%s: adding grammar_fst_file: %s", self, grammar_fst_file)
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
        frames_char = self._ffi.from_buffer(frames)
        frames_float = self._ffi.cast('float *', frames_char)

        self._start_decode_time(len(frames))
        result = self._lib.decode_otf_gmm(self._model, self.sample_rate, len(frames), frames_float, finalize,
            grammars_activity, len(grammars_activity))
        self._stop_decode_time(finalize)

        if not result:
            raise KaldiError("decoding error")
        return finalize

    def get_output(self, max_output_length=1024):
        output_p = self._ffi.new('char[]', max_output_length)
        likelihood_p = self._ffi.new('double *')
        result = self._lib.get_output_otf_gmm(self._model, output_p, max_output_length, likelihood_p)
        output_str = self._ffi.string(output_p)
        likelihood = likelihood_p[0]
        return output_str, likelihood


########################################################################################################################

class KaldiAgfNNet3Decoder(KaldiDecoderBase):
    """docstring for KaldiAgfNNet3Decoder"""

    def __init__(self, model_dir, tmp_dir, words_file=None, mfcc_conf_file=None, ie_conf_file=None, model_file=None, top_fst_file=None, dictation_fst_file=None,
            save_adaptation_state=True):
        super(KaldiAgfNNet3Decoder, self).__init__()
        self._ffi = FFI()
        self._ffi.cdef("""
            void* init_agf_nnet3(float beam, int32_t max_active, int32_t min_active, float lattice_beam, float acoustic_scale, int32_t frame_subsampling_factor,
                int32_t nonterm_phones_offset, char* word_syms_filename_cp, char* mfcc_config_filename_cp, char* ie_config_filename_cp,
                char* model_filename_cp, char* top_fst_filename_cp, char* dictation_fst_filename_cp);
            bool add_grammar_fst_agf_nnet3(void* model_vp, char* grammar_fst_filename_cp);
            bool decode_agf_nnet3(void* model_vp, float samp_freq, int32_t num_frames, float* frames, bool finalize,
                bool* grammars_activity_cp, int32_t grammars_activity_cp_size, bool save_adaptation_state);
            bool get_output_agf_nnet3(void* model_vp, char* output, int32_t output_length, double* likelihood_p);
            void reset_adaptation_state_agf_nnet3(void* model_vp);
        """)
        self._lib = self._ffi.dlopen(self._library_binary)

        if words_file is None: words_file = find_file(model_dir, 'words.txt')
        if mfcc_conf_file is None: mfcc_conf_file = find_file(model_dir, 'mfcc_hires.conf')
        if mfcc_conf_file is None: mfcc_conf_file = find_file(model_dir, 'mfcc.conf')  # warning?
        if ie_conf_file is None: ie_conf_file = self._convert_ie_conf_file(model_dir,
            find_file(model_dir, 'ivector_extractor.conf'), os.path.join(tmp_dir, 'ivector_extractor.conf'))
        if model_file is None: model_file = find_file(model_dir, 'final.mdl')
        nonterm_phones_offset = symbol_table_lookup(find_file(model_dir, 'phones.txt'), '#nonterm_bos')
        if nonterm_phones_offset is None:
            raise KaldiError("cannot find #nonterm_bos symbol in phones.txt")
        self.words_file = os.path.normpath(words_file)
        self.mfcc_conf_file = os.path.normpath(mfcc_conf_file)
        self.ie_conf_file = os.path.normpath(ie_conf_file)
        self.model_file = os.path.normpath(model_file)
        self.top_fst_file = os.path.normpath(top_fst_file)
        self._model = self._lib.init_agf_nnet3(14.0, 7000, 200, 8.0, 1.0, 3,  # chain: 7.0, 7000, 200, 8.0, 1.0, 3,
            nonterm_phones_offset, words_file, mfcc_conf_file, ie_conf_file, model_file, top_fst_file, dictation_fst_file or "")
        self.sample_rate = 16000
        self.num_grammars = 0
        self._saving_adaptation_state = save_adaptation_state

    saving_adaptation_state = property(lambda self: self._saving_adaptation_state, doc="Whether currently to save updated adaptation state at end of utterance")
    @saving_adaptation_state.setter
    def saving_adaptation_state(self, value): self._saving_adaptation_state = value

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
        with open(old_filename, 'r') as old_file, open(new_filename, 'wb') as new_file:
            for line in old_file:
                key, value = line.strip().split('=', 1)
                if key in options_with_path:
                    if not search:
                        value = os.path.join(model_dir, options_with_path[key])
                    else:
                        value = find_file(model_dir, os.path.basename(options_with_path[key]))
                new_file.write("%s=%s\n" % (key, value))
        return new_filename

    def add_grammar_fst(self, grammar_fst_file):
        grammar_fst_file = os.path.normpath(grammar_fst_file)
        _log.debug("%s: adding grammar_fst_file: %s", self, grammar_fst_file)
        result = self._lib.add_grammar_fst_agf_nnet3(self._model, grammar_fst_file)
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
        frames_char = self._ffi.from_buffer(frames)
        frames_float = self._ffi.cast('float *', frames_char)

        self._start_decode_time(len(frames))
        result = self._lib.decode_agf_nnet3(self._model, self.sample_rate, len(frames), frames_float, finalize,
            grammars_activity, len(grammars_activity), self._saving_adaptation_state)
        self._stop_decode_time(finalize)

        if not result:
            raise KaldiError("decoding error")
        return finalize

    def get_output(self, max_output_length=1024):
        output_p = self._ffi.new('char[]', max_output_length)
        likelihood_p = self._ffi.new('double *')
        result = self._lib.get_output_agf_nnet3(self._model, output_p, max_output_length, likelihood_p)
        output_str = self._ffi.string(output_p)
        likelihood = likelihood_p[0]
        return output_str, likelihood

    def reset_adaptation_state(self):
        self._lib.reset_adaptation_state_agf_nnet3(self._model)
