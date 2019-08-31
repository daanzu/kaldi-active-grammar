#
# This file is part of kaldi-active-grammar.
# (c) Copyright 2019 by David Zurow
# Licensed under the AGPL-3.0, with exceptions; see LICENSE.txt file.
#

import collections, math

from six import iteritems

class WFST(object):
    zero = float('inf')  # weight of non-final states
    one = 0.0
    eps = '<eps>'
    eps_disambig = '#0'
    silent_labels = frozenset((eps, '!SIL'))

    def __init__(self):
        self.clear()

    num_arcs = property(lambda self: len(self._arc_table))
    num_states = property(lambda self: len(self._state_table))

    def clear(self):
        self._arc_table = []  # [src_state, dst_state, label, olabel, weight]
        self._state_table = dict()  # {id: weight}
        self._state_to_num_arcs = collections.Counter()
        self._next_state_id = 0
        self.start_state = self.add_state()

    def add_state(self, weight=None, initial=False, final=False):
        id = self._next_state_id
        self._next_state_id += 1
        if weight is None:
            weight = self.one if final else self.zero
        else:
            weight = -math.log(weight)
        self._state_table[id] = weight
        if initial:
            self.add_arc(self.start_state, id, self.eps)
        return id

    def add_arc(self, src_state, dst_state, label, olabel=None, weight=None):
        if label is None: label = self.eps
        if olabel is None: olabel = label
        weight = self.one if weight is None else -math.log(weight)
        self._arc_table.append([src_state, dst_state, label, olabel, weight])
        self._state_to_num_arcs[src_state] += 1

    def get_fst_text(self, eps2disambig=False):
        eps_replacement = self.eps_disambig if eps2disambig else self.eps
        text = ''.join("%s %s %s %s %s\n" % (src_state, dst_state, str(ilabel) if ilabel != self.eps else eps_replacement, str(olabel), weight)
            for (src_state, dst_state, ilabel, olabel, weight) in self._arc_table)
        text += ''.join("%s %s\n" % (id, weight) for (id, weight) in iteritems(self._state_table) if weight is not self.zero)
        return text

    ####################################################################################################################

    def state_is_final(self, state):
        return (self._state_table[state] != self.zero)

    def label_is_silent(self, label):
        return ((label in self.silent_labels) or (label.startswith('#nonterm')))

    def equalize_weights(self):
        # breakeven 10-13?
        for arc in self._arc_table:
            arc[4] = -math.log(1.0 / self._state_to_num_arcs[arc[0]])

    def has_eps_path(self, src_state, dst_state):
        """Returns True iff there is a epsilon path from src_state to dst_state."""
        eps_like = [self.eps, self.eps_disambig]
        state_queue = collections.deque([src_state])
        queued = set(state_queue)
        while state_queue:
            state = state_queue.pop()
            if state == dst_state:
                return True
            next_states = [dst_state for (src_state, dst_state, label, olabel, weight) in self._arc_table
                if src_state == state and label in eps_like and dst_state not in queued]
            state_queue.extendleft(next_states)
            queued.update(next_states)
        return False

    def does_match(self, target_words, include_silent=False):
        arc_table_dict = collections.defaultdict(list)  # optimization: maps src_state -> a list of its outgoing arcs
        for arc in self._arc_table:
            arc_table_dict[arc[0]].append(arc)

        queue = collections.deque()  # entries: (state, path of arcs to state, index of remaining words)
        queue.append((self.start_state, (), 0))
        while queue:
            state, path, target_word_index = queue.popleft()
            if (target_word_index >= len(target_words)) and self.state_is_final(state):
                return tuple(ilabel for (src_state, dst_state, ilabel, olabel, weight) in path
                    if include_silent or (ilabel not in self.silent_labels))
            for arc in arc_table_dict[state]:
                src_state, dst_state, ilabel, olabel, weight = arc
                assert src_state == state
                if ilabel == target_words[target_word_index]:
                    queue.append((dst_state, path+(arc,), target_word_index+1))
                elif self.label_is_silent(ilabel):
                    queue.append((dst_state, path+(arc,), target_word_index))
        return False
