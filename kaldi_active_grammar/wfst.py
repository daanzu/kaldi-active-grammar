#
# This file is part of kaldi-active-grammar.
# (c) Copyright 2019 by David Zurow
# Licensed under the AGPL-3.0, with exceptions; see LICENSE.txt file.
#

import collections, itertools, math

from six import iteritems, itervalues

class WFST(object):
    zero = float('inf')  # weight of non-final states
    one = 0.0
    eps = '<eps>'
    eps_disambig = '#0'
    silent_labels = frozenset((eps, eps_disambig, '!SIL'))

    def __init__(self):
        self.clear()

    def clear(self):
        self._arc_table_dict = collections.defaultdict(list)  # {src_state: [[src_state, dst_state, label, olabel, weight], ...]}  # list of its outgoing arcs
        self._state_table = dict()  # {id: weight}
        self._state_to_num_arcs = collections.Counter()
        self._next_state_id = 0
        self.start_state = self.add_state()

    num_arcs = property(lambda self: sum(len(arc_list) for arc_list in itervalues(self._arc_table_dict)))
    num_states = property(lambda self: len(self._state_table))

    def iter_arcs(self):
        return itertools.chain.from_iterable(itervalues(self._arc_table_dict))

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
        self._arc_table_dict[src_state].append([src_state, dst_state, label, olabel, weight])
        self._state_to_num_arcs[src_state] += 1

    def get_fst_text(self, eps2disambig=False):
        eps_replacement = self.eps_disambig if eps2disambig else self.eps
        text = ''.join("%s %s %s %s %s\n" % (src_state, dst_state, str(ilabel) if ilabel != self.eps else eps_replacement, str(olabel), weight)
            for (src_state, dst_state, ilabel, olabel, weight) in self.iter_arcs())
        text += ''.join("%s %s\n" % (id, weight) for (id, weight) in iteritems(self._state_table) if weight is not self.zero)
        return text

    ####################################################################################################################

    def state_is_final(self, state):
        return (self._state_table[state] != self.zero)

    def label_is_silent(self, label):
        return ((label in self.silent_labels) or (label.startswith('#nonterm')))

    def equalize_weights(self):
        # breakeven 10-13?
        for arc in self.iter_arcs():
            arc[4] = -math.log(1.0 / self._state_to_num_arcs[arc[0]])

    def has_eps_path(self, src_state, dst_state):
        """ Returns True iff there is a epsilon path from src_state to dst_state. """
        eps_like = [self.eps, self.eps_disambig]
        state_queue = collections.deque([src_state])
        queued = set(state_queue)
        while state_queue:
            state = state_queue.pop()
            if state == dst_state:
                return True
            next_states = [dst_state for (src_state, dst_state, label, olabel, weight) in self.iter_arcs()
                if src_state == state and label in eps_like and dst_state not in queued]
            state_queue.extendleft(next_states)
            queued.update(next_states)
        return False

    def does_match(self, target_words, wildcard_nonterms=(), include_silent=False):
        """ Returns the ilabels on a matching path if there is one, False if not. Uses BFS. Wildcard accepts zero or more words. """
        # from IPython import embed; embed()
        # print(self.get_fst_text())
        queue = collections.deque()  # entries: (state, path of ilabels of arcs to state, index of remaining words)
        queue.append((self.start_state, (), 0))
        while queue:
            state, path, target_word_index = queue.popleft()
            # print(state, path, target_words[target_word_index])
            # import ipdb; ipdb.set_trace()
            target_word = target_words[target_word_index] if target_word_index < len(target_words) else None
            if (target_word is None) and self.state_is_final(state):
                return tuple(ilabel for ilabel in path
                    if include_silent or not self.label_is_silent(ilabel))
            for arc in self._arc_table_dict[state]:
                src_state, dst_state, ilabel, olabel, weight = arc
                if (target_word is not None) and (ilabel == target_word):
                    queue.append((dst_state, path+(ilabel,), target_word_index+1))
                elif ilabel in wildcard_nonterms:
                    if target_word is not None:
                        queue.append((src_state, path+(target_word,), target_word_index+1))  # accept word and stay
                        # queue.append((dst_state, path+(target_word,), target_word_index+1))  # accept word and transition
                    queue.append((dst_state, path+(ilabel,), target_word_index))  # epsilon transition
                elif self.label_is_silent(ilabel):
                    queue.append((dst_state, path+(ilabel,), target_word_index))  # epsilon transition
        return False
