#
# This file is part of kaldi-active-grammar.
# (c) Copyright 2019 by David Zurow
# Licensed under the AGPL-3.0; see LICENSE.txt file.
#

import collections, itertools, math

from six import iteritems, itervalues, text_type

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

    def __init__(self):
        self.clear()

    def clear(self):
        self._arc_table_dict = collections.defaultdict(list)  # { src_state: [[src_state, dst_state, label, olabel, weight], ...] }  # list of its outgoing arcs
        self._state_table = dict()  # { id: weight }
        self._next_state_id = 0
        self.start_state = self.add_state()

    num_arcs = property(lambda self: sum(len(arc_list) for arc_list in itervalues(self._arc_table_dict)))
    num_states = property(lambda self: len(self._state_table))

    def iter_arcs(self):
        return itertools.chain.from_iterable(itervalues(self._arc_table_dict))

    def is_state_final(self, state):
        return (self._state_table[state] != 0)

    def add_state(self, weight=None, initial=False, final=False):
        """ Default weight is 1. """
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
        if label is None: label = self.eps
        if olabel is None: olabel = label
        if weight is None: weight = 1
        self._arc_table_dict[src_state].append(
            [int(src_state), int(dst_state), text_type(label), text_type(olabel), float(weight)])

    def get_fst_text(self, eps2disambig=False):
        eps_replacement = self.eps_disambig if eps2disambig else self.eps
        states_text = u''.join("%d %d %s %s %f\n" % (
                src_state,
                dst_state,
                ilabel if ilabel != self.eps else eps_replacement,
                olabel,
                -math.log(weight) if weight != 0 else self.zero,
            )
            for (src_state, dst_state, ilabel, olabel, weight) in self.iter_arcs())
        arcs_text = u''.join("%d %f\n" % (
                id,
                -math.log(weight) if weight != 0 else self.zero,
            )
            for (id, weight) in iteritems(self._state_table)
            if weight != 0)
        return states_text + arcs_text

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
        """ Returns True iff there is a epsilon path from src_state to dst_state. Uses BFS. Does not follow nonterminals! """
        # Used in: dragonfly backend compiler.
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
        """ Returns the olabels on a matching path if there is one, False if not. Uses BFS. Wildcard accepts zero or more words. """
        # Used in: KaldiAG compiler.
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
                        path += (olabel,)
                    if target_word is not None:
                        queue.append((src_state, path+(target_word,), target_word_index+1))  # accept word and stay
                    queue.append((dst_state, path, target_word_index))  # epsilon transition; already added olabel above or previously
                elif self.label_is_silent(ilabel):
                    queue.append((dst_state, path+(olabel,), target_word_index))  # epsilon transition
        return False
