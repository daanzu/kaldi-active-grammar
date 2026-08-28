#
# This file is part of kaldi-active-grammar.
# (c) Copyright 2019 by David Zurow
# Licensed under the AGPL-3.0; see LICENSE.txt file.
#

import collections, hashlib, itertools, math

from six import iteritems, itervalues, text_type

from . import KaldiError


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

    def get_fst_text(self, eps2disambig=False):
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
        return arcs_text + states_text

    def compute_hash(self, dependencies_seed_hash_str='0'*32, eps2disambig=False):
        if not isinstance(dependencies_seed_hash_str, text_type):
            dependencies_seed_hash_str = text_type(dependencies_seed_hash_str)
        hasher = hashlib.md5()
        hasher.update(dependencies_seed_hash_str.encode('utf-8'))
        hasher.update(self.get_fst_text(eps2disambig=eps2disambig).encode('utf-8'))
        hash_str = text_type(hasher.hexdigest())
        self.filename = hash_str + '.fst'
        return hash_str

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
        """Return matching olabels, or False if there is no match.

        Uses BFS and accepts zero or more words for wildcard nonterminals.
        Currently unused in-package, but retained as a public utility.
        """
        queue = collections.deque()  # entries: (state, path of olabels of arcs to state, index into target_words of remaining words)
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
        DRAGONFLY_API bool fst__add_arcs(void* fst_vp, int32_t num_arcs, const int32_t src_state_ids_cp[], const int32_t dst_state_ids_cp[], const int32_t ilabels_cp[], const int32_t olabels_cp[], const float weights_cp[]);
        DRAGONFLY_API bool fst__compute_md5(void* fst_vp, char* md5_cp, char* dependencies_seed_md5_cp);
        DRAGONFLY_API bool fst__has_path(void* fst_vp);
        DRAGONFLY_API bool fst__has_eps_path(void* fst_vp, int32_t path_src_state, int32_t path_dst_state);
        DRAGONFLY_API bool fst__does_match(void* fst_vp, int32_t target_labels_len, int32_t target_labels_cp[], int32_t output_labels_cp[], int32_t* output_labels_len);
        DRAGONFLY_API void* fst__load_file(char* filename_cp);
        DRAGONFLY_API bool fst__write_file(void* fst_vp, char* filename_cp);
        DRAGONFLY_API bool fst__write_file_const(void* fst_vp, char* filename_cp);
        DRAGONFLY_API bool fst__print(void* fst_vp, char* filename_cp);
        DRAGONFLY_API void* fst__compile_text(char* fst_text_cp, char* isymbols_file_cp, char* osymbols_file_cp);
    """

    zero = float('inf')  # Weight of non-final states; a state is final if and only if its weight is not equal to self.zero
    one = 0.0
    eps = u'<eps>'
    eps_disambig = u'#0'
    silent_words = frozenset((eps, eps_disambig, u'!SIL'))
    native = property(lambda self: True)
    arc_batch_size = 4096

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

        cls.init_ffi()
        result = cls._lib.fst__init(len(cls.eps_like_ilabels), cls.eps_like_ilabels,
            len(cls.silent_olabels), cls.silent_olabels,
            len(cls.wildcard_olabels), cls.wildcard_olabels)
        if not result:
            raise KaldiError("Failed fst__init")

    def __init__(self):
        super().__init__()
        self._construct()

    def _construct(self):
        native_obj = self._lib.fst__construct()
        if native_obj == _ffi.NULL:
            raise KaldiError("Failed fst__construct")
        self.native_obj = self._own_native(native_obj, self._lib.fst__destruct, 'native WFST')

        self.num_states = 1  # Is initialized with a start state
        self.num_arcs = 0
        self.filename = None
        self._compiled_native_obj = None
        self._reset_pending_arcs()

    def _reset_pending_arcs(self):
        self._pending_arc_src_state_ids = []
        self._pending_arc_dst_state_ids = []
        self._pending_arc_ilabels = []
        self._pending_arc_olabels = []
        self._pending_arc_weights = []

    def close(self):
        cleanup_error = None
        try:
            del self.compiled_native_obj
        except Exception as error:
            cleanup_error = error
        try:
            self._release_native('native_obj', self._lib.fst__destruct, 'native WFST')
        except Exception as error:
            if cleanup_error is None:
                cleanup_error = error
        self._reset_pending_arcs()
        if cleanup_error is not None:
            raise cleanup_error

    @property
    def compiled_native_obj(self):
        return self._get_compiled_native_obj()

    @compiled_native_obj.setter
    def compiled_native_obj(self, value):
        if value is None or value == _ffi.NULL:
            raise KaldiError("Cannot assign closed compiled native WFST")
        owned_value = self._own_native(value, self._lib.fst__destruct, 'compiled native WFST')
        del self.compiled_native_obj
        self._compiled_native_obj = owned_value
    @compiled_native_obj.deleter
    def compiled_native_obj(self):
        self._release_native('_compiled_native_obj', self._lib.fst__destruct, 'compiled native WFST')

    def clear(self):
        self.close()
        self._construct()

    def _get_native_obj(self):
        self._flush_pending_arcs()
        return self._get_raw_native_obj()

    def _get_raw_native_obj(self):
        return self._require_native(getattr(self, 'native_obj', None), 'native WFST')

    def _get_compiled_native_obj(self):
        return self._require_native(getattr(self, '_compiled_native_obj', None), 'compiled native WFST')

    def add_state(self, weight=None, initial=False, final=False):
        """ Default weight is 1. """
        self.filename = None
        if weight is None:
            weight = 1 if final else 0
        else:
            assert final
        weight = -math.log(weight) if weight != 0 else self.zero
        # An initial state adds an epsilon arc from state 0 natively. Flush
        # first so its insertion order remains consistent with scalar builds.
        if initial:
            self._flush_pending_arcs()
        id = self._lib.fst__add_state(self._get_raw_native_obj(), float(weight), bool(initial))
        if id < 0:
            raise KaldiError("Failed fst__add_state")
        self.num_states += 1
        if initial:
            self.num_arcs += 1
        return id

    def add_arc(self, src_state, dst_state, label, olabel=None, weight=None):
        """ Default weight is 1. None label is replaced by eps. Default olabel of None is replaced by label. """
        self.filename = None
        self._get_raw_native_obj()
        if label is None: label = self.eps
        if olabel is None: olabel = label
        if weight is None: weight = 1
        weight = -math.log(weight) if weight != 0 else self.zero
        label_id = self.word_to_ilabel_map[label]
        olabel_id = self.word_to_olabel_map[olabel]
        self._queue_arc(int(src_state), int(dst_state), int(label_id), int(olabel_id), float(weight))

    def add_arcs(self, arcs):
        """Add an iterable of ``(src, dst, label[, olabel[, weight]])`` arcs."""
        self.filename = None
        self._get_raw_native_obj()
        word_to_ilabel = self.word_to_ilabel_map
        word_to_olabel = self.word_to_olabel_map

        for arc in arcs:
            if not 3 <= len(arc) <= 5:
                raise ValueError("Each arc must contain 3 to 5 values")
            src_state, dst_state, label = arc[:3]
            olabel = arc[3] if len(arc) >= 4 else None
            weight = arc[4] if len(arc) >= 5 else None
            if label is None: label = self.eps
            if olabel is None: olabel = label
            if weight is None: weight = 1

            self._queue_arc(
                int(src_state), int(dst_state),
                int(word_to_ilabel[label]), int(word_to_olabel[olabel]),
                float(-math.log(weight) if weight != 0 else self.zero))

    def _queue_arc(self, src_state, dst_state, ilabel, olabel, weight):
        self._pending_arc_src_state_ids.append(src_state)
        self._pending_arc_dst_state_ids.append(dst_state)
        self._pending_arc_ilabels.append(ilabel)
        self._pending_arc_olabels.append(olabel)
        self._pending_arc_weights.append(weight)
        self.num_arcs += 1
        if len(self._pending_arc_src_state_ids) >= self.arc_batch_size:
            self._flush_pending_arcs()

    def _flush_pending_arcs(self):
        src_state_ids = getattr(self, '_pending_arc_src_state_ids', ())
        num_arcs = len(src_state_ids)
        if num_arcs == 0:
            return
        result = self._lib.fst__add_arcs(
            self._get_raw_native_obj(), num_arcs,
            _ffi.new('int32_t[]', src_state_ids),
            _ffi.new('int32_t[]', self._pending_arc_dst_state_ids),
            _ffi.new('int32_t[]', self._pending_arc_ilabels),
            _ffi.new('int32_t[]', self._pending_arc_olabels),
            _ffi.new('float[]', self._pending_arc_weights),
        )
        if not result:
            raise KaldiError("Failed fst__add_arcs")
        self._reset_pending_arcs()

    def compute_hash(self, dependencies_seed_hash_str='0'*32):
        hash_p = _ffi.new('char[]', 33)  # Length of MD5 hex string + null terminator
        result = self._lib.fst__compute_md5(self._get_native_obj(), hash_p, encode(dependencies_seed_hash_str))
        if not result:
            raise KaldiError("Failed fst__compute_md5")
        hash_str = decode(_ffi.string(hash_p))
        self.filename = hash_str + '.fst'
        return hash_str

    ####################################################################################################################

    def has_path(self):
        """ Returns True iff there is a path (from start state to a final state). Uses BFS. Assumes can nonterminals succeed. """
        result = self._lib.fst__has_path(self._get_native_obj())
        return result

    def has_eps_path(self, path_src_state, path_dst_state, eps_like_labels=frozenset()):
        """ Returns True iff there is a epsilon-like-only path from src_state to dst_state. Uses BFS. Does not follow nonterminals! """
        assert not eps_like_labels
        result = self._lib.fst__has_eps_path(self._get_native_obj(), path_src_state, path_dst_state)
        return result

    def does_match(self, target_words, wildcard_nonterms=(), include_silent=False, output_max_length=1024):
        """Return matching olabels, or False if there is no match.

        Uses the native BFS implementation and accepts zero or more words for
        wildcard nonterminals. Currently unused in-package, but retained as a
        public utility.
        """
        # FIXME: do in decoder!
        assert frozenset(wildcard_nonterms) == self.wildcard_nonterms
        output_p = _ffi.new('int32_t[]', output_max_length)
        output_len_p = _ffi.new('int32_t*', output_max_length)
        target_labels = [self.word_to_ilabel_map[word] for word in target_words]
        result = self._lib.fst__does_match(self._get_native_obj(), len(target_labels), target_labels, output_p, output_len_p)
        if output_len_p[0] > output_max_length:
            raise KaldiError("fst__does_match needed too much output length")
        if result:
            return tuple(self.olabel_to_word_map[symbol]
                for symbol in output_p[0:output_len_p[0]]
                if include_silent or symbol not in self.silent_olabels)
        return False

    ####################################################################################################################

    def write_file(self, fst_filename):
        result = self._lib.fst__write_file(self._get_native_obj(), encode(fst_filename))
        if not result:
            raise KaldiError("Failed fst__write_file")

    def write_file_const(self, fst_filename):
        result = self._lib.fst__write_file_const(self._get_native_obj(), encode(fst_filename))
        if not result:
            raise KaldiError("Failed fst__write_file")

    def print(self, fst_filename=None):
        result = self._lib.fst__print(self._get_native_obj(), (encode(fst_filename) if fst_filename is not None else _ffi.NULL))
        if not result:
            raise KaldiError("Failed fst__print")

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

    def __init__(self, filename=None):
        self.word_to_id_map = dict()
        self.id_to_word_map = dict()
        self.max_term_word_id = -1
        self.longest_word = None
        if filename is not None:
            self.load_text_file(filename)

    def load_text_file(self, filename):
        word_to_id_map = {}
        longest_word = None
        with open(filename, 'r', encoding='utf-8') as file:
            for line_number, line in enumerate(file, 1):
                tokens = line.split()
                if len(tokens) != 2:
                    raise ValueError(
                        "invalid symbol table entry in %r at line %d: expected 2 fields, got %d"
                        % (filename, line_number, len(tokens)))
                word, id_text = tokens
                try:
                    word_id = int(id_text)
                except ValueError:
                    raise ValueError(
                        "invalid symbol ID in %r at line %d: %r"
                        % (filename, line_number, id_text))
                word_to_id_map[word] = word_id
                if longest_word is None or len(word) > len(longest_word):
                    longest_word = word

        if not word_to_id_map:
            raise ValueError("empty symbol table: %r" % filename)

        # Construct this from the completed forward map rather than directly
        # from file entries. This preserves the existing last-wins behavior
        # when a table contains duplicate words or IDs.
        id_to_word_map = { id: word for (word, id) in word_to_id_map.items() }
        max_term_word_id = max((
            id for (word, id) in word_to_id_map.items()
            if not word.startswith('#nonterm')
        ), default=None)
        if max_term_word_id is None:
            raise ValueError("symbol table has no terminal words: %r" % filename)

        # These dictionaries are captured by NativeWFST.init_class(). Preserve
        # their identity when reloading after a lexicon update.
        self.word_to_id_map.clear()
        self.id_to_word_map.clear()
        self.word_to_id_map.update(word_to_id_map)
        self.id_to_word_map.update(id_to_word_map)
        self.max_term_word_id = max_term_word_id
        self.longest_word = longest_word

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
