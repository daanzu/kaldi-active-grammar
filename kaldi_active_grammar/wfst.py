#
# This file is part of kaldi-active-grammar.
# (c) Copyright 2019 by David Zurow
# Licensed under the AGPL-3.0, with exceptions; see LICENSE.txt file.
#

import collections, math

class WFST(object):
    eps = '<eps>'
    zero = float('inf')
    one = 0.0

    def __init__(self):
        self._arc_table = []
        self._state_table = []
        self._state_to_num_arcs = collections.Counter()
        self._next_state_id = 1
        self.start_state = self.add_state()

    def add_state(self, weight=None, initial=False, final=False):
        id = self._next_state_id
        self._next_state_id += 1
        if weight is None:
            weight = self.one if final else self.zero
        else:
            weight = -math.log(weight)
        self._state_table.append((id, weight))
        if initial:
            self.add_arc(self.start_state, id, self.eps)
        return id

    def add_arc(self, src_state, dst_state, label, olabel=None, weight=None):
        if label is None: label = self.eps
        if olabel is None: olabel = label
        weight = self.one if weight is None else -math.log(weight)
        self._arc_table.append([src_state, dst_state, label, olabel, weight])
        self._state_to_num_arcs[src_state] += 1

    @property
    def fst_text(self, eps2disambig=False):
        eps_replacement = '#0' if eps2disambig else self.eps
        text = ''.join("%s %s %s %s %s\n" % (src_state, dst_state, ilabel if ilabel != self.eps else eps_replacement, olabel, weight)
            for (src_state, dst_state, ilabel, olabel, weight) in self._arc_table)
        text += ''.join("%s %s\n" % (id, weight) for (id, weight) in self._state_table if weight is not self.zero)
        return text

    def equalize_weights(self):
        # breakeven 10-13?
        for arc in self._arc_table:
            arc[4] = -math.log(1.0 / self._state_to_num_arcs[arc[0]])
