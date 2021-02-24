#
# This file is part of kaldi-active-grammar.
# (c) Copyright 2019 by David Zurow
# Licensed under the AGPL-3.0; see LICENSE.txt file.
#

import collections, itertools, math

from six import iteritems, itervalues, text_type

from . import KaldiError
from .utils import FSTFileCache


class WFST(object):
    """
    WFST class.
    Notes:
        * Weight (arc & state) is stored as raw probability, then normalized and converted to negative log likelihood/probability before export.
    """

    zero = float('inf')  # Weight of non-final states; a state is final if and only if its weight is not equal to self.zero
    one = 0.0
    eps = u'<eps>'
    eps_disambig = u'#0'
    silent_labels = frozenset((eps, eps_disambig, u'!SIL'))
    native = property(lambda self: False)

    def __init__(self):
        self.clear()

    def clear(self):
        self._arc_table_dict = collections.defaultdict(list)  # { src_state: [[src_state, dst_state, label, olabel, weight], ...] }  # list of its outgoing arcs
        self._state_table = dict()  # { id: weight }
        self._next_state_id = 0
        self.start_state = self.add_state()
        self.filename = None

    num_arcs = property(lambda self: sum(len(arc_list) for arc_list in itervalues(self._arc_table_dict)))
    num_states = property(lambda self: len(self._state_table))

    def iter_arcs(self):
        return itertools.chain.from_iterable(itervalues(self._arc_table_dict))

    def is_state_final(self, state):
        return (self._state_table[state] != 0)

    def add_state(self, weight=None, initial=False, final=False):
        """ Default weight is 1. """
        self.filename = None
        id = int(self._next_state_id)
        self._next_state_id += 1
        if weight is None:
            weight = 1 if final else 0
        else:
            assert final
        self._state_table[id] = float(weight)
        if initial:
            self.add_arc(self.start_state, id, None)
        return id

    def add_arc(self, src_state, dst_state, label, olabel=None, weight=None):
        """ Default weight is 1. None label is replaced by eps. Default olabel of None is replaced by label. """
        self.filename = None
        if label is None: label = self.eps
        if olabel is None: olabel = label
        if weight is None: weight = 1
        self._arc_table_dict[src_state].append(
            [int(src_state), int(dst_state), text_type(label), text_type(olabel), float(weight)])

    def get_fst_text(self, fst_cache, eps2disambig=False):
        eps_replacement = self.eps_disambig if eps2disambig else self.eps
        arcs_text = u''.join("%d %d %s %s %f\n" % (
                src_state,
                dst_state,
                ilabel if ilabel != self.eps else eps_replacement,
                olabel,
                -math.log(weight) if weight != 0 else self.zero,
            )
            for (src_state, dst_state, ilabel, olabel, weight) in self.iter_arcs())
        states_text = u''.join("%d %f\n" % (
                id,
                -math.log(weight) if weight != 0 else self.zero,
            )
            for (id, weight) in iteritems(self._state_table)
            if weight != 0)
        text = arcs_text + states_text
        self.filename = fst_cache.hash_data(text, mix_dependencies=True) + '.fst'
        return text

    ####################################################################################################################

    def label_is_silent(self, label):
        return ((label in self.silent_labels) or (label.startswith('#nonterm')))

    def scale_weights(self, factor):
        # Unused
        factor = float(factor)
        for arcs in itervalues(self._arc_table_dict):
            for arc in arcs:
                arc[4] = arc[4] * factor

    def normalize_weights(self, stochasticity=False):
        # Unused
        for arcs in itervalues(self._arc_table_dict):
            num_weights = len(arcs)
            sum_weights = sum(arc[4] for arc in arcs)
            divisor = float(sum_weights if stochasticity else num_weights)
            for arc in arcs:
                arc[4] = arc[4] / divisor

    def has_eps_path(self, path_src_state, path_dst_state, eps_like_labels=frozenset()):
        """ Returns True iff there is a epsilon path from src_state to dst_state. Uses BFS. Does not follow nonterminals! Used by Dragonfly compiler. """
        eps_like_labels = frozenset((self.eps, self.eps_disambig)) | frozenset(eps_like_labels)
        state_queue = collections.deque([path_src_state])
        queued = set(state_queue)
        while state_queue:
            state = state_queue.pop()
            if state == path_dst_state:
                return True
            next_states = [dst_state
                for (src_state, dst_state, label, olabel, weight) in self._arc_table_dict[state]
                if (label in eps_like_labels) and (dst_state not in queued)]
            state_queue.extendleft(next_states)
            queued.update(next_states)
        return False

    def does_match(self, target_words, wildcard_nonterms=(), include_silent=False):
        """ Returns the olabels on a matching path if there is one, False if not. Uses BFS. Wildcard accepts zero or more words. Used for parsing by KaldiAG.compiler. """
        queue = collections.deque()  # entries: (state, path of ilabels of arcs to state, index into target_words of remaining words)
        queue.append((self.start_state, (), 0))
        while queue:
            state, path, target_word_index = queue.popleft()
            target_word = target_words[target_word_index] if target_word_index < len(target_words) else None
            if (target_word is None) and self.is_state_final(state):
                return tuple(olabel for olabel in path
                    if include_silent or not self.label_is_silent(olabel))
            for arc in self._arc_table_dict[state]:
                src_state, dst_state, ilabel, olabel, weight = arc
                if (target_word is not None) and (ilabel == target_word):
                    queue.append((dst_state, path+(olabel,), target_word_index+1))
                elif ilabel in wildcard_nonterms:
                    if olabel not in path:
                        path += (olabel,)  # FIXME: Is this right? shouldn't we only check for olabel at end of path?
                    if target_word is not None:
                        queue.append((src_state, path+(target_word,), target_word_index+1))  # accept word and stay
                    queue.append((dst_state, path, target_word_index))  # epsilon transition; already added olabel above or previously
                elif self.label_is_silent(ilabel):
                    queue.append((dst_state, path+(olabel,), target_word_index))  # epsilon transition
        return False


########################################################################################################################

from .ffi import FFIObject, _ffi, decode, encode

class NativeWFST(FFIObject):
    """
    WFST class, implemented in native code.
    Notes:
        * Weight (arc & state) is stored as raw probability, then normalized and converted to negative log likelihood/probability before export.
    """

    _library_header_text = """
        DRAGONFLY_API bool fst__init(int32_t eps_like_ilabels_len, int32_t eps_like_ilabels_cp[], int32_t silent_olabels_len, int32_t silent_olabels_cp[], int32_t wildcard_olabels_len, int32_t wildcard_olabels_cp[]);
        DRAGONFLY_API void* fst__construct();
        DRAGONFLY_API bool fst__destruct(void* fst_vp);
        DRAGONFLY_API int32_t fst__add_state(void* fst_vp, float weight, bool initial);
        DRAGONFLY_API bool fst__add_arc(void* fst_vp, int32_t src_state_id, int32_t dst_state_id, int32_t ilabel, int32_t olabel, float weight);
        DRAGONFLY_API bool fst__compute_md5(void* fst_vp, char* md5_cp, char* dependencies_seed_md5_cp);
        DRAGONFLY_API bool fst__has_eps_path(void* fst_vp, int32_t path_src_state, int32_t path_dst_state);
        DRAGONFLY_API bool fst__does_match(void* fst_vp, int32_t target_labels_len, int32_t target_labels_cp[], int32_t output_labels_cp[], int32_t* output_labels_len);
        DRAGONFLY_API void* fst__load_file(char* filename_cp);
        DRAGONFLY_API void* fst__compile_text(char* fst_text_cp, char* isymbols_file_cp, char* osymbols_file_cp);
    """

    zero = float('inf')  # Weight of non-final states; a state is final if and only if its weight is not equal to self.zero
    one = 0.0
    eps = u'<eps>'
    eps_disambig = u'#0'
    silent_words = frozenset((eps, eps_disambig, u'!SIL'))
    native = property(lambda self: True)

    @classmethod
    def init_class(cls, isymbol_table, wildcard_nonterms, osymbol_table=None):
        if osymbol_table is None: osymbol_table = isymbol_table
        cls.word_to_ilabel_map = isymbol_table.word_to_id_map
        cls.word_to_olabel_map = osymbol_table.word_to_id_map
        cls.olabel_to_word_map = osymbol_table.id_to_word_map
        cls.eps_like_ilabels = tuple(cls.word_to_ilabel_map[word] for word in (cls.eps, cls.eps_disambig))
        cls.silent_olabels = tuple(
            frozenset(cls.word_to_olabel_map[word] for word in cls.silent_words)
            | frozenset(symbol for (word, symbol) in cls.word_to_olabel_map.items() if word.startswith('#nonterm')))
        cls.wildcard_nonterms = frozenset(wildcard_nonterms)
        cls.wildcard_olabels = tuple(cls.word_to_olabel_map[word] for word in cls.wildcard_nonterms)
        assert cls.word_to_ilabel_map[cls.eps] == 0

    def __init__(self):
        super().__init__()
        self.native_obj = self._lib.fst__construct()
        if self.native_obj == _ffi.NULL:
            raise KaldiError("Failed fst__construct")

        result = self._lib.fst__init(len(self.eps_like_ilabels), self.eps_like_ilabels,
            len(self.silent_olabels), self.silent_olabels,
            len(self.wildcard_olabels), self.wildcard_olabels)
        if not result:
            raise KaldiError("Failed fst__init")

        self.num_states = 1  # Is initialized with a start state
        self.num_arcs = 0
        self.filename = None
        self._compiled_native_obj = None

    def __del__(self):
        self.destruct()

    def destruct(self):
        del self.compiled_native_obj
        if self.native_obj is not None:
            result = self._lib.fst__destruct(self.native_obj)
            self.native_obj = None
            if not result:
                raise KaldiError("Failed fst__destruct on %r" % self.native_obj)

    compiled_native_obj = property(lambda self: self._compiled_native_obj)
    @compiled_native_obj.setter
    def compiled_native_obj(self, value):
        del self.compiled_native_obj
        self._compiled_native_obj = value
    @compiled_native_obj.deleter
    def compiled_native_obj(self):
        if self._compiled_native_obj is not None:
            result = self._lib.fst__destruct(self._compiled_native_obj)
            self._compiled_native_obj = None
            if not result:
                raise KaldiError("Failed fst__destruct on %r" % self._compiled_native_obj)

    def add_state(self, weight=None, initial=False, final=False):
        """ Default weight is 1. """
        self.filename = None
        if weight is None:
            weight = 1 if final else 0
        else:
            assert final
        weight = -math.log(weight) if weight != 0 else self.zero
        id = self._lib.fst__add_state(self.native_obj, float(weight), bool(initial))
        if id < 0:
            raise KaldiError("Failed fst__add_state")
        self.num_states += 1
        if initial:
            self.num_arcs += 1
        return id

    def add_arc(self, src_state, dst_state, label, olabel=None, weight=None):
        """ Default weight is 1. None label is replaced by eps. Default olabel of None is replaced by label. """
        self.filename = None
        if label is None: label = self.eps
        if olabel is None: olabel = label
        if weight is None: weight = 1
        weight = -math.log(weight) if weight != 0 else self.zero
        label_id = self.word_to_ilabel_map[label]
        olabel_id = self.word_to_olabel_map[olabel]
        result = self._lib.fst__add_arc(self.native_obj, int(src_state), int(dst_state), int(label_id), int(olabel_id), float(weight))
        if not result:
            raise KaldiError("Failed fst__add_arc")
        self.num_arcs += 1

    def compute_hash(self, dependencies_seed_hash_str='0'*32):
        hash_p = _ffi.new('char[]', 33)  # Length of MD5 hex string + null terminator
        result = self._lib.fst__compute_md5(self.native_obj, hash_p, encode(dependencies_seed_hash_str))
        if not result:
            raise KaldiError("Failed fst__compute_md5")
        hash_str = decode(_ffi.string(hash_p))
        self.filename = hash_str + '.fst'
        return hash_str

    ####################################################################################################################

    def has_eps_path(self, path_src_state, path_dst_state, eps_like_labels=frozenset()):
        """ Returns True iff there is a epsilon path from src_state to dst_state. Uses BFS. Does not follow nonterminals! """
        assert not eps_like_labels
        result = self._lib.fst__has_eps_path(self.native_obj, path_src_state, path_dst_state)
        return result

    def does_match(self, target_words, wildcard_nonterms=(), include_silent=False, output_max_length=1024):
        """ Returns the olabels on a matching path if there is one, False if not. Uses BFS. Wildcard accepts zero or more words. """
        # FIXME: do in decoder!
        assert frozenset(wildcard_nonterms) == self.wildcard_nonterms
        output_p = _ffi.new('int32_t[]', output_max_length)
        output_len_p = _ffi.new('int32_t*', output_max_length)
        target_labels = [self.word_to_ilabel_map[word] for word in target_words]
        result = self._lib.fst__does_match(self.native_obj, len(target_labels), target_labels, output_p, output_len_p)
        if output_len_p[0] > output_max_length:
            raise KaldiError("fst__does_match needed too much output length")
        if result:
            return tuple(self.olabel_to_word_map[symbol]
                for symbol in output_p[0:output_len_p[0]]
                if include_silent or symbol not in self.silent_olabels)
        return False

    ####################################################################################################################

    @classmethod
    def load_file(cls, fst_filename):
        cls.init_ffi()
        native_obj = cls._lib.fst__load_file(encode(fst_filename))
        if not native_obj:
            raise KaldiError("Failed fst__load_file")
        # FIXME: memory leak possible?
        return native_obj

    @classmethod
    def compile_text(cls, fst_text, isymbols_filename, osymbols_filename):
        cls.init_ffi()
        native_obj = cls._lib.fst__compile_text(encode(fst_text), encode(isymbols_filename), encode(osymbols_filename))
        if not native_obj:
            raise KaldiError("Failed fst__compile_text")
        # FIXME: memory leak possible?
        return native_obj


########################################################################################################################

class SymbolTable(object):

    def __init__(self, filename):
        with open(filename, 'r', encoding='utf-8') as file:
            word_id_pairs = [line.strip().split() for line in file]
        self.word_to_id_map = { word: int(id) for (word, id) in word_id_pairs }
        self.id_to_word_map = { id: word for (word, id) in self.word_to_id_map.items() }
        self.max_term_word_id = max(id for (word, id) in self.word_to_id_map.items() if not word.startswith('#nonterm'))

    def add_word(self, word, id=None):
        if id is None:
            self.max_term_word_id += 1
            id = self.max_term_word_id
        else:
            id = int(id)
        self.word_to_id_map[word] = id
        self.id_to_word_map[id] = word

    words = property(lambda self: self.word_to_id_map.keys())

    def __contains__(self, word):
        return (word in self.word_to_id_map)
