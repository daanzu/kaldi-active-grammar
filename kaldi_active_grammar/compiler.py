#
# This file is part of kaldi-active-grammar.
# (c) Copyright 2019 by David Zurow
# Licensed under the AGPL-3.0; see LICENSE.txt file.
#

import collections, multiprocessing, os, re, threading, weakref
import concurrent.futures
from contextlib import contextmanager

from six.moves import range, zip

from . import _log, KaldiError
from .utils import ExternalProcess, debug_timer, show_donation_message
from .wfst import NativeWFST, SymbolTable
from .model import Model
from .wrapper import KaldiAgfCompiler, KaldiAgfNNet3Decoder, KaldiLafNNet3Decoder
import kaldi_active_grammar.defaults as defaults

_log = _log.getChild('compiler')


########################################################################################################################

class KaldiRule(object):

    cls_lock = threading.Lock()

    def __init__(self, compiler, name, nonterm=True, exported=True, has_dictation=None, is_complex=None):
        """
        :param nonterm: bool whether rule represents a nonterminal in the active-grammar-fst (only False for the top FST).
        :param exported: bool whether rule is a top-level rule (with an arc to it from the top_fst), rather than needing to be referenced from another rule.
        """
        compiler._require_open()
        self.compiler = compiler
        self.name = name
        assert nonterm or not exported
        self.nonterm = bool(nonterm)
        self.exported = bool(exported)
        self.has_dictation = has_dictation
        self.is_complex = is_complex

        # id: matches "nonterm:rule__"; 0-based; stable for this rule's lifetime (other rules' ids do not shift when one is unloaded), but a freed id may later be reused by a new rule.
        self.id = int(self.compiler._kaldi_rule_id_allocator.alloc_id(self.exported) if self.nonterm else -1)
        if self.id in self.compiler.kaldi_rule_by_id_dict: raise KaldiError("KaldiRule id already in use")
        if self.id >= 0:
            self.compiler.kaldi_rule_by_id_dict[self.id] = self

        # Private/protected
        self.compiled = False
        self.loaded = False
        self.reloading = False  # KaldiRule is in the process of the reload contextmanager
        self.has_been_loaded = False  # KaldiRule was loaded, then reload() was called & completed, and now it is not currently loaded, and load() we need to call the decoder's reload
        self.closed = False  # KaldiRule must not be used/referenced anymore

        # Public
        self.fst = NativeWFST()
        self.matcher = None
        self.active = True
        self.compiler._all_rules.add(self)

    def __repr__(self):
        return "%s(%s, %s)" % (self.__class__.__name__, self.id, self.name)

    def _require_compiler(self):
        if self.closed:
            raise KaldiError("Cannot use a KaldiRule after calling close()")
        return self.compiler

    decoder = property(lambda self: self._require_compiler().decoder)

    pending_compile = property(lambda self: (self in self._require_compiler().compile_queue) or (self in self._require_compiler().compile_duplicate_filename_queue))
    pending_load = property(lambda self: self in self._require_compiler().load_queue)

    filename = property(lambda self: self.fst.filename)

    @property
    def filepath(self):
        compiler = self._require_compiler()
        assert self.filename
        if compiler.tmp_dir is None:
            raise KaldiError("Cannot get a KaldiRule filepath without a temporary directory")
        return os.path.join(compiler.tmp_dir, self.filename)

    def compile(self, lazy=False, duplicate=None):
        self._require_compiler()
        if self.compiled: return self

        fst_cache = self.compiler.model._fst_cache
        if not self.filename:
            self.fst.compute_hash(fst_cache.dependencies_hash)
            assert self.filename

        if self.compiler.cache_fsts and fst_cache.fst_is_current(self.filepath, touch=False):
            _log.debug("%s: Skipped FST compilation thanks to FileCache" % self)
            if self.compiler.decoding_framework == 'agf':
                self.fst.compiled_native_obj = NativeWFST.load_file(self.filepath)
            self.compiled = True
            return self
        else:
            if duplicate:
                _log.warning("%s was supposed to be a duplicate compile, but was not found in FileCache", self)

        if lazy:
            if not self.pending_compile:
                # Special handling for rules that are an exact content match (and hence hash/name) with another (different) rule already in the compile_queue
                if not any(self.filename == kaldi_rule.filename for kaldi_rule in self.compiler.compile_queue if self != kaldi_rule):
                    self.compiler.compile_queue.add(self)
                else:
                    self.compiler.compile_duplicate_filename_queue.add(self)
            return self

        return self.finish_compile()

    def finish_compile(self):
        # Must be thread-safe!
        with self.cls_lock:
            self.compiler.prepare_for_compilation()
        _log.log(15, "%s: Compiling %sstate/%sarc FST%s" % (self, self.fst.num_states, self.fst.num_arcs,
                (" to " + self.filename) if self.filename else ""))
        if _log.isEnabledFor(3):
            self.fst.write_file('tmp_G.fst')
            if _log.isEnabledFor(2):
                self.fst.print()

        try:
            if self.compiler.decoding_framework == 'agf':
                self.fst.compiled_native_obj = self.compiler._compile_agf_graph(
                    nonterm=self.nonterm, input_fst=self.fst, return_output_fst=True,
                    output_filename=(self.filepath if self.compiler.cache_fsts else None))

            elif self.compiler.decoding_framework == 'laf':
                pass

            else: raise KaldiError("unknown compiler.decoding_framework")
        except Exception as e:
            raise KaldiError("Exception while compiling", self) from e  # Return this KaldiRule inside exception

        self.compiled = True
        return self

    def load(self, lazy=False):
        self._require_compiler()
        if lazy or self.pending_compile:
            self.compiler.load_queue.add(self)
            return self
        assert self.compiled

        if self.has_been_loaded:
            # FIXME: why is this necessary?
            self._do_reloading()
        else:
            grammar_fst_index = self.decoder.add_grammar_fst(self.id, self.fst)
            self.decoder.set_mimic_grammar_fst(self.id, self.fst)
            assert self.id == grammar_fst_index, "add_grammar_fst allocated invalid grammar_fst_index %d != %d for %s" % (grammar_fst_index, self.id, self)

        self.loaded = True
        self.has_been_loaded = True
        return self

    def _do_reloading(self):
        self.decoder.reload_grammar_fst(self.id, self.fst)
        self.decoder.set_mimic_grammar_fst(self.id, self.fst)

    @contextmanager
    def reload(self):
        """ Used for modifying a rule in place, e.g. ListRef. """
        self._require_compiler()

        was_loaded = self.loaded
        self.reloading = True
        self.fst.clear()
        self.compiled = False
        self.loaded = False

        yield

        if self.compiled and was_loaded:
            if not self.loaded:
                # FIXME: how is this different from the branch of the if above in load()?
                self._do_reloading()
                self.loaded = True
        elif was_loaded:  # must be not self.compiled (i.e. the compile during reloading was lazy)
            self.compiler.load_queue.add(self)
        self.reloading = False

    def _release(self):
        """Drop compiler/native references, marking this rule dead; idempotent."""
        self.closed = True
        self.loaded = False
        self.compiler = None
        self.fst.close()

    def close(self):
        """Release this rule and its native FST, once."""
        if self.closed:
            return

        compiler = self.compiler

        if self.loaded and compiler.decoder is not None:
            self.decoder.remove_grammar_fst(self.id)
            assert self not in compiler.compile_queue
            assert self not in compiler.compile_duplicate_filename_queue
            assert self not in compiler.load_queue
        else:
            if self in compiler.compile_queue: compiler.compile_queue.remove(self)
            if self in compiler.compile_duplicate_filename_queue: compiler.compile_duplicate_filename_queue.remove(self)
            if self in compiler.load_queue: compiler.load_queue.remove(self)

        if self.id >= 0:
            del compiler.kaldi_rule_by_id_dict[self.id]
            compiler._kaldi_rule_id_allocator.free_id(self.id)

        self._release()

    def __enter__(self):
        self._require_compiler()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()


########################################################################################################################

class Compiler(object):

    def __init__(self, model_dir=None, tmp_dir=None, alternative_dictation=None,
            framework='agf-direct', cache_fsts=True,
            strict_content_validation=False, invalidate=False):
        """Create a grammar compiler.

        ``framework`` is either ``'agf-direct'`` or ``'laf'``. Compiler-owned
        rules always use :class:`NativeWFST`; the removed ``native_fst``
        option is no longer accepted. ``cache_fsts`` controls whether
        compiled AGF graphs are written to and restored from the model cache.
        ``strict_content_validation`` forces every model dependency to be
        content-hashed during cache validation, detecting replacements that
        preserve both file size and modification time at the cost of reading
        the dependency files on each initialization.
        ``invalidate`` forces model and lexicon regeneration for this
        construction only. When FST caching is enabled, regeneration also
        discards cached grammar FSTs.
        """

        show_donation_message()
        self._log = _log

        if framework == 'agf-indirect':
            raise KaldiError("framework='agf-indirect' was removed; use framework='agf-direct'")
        if framework == 'agf-direct':
            framework = 'agf'
        self.decoding_framework = framework
        # 'agf' is accepted as well as 'agf-direct': it is the canonical form stored in
        # decoding_framework, so that value can be passed back in.
        if self.decoding_framework not in ('agf', 'laf'):
            raise KaldiError("Invalid Compiler framework %r; expected 'agf-direct' (canonically 'agf') or 'laf'" % framework)
        self.parsing_framework = 'token'
        self.cache_fsts = bool(cache_fsts)
        self.alternative_dictation = alternative_dictation
        self._closed = False

        tmp_dir_needed = bool(self.cache_fsts)
        self.model = Model(
            model_dir, tmp_dir, tmp_dir_needed=tmp_dir_needed,
            strict_content_validation=strict_content_validation,
            invalidate=invalidate,
        )
        self._lexicon_files_stale = False

        NativeWFST.init_class(
            osymbol_table=self.model.words_table,
            isymbol_table=self.model.words_table if self.decoding_framework != 'laf' else SymbolTable(self.files_dict['words.relabeled.txt']),
            wildcard_nonterms=self.wildcard_nonterms)
        self._kaldi_rule_id_allocator = IdAllocator(max_num_exported_rules=1000, max_num_nonexported_rules=9000)
        self._agf_compiler = self._init_agf_compiler() if self.decoding_framework == 'agf' else None
        self.decoder = None

        words_set = frozenset(self.model.words_table.words)
        self._oov_word = '<unk>' if ('<unk>' in self.model.words_table) else None  # FIXME: make this configurable, for different models
        self._silence_words = frozenset(['!SIL']) & words_set  # FIXME: make this configurable, for different models
        self._noise_words = frozenset(['<unk>', '!SIL']) & words_set  # FIXME: make this configurable, for different models

        self.kaldi_rule_by_id_dict = collections.OrderedDict()  # maps KaldiRule.id -> KaldiRule
        self.compile_queue = set()  # KaldiRule
        self.compile_duplicate_filename_queue = set()  # KaldiRule; queued KaldiRules with a duplicate filename (and thus contents), so can skip compilation
        self.load_queue = set()  # KaldiRule; must maintain same order as order of instantiation!
        self._all_rules = weakref.WeakSet()  # Every KaldiRule created by this Compiler

    def close(self):
        """Release native resources owned by this compiler, once."""
        if self._closed:
            return
        self._closed = True

        cleanup_error = None
        decoder, self.decoder = self.decoder, None
        if decoder is not None:
            try:
                decoder.close()
            except Exception as error:
                cleanup_error = error

        agf_compiler, self._agf_compiler = self._agf_compiler, None
        if agf_compiler is not None:
            try:
                agf_compiler.close()
            except Exception as error:
                if cleanup_error is None:
                    cleanup_error = error

        # Rules point back to this compiler.  Break those cycles after native
        # decoder teardown; unloading individual grammars is neither necessary
        # nor valid once the decoder has gone away.
        rules = list(self._all_rules)
        self.kaldi_rule_by_id_dict.clear()
        self.compile_queue.clear()
        self.compile_duplicate_filename_queue.clear()
        self.load_queue.clear()
        self._all_rules.clear()
        for rule in rules:
            try:
                rule._release()
            except Exception as error:
                if cleanup_error is None:
                    cleanup_error = error

        if cleanup_error is not None:
            raise cleanup_error

    def __enter__(self):
        self._require_open()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def _require_open(self):
        if self._closed:
            raise KaldiError("Cannot use closed Compiler")
        return self

    def init_decoder(self, config=None, dictation_fst_file=None, dictation_g_fst_file=None):
        self._require_open()
        if self.decoder: raise KaldiError("Decoder already initialized")
        assert (dictation_fst_file is not None) or (dictation_fst_file == dictation_g_fst_file)
        if dictation_fst_file is None: dictation_fst_file = self.dictation_fst_filepath
        if dictation_g_fst_file is None: dictation_g_fst_file = self.dictation_g_fst_filepath

        decoder_kwargs = dict(
            model_dir=self.model_dir,
            tmp_dir=self.tmp_dir,
            dictation_fst_file=dictation_fst_file,
            max_num_rules=self._kaldi_rule_id_allocator.max_num_rules,
            max_num_exported_rules=self._kaldi_rule_id_allocator.max_num_exported_rules,
            eps_disambig_sym=NativeWFST.eps_disambig,
            config=config,
            )
        if self.decoding_framework == 'agf':
            top_fst_rule = self.compile_top_fst()
            decoder_kwargs.update(top_fst=top_fst_rule.fst)
            self.decoder = KaldiAgfNNet3Decoder(**decoder_kwargs)
        elif self.decoding_framework == 'laf':
            self.decoder = KaldiLafNNet3Decoder(**decoder_kwargs)
        else:
            raise KaldiError("Invalid Compiler.decoding_framework: %r" % self.decoding_framework)

        if dictation_g_fst_file:
            self.decoder.set_mimic_dictation_fst_file(dictation_g_fst_file)
        return self.decoder

    exec_dir = property(lambda self: self.model.exec_dir)
    model_dir = property(lambda self: self.model.model_dir)
    tmp_dir = property(lambda self: self.model.tmp_dir)
    files_dict = property(lambda self: self.model.files_dict)

    lexicon_words = property(lambda self: self.model.words_table.word_to_id_map)
    _longest_word = property(lambda self: self.model.longest_word)

    _default_dictation_g_fst_filepath = property(lambda self: os.path.join(self.model_dir, defaults.DEFAULT_DICTATION_G_FILENAME))
    _default_dictation_fst_filepath = property(lambda self: os.path.join(self.model_dir,
        (defaults.DEFAULT_DICTATION_FST_FILENAME if self.decoding_framework == 'agf' else 'Gr.fst')))  # FIXME: generalize
    _plain_dictation_hclg_fst_filepath = property(lambda self: os.path.join(self.model_dir, defaults.DEFAULT_PLAIN_DICTATION_HCLG_FST_FILENAME))

    @property
    def dictation_fst_filepath(self):
        if os.path.exists(self._default_dictation_fst_filepath):
            return self._default_dictation_fst_filepath
        self._log.error("cannot find dictation fst: %s", self._default_dictation_fst_filepath)
        # FIXME: Fall back to universal dictation?

    @property
    def dictation_g_fst_filepath(self):
        if os.path.exists(self._default_dictation_g_fst_filepath):
            return self._default_dictation_g_fst_filepath
        self._log.error("cannot find dictation G fst: %s", self._default_dictation_g_fst_filepath)
        # FIXME: Fall back to universal dictation?


    ####################################################################################################################
    # Methods for compiling graphs.

    def add_word(self, word, phones=None, lazy_compilation=False, allow_online_pronunciations=False):
        if self.decoding_framework == 'laf':
            raise KaldiError(
                "LAF does not support adding words or pronunciations at runtime; "
                "rebuild the LAF graph bundle (HCLr.fst, Gr.fst, "
                "relabel_ilabels.int, and words.relabeled.txt) with the updated "
                "lexicon before constructing the compiler.")
        self._require_open()
        pronunciations = self.model.add_word(word, phones=phones, lazy_compilation=lazy_compilation, allow_online_pronunciations=allow_online_pronunciations)
        self._lexicon_files_stale = True  # Only mark lexicon stale if it was successfully modified (not an exception)
        return pronunciations

    def prepare_for_compilation(self):
        self._require_open()
        if self._lexicon_files_stale:
            self.model.generate_lexicon_files()
            self.model.load_words()  # FIXME: This re-loading from the words.txt file may be unnecessary now that we have/use NativeWFST + SymbolTable, but it's not clear if it's safe to remove it.
            self.decoder.load_lexicon()
            if self._agf_compiler:
                # TODO: Just update the necessary files in the config
                self._agf_compiler.close()
                self._agf_compiler = self._init_agf_compiler()
            self._lexicon_files_stale = False

    def _init_agf_compiler(self):
        config = dict(
            tree_rxfilename=self.files_dict['tree'],
            model_rxfilename=self.files_dict['final_mdl'],
            lex_rxfilename=self.files_dict['L_disambig_fst'],
            disambig_rxfilename=self.files_dict['disambig_int'],
            word_syms_filename=self.files_dict['words_txt'],
            )
        return KaldiAgfCompiler(config)

    def _compile_agf_graph(self, nonterm=False, simplify_lg=True,
            input_filename=None, input_fst=None,
            output_filename=None, return_output_fst=False):
        """
        :param nonterm: bool whether rule represents a nonterminal in the active-grammar-fst (only False for the top FST?)
        :param simplify_lg: bool whether to simplify LG (disambiguate, and more) (do for command grammars, but not for dictation graph!)
        """
        self._require_open()
        # Must be thread-safe!
        if 1 != sum(int(i is not None) for i in [input_filename, input_fst]):
            raise KaldiError("must pass exactly one input")
        if self._agf_compiler is None:
            raise KaldiError("AGF graph compilation is not available with framework=%r" % self.decoding_framework)

        verbose_level = 3 if self._log.isEnabledFor(5) else 0
        config = dict(
            nonterm_phones_offset=self.model.nonterm_phones_offset,
            disambig_rxfilename=self.files_dict['disambig_int'],
            simplify_lg=bool(simplify_lg),
            verbose=verbose_level,
            tree_rxfilename=self.files_dict['tree'],
            model_rxfilename=self.files_dict['final_mdl'],
            lex_rxfilename=self.files_dict['L_disambig_fst'],
            word_syms_filename=self.files_dict['words_txt'],
            )
        if output_filename:
            config['hclg_wxfilename'] = output_filename
        elif self.tmp_dir is not None and self._log.isEnabledFor(3):
            import datetime
            config['hclg_wxfilename'] = os.path.join(
                self.tmp_dir, datetime.datetime.now().isoformat().replace(':', '') + '.fst')
        if nonterm:
            config.update(
                grammar_prepend_nonterm=self.model.nonterm_words_offset,
                grammar_append_nonterm=self.model.nonterm_words_offset + 1,
                )

        if input_filename is not None:
            return self._agf_compiler.compile_graph(
                config, grammar_fst_file=input_filename, return_graph=return_output_fst)
        return self._agf_compiler.compile_graph(
            config, grammar_fst=input_fst, return_graph=return_output_fst)

    def compile_plain_dictation_fst(self, g_filename=None, output_filename=None):
        if g_filename is None: g_filename = self._default_dictation_g_fst_filepath
        if output_filename is None: output_filename = self._plain_dictation_hclg_fst_filepath
        verbose_level = 5 if self._log.isEnabledFor(5) else 0
        format_kwargs = dict(self.files_dict, g_filename=g_filename, output_filename=output_filename, verbose=verbose_level)
        format = ExternalProcess.get_list_formatter(format_kwargs)
        args = format('--read-disambig-syms={disambig_int}', '--simplify-lg=false', '--verbose={verbose}',
            '{tree}', '{final_mdl}', '{L_disambig_fst}', '{g_filename}', '{output_filename}')
        compile_command = ExternalProcess.compile_graph_agf(*args, **ExternalProcess.get_debug_stderr_kwargs(self._log))
        compile_command()

    def compile_agf_dictation_fst(self, g_filename=None):
        if g_filename is None: g_filename = self._default_dictation_g_fst_filepath
        self._compile_agf_graph(input_filename=g_filename, output_filename=self._default_dictation_fst_filepath, nonterm=True, simplify_lg=False)

    def compile_top_fst(self):
        return self._build_top_fst(nonterms=['#nonterm:rule'+str(i) for i in range(self._kaldi_rule_id_allocator.max_num_exported_rules)], noise_words=self._noise_words).compile()

    def compile_top_fst_dictation_only(self):
        return self._build_top_fst(nonterms=['#nonterm:dictation'], noise_words=self._noise_words).compile()

    def _build_top_fst(self, nonterms, noise_words):
        kaldi_rule = KaldiRule(self, 'top', nonterm=False, exported=False)
        fst = kaldi_rule.fst
        state_initial = fst.add_state(initial=True)
        state_final = fst.add_state(final=True)

        state_return = fst.add_state()
        for nonterm in nonterms:
            fst.add_arc(state_initial, state_return, nonterm)
        fst.add_arc(state_return, state_final, None, '#nonterm:end')

        if noise_words:
            for (state_from, state_to) in [
                    (state_initial, state_final),
                    # (state_initial, state_initial),  # FIXME: test this
                    # (state_final, state_final),
                    ]:
                for word in noise_words:
                    fst.add_arc(state_from, state_to, word)

        return kaldi_rule

    # def _construct_dictation_states(self, fst, src_state, dst_state, number=(1,None), words=None, start_weight=None):
    #     """
    #     Matches `number` words.
    #     :param number: (0,None) or (1,None) or (1,1), where None is infinity.
    #     """
    #     # unweighted=0.01
    #     if words is None: words = self.lexicon_words
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
        if words is None: words = self.lexicon_words
        fst = kaldi_rule.fst
        backoff_state = fst.add_state(initial=True, final=True)
        for word in words:
            # state = fst.add_state()
            # fst.add_arc(backoff_state, state, word)
            # fst.add_arc(state, backoff_state, None)
            fst.add_arc(backoff_state, backoff_state, word)
        kaldi_rule.compile()
        return kaldi_rule

    def process_compile_and_load_queues(self):
        self._require_open()
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
                # Handle rules that were pending compile but were duplicate and so compiled by/for another rule. They should be in the cache now
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
        self._require_open()
        try:
            if self.compile_queue or self.compile_duplicate_filename_queue or self.load_queue:
                self.process_compile_and_load_queues()
        except KaldiError:
            raise
        except Exception:
            raise KaldiError("Exception while compiling/loading rules in prepare_for_recognition")
        finally:
            if self.model._fst_cache.dirty:
                self.model._fst_cache.save()

    def mimic(self, text, grammars_activity):
        """Mimic text using active compiler rule IDs.

        ``grammars_activity`` is an iterable of ``KaldiRule.id`` values, not
        a positional Boolean mask.  The decoder wrapper also accepts ``None``
        to preserve its current activity set.
        """
        self._require_open()
        output = self.decoder.mimic(text, grammars_activity)
        if output is False:
            return None
        return output

    def parse_output_for_rule_token(self, kaldi_rule, output):
        """Can be used even when self.parsing_framework == 'token', only for mimic (which contains no nonterms)."""
        words = output.split()
        labels = self.mimic_for_rule(words, kaldi_rule)
        self._log.log(5, "parse_output_for_rule(%s, %r) got %r", kaldi_rule, output, labels)
        if labels is False:
            return None
        # words = [label for label in labels if not label.startswith('#nonterm:')]
        # parsed_output = ' '.join(words)
        # if parsed_output.lower() != output:
        #     self._log.error("parsed_output(%r).lower() != output(%r)" % (parsed_output, output))
        return words

    wildcard_nonterms = ('#nonterm:dictation', '#nonterm:dictation_cloud')
    alternative_dictation_regex = re.compile(r'(?<=#nonterm:dictation_cloud )(.*?)(?= #nonterm:end)')  # lookbehind & lookahead assertions

    def parse_output(self, output, dictation_info_func=None):
        """
        dictation_info_func: Optional but required for using alternative_dictation; expected to be (audio_data, wrapper::KaldiNNet3Decoder.get_word_align output).
        """
        assert self.parsing_framework == 'token'
        self._log.debug("parse_output(%r)" % output)
        if (output is None) or (output == '') or (output in self._noise_words):
            return None, [], []

        nonterm_token, _, parsed_output = output.partition(' ')
        assert nonterm_token.startswith('#nonterm:rule')
        kaldi_rule_id = int(nonterm_token[len('#nonterm:rule'):])
        kaldi_rule = self.kaldi_rule_by_id_dict[kaldi_rule_id]

        if self.alternative_dictation and dictation_info_func and kaldi_rule.has_dictation and '#nonterm:dictation_cloud' in parsed_output:
            try:
                if callable(self.alternative_dictation):
                    alternative_text_func = self.alternative_dictation
                else:
                    raise TypeError("Invalid alternative_dictation value: %r" % self.alternative_dictation)

                audio_data, word_align = dictation_info_func()
                self._log.log(5, "alternative_dictation word_align: %s", word_align)
                words, times, lengths = list(zip(*word_align))
                # Find start & end word-index & byte-offset of each alternative dictation span
                dictation_spans = [{
                        'index_start': index,
                        'offset_start': time,
                        'index_end': words.index('#nonterm:end', index),
                        'offset_end': times[words.index('#nonterm:end', index)],
                    }
                    for index, (word, time, length) in enumerate(word_align)
                    if word.startswith('#nonterm:dictation_cloud')]

                # If last dictation is at end of utterance, it should include rest of audio_data; else, it should include half of audio_data between dictation end and start of next word
                dictation_span = dictation_spans[-1]
                if dictation_span['index_end'] == len(word_align) - 1:
                    dictation_span['offset_end'] = len(audio_data)
                else:
                    next_word_time = times[dictation_span['index_end'] + 1]
                    dictation_span['offset_end'] = (dictation_span['offset_end'] + next_word_time) // 2

                def replace_dictation(matchobj: re.Match) -> str:
                    orig_text = matchobj.group(1)
                    dictation_span = dictation_spans.pop(0)
                    dictation_audio = audio_data[dictation_span['offset_start'] : dictation_span['offset_end']]
                    with debug_timer(self._log.debug, 'alternative_dictation call'):
                        alternative_text = alternative_text_func(dictation_audio)
                        self._log.debug("alternative_dictation: %.2fs audio -> %r", (0.5 * len(dictation_audio) / 16000), alternative_text)  # FIXME: hardcoded sample_rate!
                    # alternative_dictation.write_wav('test.wav', dictation_audio)
                    return (alternative_text or orig_text)

                parsed_output = self.alternative_dictation_regex.sub(replace_dictation, parsed_output)
            except Exception as e:
                self._log.exception("Exception performing alternative dictation")

        words = []
        words_are_dictation_mask = []
        in_dictation = False
        for word in parsed_output.split():
            if word.startswith('#nonterm:'):
                if word.startswith('#nonterm:dictation'):
                    in_dictation = True
                elif in_dictation and word == '#nonterm:end':
                    in_dictation = False
            else:
                words.append(word)
                words_are_dictation_mask.append(in_dictation)

        return kaldi_rule, words, words_are_dictation_mask

    def parse_partial_output(self, output):
        assert self.parsing_framework == 'token'
        self._log.log(3, "parse_partial_output(%r)", output)
        if (output == '') or (output in self._noise_words):
            return None, [], [], False

        nonterm_token, _, parsed_output = output.partition(' ')
        assert nonterm_token.startswith('#nonterm:rule')
        kaldi_rule_id = int(nonterm_token[len('#nonterm:rule'):])
        kaldi_rule = self.kaldi_rule_by_id_dict[kaldi_rule_id]

        words = []
        words_are_dictation_mask = []
        in_dictation = False
        for word in parsed_output.split():
            if word.startswith('#nonterm:'):
                if word.startswith('#nonterm:dictation'):
                    in_dictation = True
                elif in_dictation and word == '#nonterm:end':
                    in_dictation = False
            else:
                words.append(word)
                words_are_dictation_mask.append(in_dictation)

        return kaldi_rule, words, words_are_dictation_mask, in_dictation


########################################################################################################################
# Utility functions.

def remove_words_in_words(words, remove_words_func):
    return [word for word in words if not remove_words_func(word)]

def remove_words_in_text(text, remove_words_func):
    return ' '.join(word for word in text.split() if not remove_words_func(word))

def remove_nonterms_in_words(words):
    return remove_words_in_words(words, lambda word: word.startswith('#nonterm:'))

def remove_nonterms_in_text(text):
    return remove_words_in_text(text, lambda word: word.startswith('#nonterm:'))

class IdAllocator(object):

    def __init__(self, max_num_exported_rules, max_num_nonexported_rules):
        self.max_num_exported_rules = int(max_num_exported_rules)
        self.max_num_nonexported_rules = int(max_num_nonexported_rules)

        self.num_exported_rules = 0
        self.num_nonexported_rules = 0
        self.free_exported_ids = set()  # Free IDs below num_exported_rules
        self.free_nonexported_ids = set()  # Free IDs below num_nonexported_rules

    max_num_rules = property(lambda self: self.max_num_exported_rules + self.max_num_nonexported_rules)
    num_rules = property(lambda self: self.num_exported_rules + self.num_nonexported_rules - len(self.free_exported_ids) - len(self.free_nonexported_ids))

    def alloc_id(self, exported):
        if exported:
            if self.free_exported_ids:
                id = self.free_exported_ids.pop()
            else:
                assert self.num_exported_rules < self.max_num_exported_rules
                id = self.num_exported_rules
                self.num_exported_rules += 1
        else:
            if self.free_nonexported_ids:
                id = self.free_nonexported_ids.pop()
            else:
                assert self.num_nonexported_rules < self.max_num_nonexported_rules
                id = self.num_nonexported_rules + self.max_num_exported_rules  # Must offset by all exported rules
                self.num_nonexported_rules += 1
        return id

    def free_id(self, id):
        exported = (id < self.max_num_exported_rules)
        if exported:
            self.free_exported_ids.add(id)
        else:
            self.free_nonexported_ids.add(id)
        return id
