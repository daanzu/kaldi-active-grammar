#
# This file is part of kaldi-active-grammar.
# (c) Copyright 2019 by David Zurow
# Licensed under the AGPL-3.0, with exceptions; see LICENSE.txt file.
#

import base64, collections, logging, multiprocessing, os, re, shlex, subprocess
import concurrent.futures
from contextlib import contextmanager
from io import open

from six.moves import range, zip

from . import _log, KaldiError
from .utils import debug_timer, lazy_readonly_property, platform, load_symbol_table, symbol_table_lookup, ExternalProcess
from .wfst import WFST
from .model import Model
import kaldi_active_grammar.cloud as cloud

_log = _log.getChild('compiler')


########################################################################################################################

class KaldiRule(object):

    def __init__(self, compiler, name, nonterm=True, has_dictation=None, is_complex=None):
        """
        :param nonterm: bool whether rule represents a nonterminal in the active-grammar-fst (only False for the top FST?)
        """
        self.compiler = compiler
        self.name = name
        self.nonterm = nonterm
        self.has_dictation = has_dictation
        self.is_complex = is_complex

        # id: matches "nonterm:rule__"; 0-based; can/will change due to rule unloading!
        self.id = int(self.compiler.alloc_rule_id() if nonterm else -1)
        if self.id > self.compiler._max_rule_id: raise KaldiError("KaldiRule id > compiler._max_rule_id")
        if self.id in self.compiler.kaldi_rule_by_id_dict: raise KaldiError("KaldiRule id already in use")
        if self.id >= 0:
            self.compiler.kaldi_rule_by_id_dict[self.id] = self

        # Private/protected
        self._fst_text = None
        self.compiled = False
        self.loaded = False
        self.reloading = False  # KaldiRule is in the process of the reload contextmanager
        self.has_been_loaded = False  # KaldiRule was loaded, then reload() was called & completed, and now it is not currently loaded, and load() we need to call the decoder's reload
        self.destroyed = False  # KaldiRule must not be used/referenced anymore

        # Public
        self.fst = WFST()
        self.filename = None
        self.matcher = None
        self.active = True

    def __repr__(self):
        return "%s(%s, %s)" % (self.__class__.__name__, self.id, self.name)

    path = property(lambda self: self.compiler.tmp_dir)
    filepath = property(lambda self: os.path.join(self.compiler.tmp_dir, self.filename))
    fst_cache = property(lambda self: self.compiler.fst_cache)
    decoder = property(lambda self: self.compiler.decoder)
    pending_compile = property(lambda self: (self in self.compiler.compile_queue) or (self in self.compiler.compile_duplicate_filename_queue))
    pending_load = property(lambda self: self in self.compiler.load_queue)

    def compile(self, lazy=False, duplicate=None):
        if self.destroyed: raise KaldiError("Cannot use a KaldiRule after calling destroy()")
        if not self._fst_text:
            self.fst.normalize_weights()
            self._fst_text = self.fst.get_fst_text()
            self.filename = self.fst_cache.get_fst_filename(self._fst_text)

        if self.fst_cache.fst_is_current(self.filepath):
            # _log.debug("%s: Skipped full compilation thanks to FileCache" % self)
            self.compiled = True
            return self
        else:
            # _log.debug("%s: FileCache useless; has %s not %s" % (self, self.fst_cache.cache.get(self.filepath), self.fst_cache.hash_data(self._fst_text)))
            if duplicate:
                _log.warning("%s was supposed to be a duplicate compile, but was not found in FileCache")

        if lazy:
            if not self.pending_compile:
                if not any(self.filename == kaldi_rule.filename for kaldi_rule in self.compiler.compile_queue if self != kaldi_rule):
                    self.compiler.compile_queue.add(self)
                else:
                    self.compiler.compile_duplicate_filename_queue.add(self)
            return self

        return self.finish_compile()

    def finish_compile(self):
        # Must be thread-safe!
        assert self._fst_text
        _log.debug("%s: Compiling %sstate/%sarc/%sbyte fst.txt file to %s" % (self, self.fst.num_states, self.fst.num_arcs, len(self._fst_text), self.filename))
        assert self.compiler.decoding_framework == 'agf'
        self.compiler._compile_agf_graph(compile=True, nonterm=self.nonterm, input_data=self._fst_text, filename=self.filepath)

        # elif self.compiler.decoding_framework == 'otf':
        #     with open(self.filepath + '.txt', 'wb') as f:
        #         # FIXME: https://stackoverflow.com/questions/2536545/how-to-write-unix-end-of-line-characters-in-windows-using-python/23434608#23434608
        #         f.write(self._fst_text)
        #     self.compiler._compile_otf_graph(filename=self.filepath)

        self._fst_text = None
        self.compiled = True
        with self.fst_cache.lock:
            self.fst_cache.add_fst(self.filepath)
            self.fst_cache.save()
        return self

    def load(self, lazy=False):
        if self.destroyed: raise KaldiError("Cannot use a KaldiRule after calling destroy()")
        if lazy or self.pending_compile:
            self.compiler.load_queue.add(self)
            return self
        assert self.compiled

        if self.has_been_loaded:
            self.decoder.reload_grammar_fst(self.id, self.filepath)
        else:
            grammar_fst_index = self.decoder.add_grammar_fst(self.filepath)
            assert self.id == grammar_fst_index, "add_grammar_fst allocated invalid grammar_fst_index %d for %s" % (grammar_fst_index, self)

        self.loaded = True
        self.has_been_loaded = True
        return self

    @contextmanager
    def reload(self):
        """ Used for modifying a rule in place, e.g. ListRef. """
        if self.destroyed: raise KaldiError("Cannot use a KaldiRule after calling destroy()")

        was_loaded = self.loaded
        self.reloading = True
        self.fst.clear()
        self.compiled = False
        self.loaded = False

        yield

        if self.compiled and was_loaded:
            if not self.loaded:
                self.decoder.reload_grammar_fst(self.id, self.filepath)
                self.loaded = True
        elif was_loaded:  # must be not self.compiled (i.e. the compile during reloading was lazy)
            self.compiler.load_queue.add(self)
        self.reloading = False

    def destroy(self):
        """ Destructor. Unloads rule. The rule should not be used/referenced anymore after calling! """
        if self.destroyed:
            return

        if self.loaded:
            self.decoder.remove_grammar_fst(self.id)
            assert self not in self.compiler.compile_queue
            assert self not in self.compiler.compile_duplicate_filename_queue
            assert self not in self.compiler.load_queue
        else:
            if self in self.compiler.compile_queue: self.compiler.compile_queue.remove(self)
            if self in self.compiler.compile_duplicate_filename_queue: self.compiler.compile_duplicate_filename_queue.remove(self)
            if self in self.compiler.load_queue: self.compiler.load_queue.remove(self)

        # Adjust other kaldi_rules ids down, if above self.id, then rebuild dict
        other_kaldi_rules = list(self.compiler.kaldi_rule_by_id_dict.values())
        other_kaldi_rules.remove(self)
        for kaldi_rule in other_kaldi_rules:
            if kaldi_rule.id > self.id:
                kaldi_rule.id -= 1
        self.compiler.kaldi_rule_by_id_dict = { kaldi_rule.id: kaldi_rule for kaldi_rule in other_kaldi_rules }

        self.compiler.free_rule_id()
        self.destroyed = True


########################################################################################################################

class Compiler(object):

    def __init__(self, model_dir=None, tmp_dir=None, alternative_dictation=None, cloud_dictation_lang='en-US'):
        self.decoding_framework = 'agf'
        assert self.decoding_framework in ('otf', 'agf')
        self.parsing_framework = 'token'
        assert self.parsing_framework in ('text', 'token')
        self._log = _log

        self.model = Model(model_dir, tmp_dir)
        self.cloud_dictation = alternative_dictation
        self.cloud_dictation_lang = cloud_dictation_lang
        self.decoder = None

        self._num_kaldi_rules = 0
        self._max_rule_id = load_symbol_table(self.files_dict['phones.txt'])[-1][1] - symbol_table_lookup(self.files_dict['phones.txt'], '#nonterm:rule0')  # FIXME: inaccuracy
        self._max_rule_id = 999
        self.nonterminals = tuple(['#nonterm:dictation'] + ['#nonterm:rule%i' % i for i in range(self._max_rule_id + 1)])

        self.kaldi_rule_by_id_dict = collections.OrderedDict()  # maps KaldiRule.id -> KaldiRule
        self.compile_queue = set()  # KaldiRule
        self.compile_duplicate_filename_queue = set()  # KaldiRule; queued KaldiRules with a duplicate filename (and thus contents), so can skip compilation
        self.load_queue = set()  # KaldiRule; must maintain same order as order of instantiation!

    exec_dir = property(lambda self: self.model.exec_dir)
    model_dir = property(lambda self: self.model.model_dir)
    tmp_dir = property(lambda self: self.model.tmp_dir)
    files_dict = property(lambda self: self.model.files_dict)
    fst_cache = property(lambda self: self.model.fst_cache)

    num_kaldi_rules = property(lambda self: self._num_kaldi_rules)
    lexicon_words = property(lambda self: self.model.lexicon_words)
    _longest_word = property(lambda self: self.model.longest_word)

    default_dictation_g_filepath = property(lambda self: os.path.join(self.model_dir, 'G_dictation.fst'))
    _dictation_fst_filepath = property(lambda self: os.path.join(self.model_dir, 'Dictation.fst'))

    def alloc_rule_id(self):
        id = self._num_kaldi_rules
        self._num_kaldi_rules += 1
        return id

    def free_rule_id(self):
        id = self._num_kaldi_rules
        self._num_kaldi_rules -= 1
        return id

    ####################################################################################################################
    # Methods for compiling graphs.

    # def _compile_otf_graph(self, **kwargs):
    #     # FIXME: documentation
    #     with debug_timer(self._log.debug, "otf graph compilation"):
    #         format_kwargs = dict(self.files_dict, **kwargs)
    #         run = lambda cmd, **kwargs: run_subprocess(cmd, format_kwargs, "otf graph compilation step", **kwargs)

    #         p1 = run("{exec_dir}fstcompile --isymbols={words_txt} --osymbols={words_txt} {filename}.txt {filename}")
    #         p2 = run("{exec_dir}fstrelabel --relabel_ipairs={g.irelabel} {filename} {filename}")
    #         p3 = run("{exec_dir}fstarcsort {filename} {filename}")
    #         # p4 = run("{exec_dir}fstconvert --fst_type=const {filename} {filename}")

    def _compile_agf_graph(self, compile=False, nonterm=False, input_data=None, input_filename=None, filename=None, **kwargs):
        """
        :param compile: bool whether to compile FST (False if it has already been compiled, like importing dictation FST)
        :param nonterm: bool whether rule represents a nonterminal in the active-grammar-fst (only False for the top FST?)
        """
        # Must be thread-safe!
        # Possible combinations of (compile,nonterm): (True,True) (True,False) (False,True)
        # FIXME: documentation
        with debug_timer(self._log.debug, "agf graph compilation") as get_time_spent:
            verbose_level = 5 if self._log.isEnabledFor(5) else 0
            format_kwargs = dict(self.files_dict, input_filename=input_filename, filename=filename, verbose=verbose_level, **kwargs)
            format_kwargs.update(nonterm_phones_offset=self.model.nonterm_phones_offset)
            format_kwargs.update(words_nonterm_begin=self.model.nonterm_words_offset, words_nonterm_end=self.model.nonterm_words_offset+1)

            if 1:
                # Pipeline-style
                if input_data and input_filename: raise KaldiError("_compile_agf_graph passed both input_data and input_filename")
                elif input_data: input = ExternalProcess.shell.echo(input_data.encode('utf-8'))
                elif input_filename: input = input_filename
                else: raise KaldiError("_compile_agf_graph passed neither input_data nor input_filename")
                compile_command = input
                format = ExternalProcess.get_formatter(format_kwargs)
                args = []

                # if True: (input | ExternalProcess.fstcompile(*format('--isymbols={words_txt}', '--osymbols={words_txt}')) | ExternalProcess.fstinfo | 'stats.log+')()
                # if True: (ExternalProcess.shell.echo(input_data) | ExternalProcess.fstcompile(*format('--isymbols={words_txt}', '--osymbols={words_txt}')) | (filename+'-G'))()

                if compile:
                    compile_command |= ExternalProcess.fstcompile(*format('--isymbols={words_txt}', '--osymbols={words_txt}'))
                    args.extend(['--arcsort-grammar'])
                if nonterm:
                    args.extend(format('--grammar-prepend-nonterm={words_nonterm_begin}'))
                    args.extend(format('--grammar-append-nonterm={words_nonterm_end}'))
                args.extend(format('--nonterm-phones-offset={nonterm_phones_offset}', '--read-disambig-syms={disambig_int}', '--verbose={verbose}',
                    '{tree}', '{final_mdl}', '{L_disambig_fst}', '-', '{filename}'))
                compile_command |= ExternalProcess.compile_graph_agf(*args, **ExternalProcess.get_debug_stderr_kwargs(self._log))
                # compile_command |= ExternalProcess.compile_graph_agf_debug(*args, **kwargs)
                # if len(input_data) >= 1000000:
                #     compile_command |= ExternalProcess.compile_graph_agf_debug(*args, **kwargs)
                # else:
                #     compile_command |= ExternalProcess.compile_graph_agf(*args, **kwargs)
                compile_command()

                # if True: (ExternalProcess.shell.echo('%s -> %s\n' % (len(input_data), get_time_spent())) | ExternalProcess.shell('cat') | 'stats.log+')()

            else:
                # CLI-style
                run = lambda cmd, **kwargs: run_subprocess(cmd, format_kwargs, "agf graph compilation step", format_kwargs_update=dict(input_filename=filename), **kwargs)
                if compile: run("{exec_dir}fstcompile --isymbols={words_txt} --osymbols={words_txt} {input_filename}.txt {filename}")
                # run("cp {input_filename} {filename}-G")
                if compile: run("{exec_dir}fstarcsort --sort_type=ilabel {input_filename} {filename}")
                if nonterm: run("{exec_dir}fstconcat {tmp_dir}nonterm_begin.fst {input_filename} {filename}")
                if nonterm: run("{exec_dir}fstconcat {input_filename} {tmp_dir}nonterm_end.fst {filename}")
                # run("cp {input_filename} {filename}-G")
                run("{exec_dir}compile-graph --nonterm-phones-offset={nonterm_phones_offset} --read-disambig-syms={disambig_int} --verbose={verbose}"
                    + " {tree} {final_mdl} {L_disambig_fst} {input_filename} {filename}")

    # def _compile_base_fsts(self):
    #     filepaths = [self.tmp_dir + filename for filename in ['nonterm_begin.fst', 'nonterm_end.fst']]
    #     if all(self.fst_cache.is_current(filepath) for filepath in filepaths):
    #         return
    #     format_kwargs = dict(self.files_dict)
    #     def run(cmd): subprocess.check_call(cmd.format(**format_kwargs), shell=True)  # FIXME: unsafe shell?
    #     if platform == 'windows':
    #     else:
    #         run("(echo 0 1 #nonterm_begin 0^& echo 1) | {exec_dir}fstcompile.exe --isymbols={words_txt} > {tmp_dir}nonterm_begin.fst")
    #         run("(echo 0 1 #nonterm_end 0^& echo 1) | {exec_dir}fstcompile.exe --isymbols={words_txt} > {tmp_dir}nonterm_end.fst")
    #         run("(echo 0 1 \\#nonterm_begin 0; echo 1) | {exec_dir}fstcompile --isymbols={words_txt} > {tmp_dir}nonterm_begin.fst")
    #         run("(echo 0 1 \\#nonterm_end 0; echo 1) | {exec_dir}fstcompile --isymbols={words_txt} > {tmp_dir}nonterm_end.fst")
    #     for filepath in filepaths:
    #         self.fst_cache.add(filepath)

    def compile_top_fst(self):
        kaldi_rule = KaldiRule(self, 'top', nonterm=False)
        fst = kaldi_rule.fst
        state_initial = fst.add_state(initial=True)
        state_return = fst.add_state()
        state_final = fst.add_state(final=True)
        for i in range(self._max_rule_id + 1):
            # fst.add_arc(state_initial, state_final, '#nonterm:rule'+str(i), olabel=WFST.eps)
            # fst.add_arc(state_initial, state_final, '#nonterm:rule'+str(i))
            fst.add_arc(state_initial, state_return, '#nonterm:rule'+str(i))
        fst.add_arc(state_return, state_final, None, '#nonterm:end')
        kaldi_rule.compile()
        return kaldi_rule

    def _get_dictation_fst_filepath(self):
        if os.path.exists(self._dictation_fst_filepath):
            return self._dictation_fst_filepath
        self._log.error("cannot find dictation fst: %s", self._dictation_fst_filepath)
        # self._log.error("using universal dictation fst")
    dictation_fst_filepath = property(_get_dictation_fst_filepath)

    # def _construct_dictation_states(self, fst, src_state, dst_state, number=(1,None), words=None, start_weight=None):
    #     """
    #     Matches `number` words.
    #     :param number: (0,None) or (1,None) or (1,1), where None is infinity.
    #     """
    #     # unweighted=0.01
    #     if words is None: words = self._lexicon_words
    #     word_probs = self._lexicon_word_probs
    #     backoff_state = fst.add_state()
    #     fst.add_arc(src_state, backoff_state, None, weight=start_weight)
    #     if number[0] == 0:
    #         fst.add_arc(backoff_state, dst_state, None)
    #     for word, prob in word_probs.items():
    #         state = fst.add_state()
    #         fst.add_arc(backoff_state, state, word, weight=prob)
    #         if number[1] == None:
    #             fst.add_arc(state, backoff_state, None)
    #         fst.add_arc(state, dst_state, None)

    def compile_universal_grammar(self, words=None):
        """recognizes any sequence of words"""
        kaldi_rule = KaldiRule(self, 'universal', nonterm=False)
        if words is None: words = self._lexicon_words
        fst = kaldi_rule.fst
        backoff_state = fst.add_state(initial=True, final=True)
        for word in words:
            # state = fst.add_state()
            # fst.add_arc(backoff_state, state, word)
            # fst.add_arc(state, backoff_state, None)
            fst.add_arc(backoff_state, backoff_state, word)
        kaldi_rule.compile()
        return kaldi_rule

    def compile_dictation_fst(self, g_filename):
        self._compile_agf_graph(input_filename=g_filename, filename=self._dictation_fst_filepath, nonterm=True)

    def process_compile_and_load_queues(self):
        # Allowing this gives us leeway elsewhere
        # for kaldi_rule in self.compile_queue:
        #     if kaldi_rule.compiled:
        #         self._log.warning("compile_queue has %s but it is already compiled", kaldi_rule)
        # for kaldi_rule in self.compile_duplicate_filename_queue:
        #     if kaldi_rule.compiled:
        #         self._log.warning("compile_duplicate_filename_queue has %s but it is already compiled", kaldi_rule)
        # for kaldi_rule in self.load_queue:
        #     if kaldi_rule.loaded:
        #         self._log.warning("load_queue has %s but it is already loaded", kaldi_rule)

        # Clean out obsolete entries
        self.compile_queue.difference_update([kaldi_rule for kaldi_rule in self.compile_queue if kaldi_rule.compiled])
        self.compile_duplicate_filename_queue.difference_update([kaldi_rule for kaldi_rule in self.compile_duplicate_filename_queue if kaldi_rule.compiled])
        self.load_queue.difference_update([kaldi_rule for kaldi_rule in self.load_queue if kaldi_rule.loaded])

        if self.compile_queue or self.compile_duplicate_filename_queue or self.load_queue:
            with concurrent.futures.ThreadPoolExecutor(max_workers=multiprocessing.cpu_count()) as executor:
                results = executor.map(lambda kaldi_rule: kaldi_rule.finish_compile(), self.compile_queue)
                # Load pending rules that have already been compiled
                # for kaldi_rule in (self.load_queue - self.compile_queue - self.compile_duplicate_filename_queue):
                #     kaldi_rule.load()
                #     self.load_queue.remove(kaldi_rule)
                # Handle rules as they are completed (have been compiled)
                for kaldi_rule in results:
                    assert kaldi_rule.compiled
                    self.compile_queue.remove(kaldi_rule)
                    # if kaldi_rule in self.load_queue:
                    #     kaldi_rule.load()
                    #     self.load_queue.remove(kaldi_rule)
                # Handle rules that were pending compile but were duplicate and so compiled by/for another rule
                for kaldi_rule in list(self.compile_duplicate_filename_queue):
                    kaldi_rule.compile(duplicate=True)
                    assert kaldi_rule.compiled
                    self.compile_duplicate_filename_queue.remove(kaldi_rule)
                    # if kaldi_rule in self.load_queue:
                    #     kaldi_rule.load()
                    #     self.load_queue.remove(kaldi_rule)
                # Load rules in correct order
                for kaldi_rule in sorted(self.load_queue, key=lambda kr: kr.id):
                    kaldi_rule.load()
                    assert kaldi_rule.loaded
                    self.load_queue.remove(kaldi_rule)

    ####################################################################################################################
    # Methods for recognition.

    def prepare_for_recognition(self):
        if self.compile_queue or self.compile_duplicate_filename_queue or self.load_queue:
            self.process_compile_and_load_queues()
        if self.fst_cache.dirty:
            self.fst_cache.save()

    wildcard_nonterms = ('#nonterm:dictation', '#nonterm:dictation_cloud')

    def parse_output_for_rule(self, kaldi_rule, output):
        """Can be used even when self.parsing_framework == 'token', only for mimic (which contains no nonterms)."""
        labels = kaldi_rule.fst.does_match(output.split(), wildcard_nonterms=self.wildcard_nonterms)
        self._log.log(5, "parse_output_for_rule(%s, %r) got %r", kaldi_rule, output, labels)
        if labels is False:
            return None
        words = [label for label in labels if not label.startswith('#nonterm:')]
        parsed_output = ' '.join(words)
        if parsed_output.lower() != output:
            self._log.error("parsed_output(%r).lower() != output(%r)" % (parsed_output, output))
        return words

    cloud_dictation_regex = re.compile(r'(?<=#nonterm:dictation_cloud )(.*?)(?= #nonterm:end)')  # lookbehind & lookahead assertions

    def parse_output(self, output, dictation_info_func=None):
        assert self.parsing_framework == 'token'
        self._log.debug("parse_output(%r)" % output)
        if output == '':
            return None, [], []

        nonterm_token, _, parsed_output = output.partition(' ')
        assert nonterm_token.startswith('#nonterm:rule')
        kaldi_rule_id = int(nonterm_token[len('#nonterm:rule'):])
        kaldi_rule = self.kaldi_rule_by_id_dict[kaldi_rule_id]

        if self.cloud_dictation and dictation_info_func and kaldi_rule.has_dictation and '#nonterm:dictation_cloud' in parsed_output:
            try:
                audio_data, word_align = dictation_info_func()
                self._log.log(5, "cloud_dictation word_align: %s", word_align)
                words, times, lengths = list(zip(*word_align))
                # Find start & end word-index & byte-offset of each cloud dictation span
                dictation_spans = [{
                        'index_start': index,
                        'offset_start': time,
                        'index_end': words.index('#nonterm:end', index),
                        'offset_end': times[words.index('#nonterm:end', index)],
                    }
                    for index, (word, time, length) in zip(range(len(word_align)), word_align)
                    if word.startswith('#nonterm:dictation_cloud')]

                # If last dictation is at end of utterance, include rest of audio_data; else, include half of audio_data between dictation end and start of next word
                dictation_span = dictation_spans[-1]
                if dictation_span['index_end'] == len(word_align) - 1:
                    dictation_span['offset_end'] = len(audio_data)
                else:
                    next_word_time = times[dictation_span['index_end'] + 1]
                    dictation_span['offset_end'] = (dictation_span['offset_end'] + next_word_time) / 2

                def replace_dictation(matchobj):
                    orig_text = matchobj.group(1)
                    dictation_span = dictation_spans.pop(0)
                    dictation_audio = audio_data[dictation_span['offset_start'] : dictation_span['offset_end']]
                    kwargs = dict(language_code=self.cloud_dictation_lang)
                    with debug_timer(self._log.debug, 'cloud dictation call'):
                        cloud_text = cloud.GCloud.transcribe_data_sync(dictation_audio, **kwargs)
                        self._log.debug("cloud_dictation: %.2fs audio -> %r", (0.5 * len(dictation_audio) / 16000), cloud_text)
                    # with debug_timer(self._log.debug, 'cloud dictation call'):
                    #     cloud_text = cloud.GCloud.transcribe_data_sync(dictation_audio, model='command_and_search', **kwargs)
                    #     self._log.debug("cloud_dictation: %.2fs audio -> %r", (0.5 * len(dictation_audio) / 16000), cloud_text)
                    # with debug_timer(self._log.debug, 'cloud dictation call'):
                    #     cloud_text = cloud.GCloud.transcribe_data_streaming(dictation_audio, **kwargs)
                    #     self._log.debug("cloud_dictation: %.2fs audio -> %r", (0.5 * len(dictation_audio) / 16000), cloud_text)
                    # cloud.write_wav('test.wav', dictation_audio)
                    return (cloud_text or orig_text)

                parsed_output = self.cloud_dictation_regex.sub(replace_dictation, parsed_output)
            except Exception as e:
                self._log.exception("Exception performing cloud dictation")

        words = []
        words_are_dictation = []
        in_dictation = False
        for word in parsed_output.split():
            if word.startswith('#nonterm:'):
                if word.startswith('#nonterm:dictation'):
                    in_dictation = True
                elif in_dictation and word == '#nonterm:end':
                    in_dictation = False
            else:
                words.append(word)
                words_are_dictation.append(in_dictation)

        return kaldi_rule, words, words_are_dictation

    def parse_partial_output(self, output):
        assert self.parsing_framework == 'token'
        # self._log.debug("parse_partial_output(%r)" % output)
        if output == '':
            return None, [], [], False

        nonterm_token, _, parsed_output = output.partition(' ')
        assert nonterm_token.startswith('#nonterm:rule')
        kaldi_rule_id = int(nonterm_token[len('#nonterm:rule'):])
        kaldi_rule = self.kaldi_rule_by_id_dict[kaldi_rule_id]

        words = []
        words_are_dictation = []
        in_dictation = False
        for word in parsed_output.split():
            if word.startswith('#nonterm:'):
                if word.startswith('#nonterm:dictation'):
                    in_dictation = True
                elif in_dictation and word == '#nonterm:end':
                    in_dictation = False
            else:
                words.append(word)
                words_are_dictation.append(in_dictation)

        return kaldi_rule, words, words_are_dictation, in_dictation

########################################################################################################################
# Utility functions.

def remove_nonterms_in_words(words):
    return [word for word in words if not word.startswith('#nonterm:')]

def remove_nonterms_in_text(text):
    return ' '.join(word for word in text.split() if not word.startswith('#nonterm:'))

def run_subprocess(cmd, format_kwargs, description=None, format_kwargs_update=None, **kwargs):
    with debug_timer(_log.debug, description or "description", False), open(os.devnull, 'wb') as devnull:
        output = None if _log.isEnabledFor(logging.DEBUG) else devnull
        args = shlex.split(cmd.format(**format_kwargs), posix=(platform != 'windows'))
        _log.log(5, "subprocess.check_call(%r)", args)
        subprocess.check_call(args, stdout=output, stderr=output, **kwargs)
        if format_kwargs_update:
            format_kwargs.update(format_kwargs_update)
