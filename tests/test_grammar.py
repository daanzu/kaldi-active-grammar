
from typing import Callable, Optional, Union

import pytest

from kaldi_active_grammar import Compiler, KaldiRule, NativeWFST, WFST
from tests.helpers import *


class TestGrammar:

    @pytest.fixture(autouse=True)
    def setup(self, change_to_test_dir, audio_generator):
        self.compiler = Compiler()
        self.decoder = self.compiler.init_decoder()
        self.audio_generator = audio_generator

    def make_rule(self, name: str, build_func: Callable[[Union[NativeWFST, WFST]], None]):
        rule = KaldiRule(self.compiler, name)
        assert rule.name == name
        assert rule.fst is not None
        build_func(rule.fst)
        rule.compile()
        assert rule.compiled
        rule.load()
        assert rule.loaded
        return rule

    def decode(self, text: str, kaldi_rules_activity: list[bool], expected_rule: KaldiRule, expected_words_are_dictation_mask: Optional[list[bool]] = None):
        self.decoder.decode(self.audio_generator(text), True, kaldi_rules_activity)

        output, info = self.decoder.get_output()
        assert isinstance(output, str)
        assert len(output) > 0
        assert_info_shape(info)

        recognized_rule, words, words_are_dictation_mask = self.compiler.parse_output(output)
        assert recognized_rule == expected_rule
        assert words == text.split()
        if expected_words_are_dictation_mask is None:
            expected_words_are_dictation_mask = [False] * len(words)
        assert words_are_dictation_mask == expected_words_are_dictation_mask

    def test_simple_rule(self):
        def _build(fst):
            initial_state = fst.add_state(initial=True)
            final_state = fst.add_state(final=True)
            fst.add_arc(initial_state, final_state, 'hello')
        rule = self.make_rule('TestRule', _build)
        self.decode("hello", [True], rule)

    def test_epsilon_transition(self):
        """Test epsilon transitions between states."""
        def _build(fst):
            initial_state = fst.add_state(initial=True)
            middle_state = fst.add_state()
            final_state = fst.add_state(final=True)
            fst.add_arc(initial_state, middle_state, None)  # epsilon transition
            fst.add_arc(middle_state, final_state, 'world')
        rule = self.make_rule('EpsilonRule', _build)
        self.decode("world", [True], rule)

    def test_multiple_paths(self):
        """Test grammar with multiple alternative paths (choice)."""
        def _build(fst):
            initial_state = fst.add_state(initial=True)
            final_state = fst.add_state(final=True)
            # Create three alternative paths
            fst.add_arc(initial_state, final_state, 'hello')
            fst.add_arc(initial_state, final_state, 'hi')
            fst.add_arc(initial_state, final_state, 'greetings')
        rule = self.make_rule('MultiPathRule', _build)
        # Test each alternative path
        self.decode("hello", [True], rule)

    def test_multiple_paths_hi(self):
        """Test second alternative in multiple path grammar."""
        def _build(fst):
            initial_state = fst.add_state(initial=True)
            final_state = fst.add_state(final=True)
            fst.add_arc(initial_state, final_state, 'hello')
            fst.add_arc(initial_state, final_state, 'hi')
            fst.add_arc(initial_state, final_state, 'greetings')
        rule = self.make_rule('MultiPathRule2', _build)
        self.decode("hi", [True], rule)

    def test_sequential_chain(self):
        """Test long sequential chain of states."""
        def _build(fst):
            initial_state = fst.add_state(initial=True)
            state1 = fst.add_state()
            state2 = fst.add_state()
            state3 = fst.add_state()
            final_state = fst.add_state(final=True)
            fst.add_arc(initial_state, state1, 'the')
            fst.add_arc(state1, state2, 'quick')
            fst.add_arc(state2, state3, 'brown')
            fst.add_arc(state3, final_state, 'fox')
        rule = self.make_rule('SequentialRule', _build)
        self.decode("the quick brown fox", [True], rule)

    def test_diamond_pattern(self):
        """Test diamond pattern with branch and merge."""
        def _build(fst):
            initial_state = fst.add_state(initial=True)
            branch1 = fst.add_state()
            branch2 = fst.add_state()
            merge_state = fst.add_state()
            final_state = fst.add_state(final=True)

            # Initial arc
            fst.add_arc(initial_state, branch1, 'start')

            # Two branches with different paths
            fst.add_arc(branch1, merge_state, 'left')
            fst.add_arc(branch1, branch2, 'right')
            fst.add_arc(branch2, merge_state, 'path')

            # Merge and continue
            fst.add_arc(merge_state, final_state, 'end')
        rule = self.make_rule('DiamondRule', _build)
        self.decode("start left end", [True], rule)

    def test_diamond_pattern_alt(self):
        """Test alternative path through diamond pattern."""
        def _build(fst):
            initial_state = fst.add_state(initial=True)
            branch1 = fst.add_state()
            branch2 = fst.add_state()
            merge_state = fst.add_state()
            final_state = fst.add_state(final=True)

            fst.add_arc(initial_state, branch1, 'start')
            fst.add_arc(branch1, merge_state, 'left')
            fst.add_arc(branch1, branch2, 'right')
            fst.add_arc(branch2, merge_state, 'path')
            fst.add_arc(merge_state, final_state, 'end')
        rule = self.make_rule('DiamondRule2', _build)
        self.decode("start right path end", [True], rule)

    def test_self_loop(self):
        """Test self-loop for optional repetition."""
        def _build(fst):
            initial_state = fst.add_state(initial=True)
            loop_state = fst.add_state()
            final_state = fst.add_state(final=True)

            fst.add_arc(initial_state, loop_state, 'repeat')
            fst.add_arc(loop_state, loop_state, 'again')  # Self-loop
            fst.add_arc(loop_state, final_state, 'done')
        rule = self.make_rule('LoopRule', _build)
        self.decode("repeat again again done", [True], rule)

    def test_optional_path_with_epsilon(self):
        """Test optional path using epsilon transition."""
        def _build(fst):
            initial_state = fst.add_state(initial=True)
            optional_state = fst.add_state()
            final_state = fst.add_state(final=True)

            # Direct path (skipping optional)
            fst.add_arc(initial_state, final_state, 'hello')

            # Optional path with epsilon
            fst.add_arc(initial_state, optional_state, None)  # epsilon
            fst.add_arc(optional_state, final_state, 'optional')
        rule = self.make_rule('OptionalRule', _build)
        self.decode("hello", [True], rule)

    def test_complex_branching(self):
        """Test complex branching structure with multiple decision points."""
        def _build(fst):
            initial_state = fst.add_state(initial=True)
            branch_a = fst.add_state()
            branch_b = fst.add_state()
            sub_branch_a1 = fst.add_state()
            sub_branch_a2 = fst.add_state()
            final_state = fst.add_state(final=True)

            # First level branching
            fst.add_arc(initial_state, branch_a, 'go')
            fst.add_arc(initial_state, branch_b, 'move')

            # Branch A has sub-branches
            fst.add_arc(branch_a, sub_branch_a1, 'left')
            fst.add_arc(branch_a, sub_branch_a2, 'right')
            fst.add_arc(sub_branch_a1, final_state, 'side')
            fst.add_arc(sub_branch_a2, final_state, 'side')

            # Branch B goes directly to final
            fst.add_arc(branch_b, final_state, 'forward')
        rule = self.make_rule('ComplexBranchRule', _build)
        self.decode("go left side", [True], rule)

    def test_complex_branching_alt1(self):
        """Test alternative path in complex branching."""
        def _build(fst):
            initial_state = fst.add_state(initial=True)
            branch_a = fst.add_state()
            branch_b = fst.add_state()
            sub_branch_a1 = fst.add_state()
            sub_branch_a2 = fst.add_state()
            final_state = fst.add_state(final=True)

            fst.add_arc(initial_state, branch_a, 'go')
            fst.add_arc(initial_state, branch_b, 'move')
            fst.add_arc(branch_a, sub_branch_a1, 'left')
            fst.add_arc(branch_a, sub_branch_a2, 'right')
            fst.add_arc(sub_branch_a1, final_state, 'side')
            fst.add_arc(sub_branch_a2, final_state, 'side')
            fst.add_arc(branch_b, final_state, 'forward')
        rule = self.make_rule('ComplexBranchRule2', _build)
        self.decode("go right side", [True], rule)

    def test_complex_branching_alt2(self):
        """Test third alternative path in complex branching."""
        def _build(fst):
            initial_state = fst.add_state(initial=True)
            branch_a = fst.add_state()
            branch_b = fst.add_state()
            sub_branch_a1 = fst.add_state()
            sub_branch_a2 = fst.add_state()
            final_state = fst.add_state(final=True)

            fst.add_arc(initial_state, branch_a, 'go')
            fst.add_arc(initial_state, branch_b, 'move')
            fst.add_arc(branch_a, sub_branch_a1, 'left')
            fst.add_arc(branch_a, sub_branch_a2, 'right')
            fst.add_arc(sub_branch_a1, final_state, 'side')
            fst.add_arc(sub_branch_a2, final_state, 'side')
            fst.add_arc(branch_b, final_state, 'forward')
        rule = self.make_rule('ComplexBranchRule3', _build)
        self.decode("move forward", [True], rule)

    def test_multiple_epsilon_transitions(self):
        """Test multiple consecutive epsilon transitions."""
        def _build(fst):
            initial_state = fst.add_state(initial=True)
            eps1 = fst.add_state()
            eps2 = fst.add_state()
            eps3 = fst.add_state()
            final_state = fst.add_state(final=True)

            fst.add_arc(initial_state, eps1, None)  # epsilon
            fst.add_arc(eps1, eps2, None)  # epsilon
            fst.add_arc(eps2, eps3, None)  # epsilon
            fst.add_arc(eps3, final_state, 'finish')
        rule = self.make_rule('MultiEpsilonRule', _build)
        self.decode("finish", [True], rule)

    def test_weighted_alternatives(self):
        """Test weighted alternative paths (higher weight should be preferred)."""
        def _build(fst):
            initial_state = fst.add_state(initial=True)
            final_state = fst.add_state(final=True)

            # Add alternatives with different weights
            fst.add_arc(initial_state, final_state, 'test', weight=0.9)  # Higher probability
            fst.add_arc(initial_state, final_state, 'test', weight=0.1)  # Lower probability
        rule = self.make_rule('WeightedRule', _build)
        self.decode("test", [True], rule)

    def test_parallel_sequences(self):
        """Test parallel sequences that merge at the end."""
        def _build(fst):
            initial_state = fst.add_state(initial=True)
            seq1_s1 = fst.add_state()
            seq1_s2 = fst.add_state()
            seq2_s1 = fst.add_state()
            final_state = fst.add_state(final=True)

            # Sequence 1: long path
            fst.add_arc(initial_state, seq1_s1, 'long')
            fst.add_arc(seq1_s1, seq1_s2, 'path')
            fst.add_arc(seq1_s2, final_state, 'here')

            # Sequence 2: short path
            fst.add_arc(initial_state, seq2_s1, 'short')
            fst.add_arc(seq2_s1, final_state, 'way')
        rule = self.make_rule('ParallelRule', _build)
        self.decode("long path here", [True], rule)

    def test_parallel_sequences_alt(self):
        """Test alternative parallel sequence."""
        def _build(fst):
            initial_state = fst.add_state(initial=True)
            seq1_s1 = fst.add_state()
            seq1_s2 = fst.add_state()
            seq2_s1 = fst.add_state()
            final_state = fst.add_state(final=True)

            fst.add_arc(initial_state, seq1_s1, 'long')
            fst.add_arc(seq1_s1, seq1_s2, 'path')
            fst.add_arc(seq1_s2, final_state, 'here')
            fst.add_arc(initial_state, seq2_s1, 'short')
            fst.add_arc(seq2_s1, final_state, 'way')
        rule = self.make_rule('ParallelRule2', _build)
        self.decode("short way", [True], rule)

    def test_nested_loops(self):
        """Test nested loop structures."""
        def _build(fst):
            initial_state = fst.add_state(initial=True)
            outer_loop = fst.add_state()
            inner_loop = fst.add_state()
            exit_state = fst.add_state()
            final_state = fst.add_state(final=True)

            fst.add_arc(initial_state, outer_loop, 'start')
            fst.add_arc(outer_loop, inner_loop, 'inner')
            fst.add_arc(inner_loop, inner_loop, 'repeat')  # Inner self-loop
            fst.add_arc(inner_loop, outer_loop, 'outer')  # Back to outer
            fst.add_arc(outer_loop, exit_state, 'exit')
            fst.add_arc(exit_state, final_state, 'done')
        rule = self.make_rule('NestedLoopRule', _build)
        self.decode("start inner repeat outer exit done", [True], rule)

    def test_multiple_entry_points(self):
        """Test graph with multiple entry points via epsilon."""
        def _build(fst):
            initial_state = fst.add_state(initial=True)
            entry1 = fst.add_state()
            entry2 = fst.add_state()
            merge = fst.add_state()
            final_state = fst.add_state(final=True)

            # Multiple epsilon transitions to different entry points
            fst.add_arc(initial_state, entry1, None)  # epsilon to entry1
            fst.add_arc(initial_state, entry2, None)  # epsilon to entry2

            # Each entry has its own word
            fst.add_arc(entry1, merge, 'alpha')
            fst.add_arc(entry2, merge, 'beta')

            # Merge to final
            fst.add_arc(merge, final_state, 'end')
        rule = self.make_rule('MultiEntryRule', _build)
        self.decode("alpha end", [True], rule)

    def test_cascade_pattern(self):
        """Test cascading pattern with multiple stages."""
        def _build(fst):
            initial_state = fst.add_state(initial=True)
            stage1 = fst.add_state()
            stage2 = fst.add_state()
            stage3 = fst.add_state()
            final_state = fst.add_state(final=True)

            # Stage 1: two options
            fst.add_arc(initial_state, stage1, 'one')
            fst.add_arc(initial_state, stage1, 'two')

            # Stage 2: connects to stage1
            fst.add_arc(stage1, stage2, 'and')

            # Stage 3: two options from stage2
            fst.add_arc(stage2, stage3, 'three')
            fst.add_arc(stage2, stage3, 'four')

            # Final
            fst.add_arc(stage3, final_state, 'done')
        rule = self.make_rule('CascadeRule', _build)
        self.decode("one and three done", [True], rule)

    def test_backtracking_pattern(self):
        """Test pattern that requires backtracking in search."""
        def _build(fst):
            initial_state = fst.add_state(initial=True)
            trap = fst.add_state()  # Dead end
            good_path = fst.add_state()
            final_state = fst.add_state(final=True)

            # First arc is ambiguous
            fst.add_arc(initial_state, trap, 'start')
            fst.add_arc(initial_state, good_path, 'start')

            # Trap has no continuation matching our test
            fst.add_arc(trap, trap, 'wrong')

            # Good path continues
            fst.add_arc(good_path, final_state, 'right')
        rule = self.make_rule('BacktrackRule', _build)
        self.decode("start right", [True], rule)

    def test_very_long_sequence(self):
        """Test very long sequential chain to stress test."""
        def _build(fst):
            words = ['one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten']
            states = [fst.add_state(initial=(i == 0), final=(i == len(words))) for i in range(len(words) + 1)]
            for i, word in enumerate(words):
                fst.add_arc(states[i], states[i + 1], word)
        rule = self.make_rule('LongSequenceRule', _build)
        self.decode("one two three four five six seven eight nine ten", [True], rule)

    def test_hub_and_spoke(self):
        """Test hub-and-spoke pattern with central node."""
        def _build(fst):
            initial_state = fst.add_state(initial=True)
            hub = fst.add_state()
            spoke1 = fst.add_state()
            spoke2 = fst.add_state()
            spoke3 = fst.add_state()
            final_state = fst.add_state(final=True)

            # All paths go through hub
            fst.add_arc(initial_state, hub, 'center')

            # Spokes from hub
            fst.add_arc(hub, spoke1, 'north')
            fst.add_arc(hub, spoke2, 'south')
            fst.add_arc(hub, spoke3, 'east')

            # All spokes lead to final
            fst.add_arc(spoke1, final_state, 'end')
            fst.add_arc(spoke2, final_state, 'end')
            fst.add_arc(spoke3, final_state, 'end')
        rule = self.make_rule('HubSpokeRule', _build)
        self.decode("center north end", [True], rule)
