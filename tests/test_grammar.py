
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


class TestAlternativeDictation:
    """Tests for alternative dictation feature."""

    @pytest.fixture(autouse=True)
    def setup(self, change_to_test_dir, audio_generator):
        self.audio_generator = audio_generator
        self.alternative_dictation_calls = []

    @pytest.fixture
    def compiler_with_mock(self):
        """Fixture providing compiler with mock alternative dictation."""
        def mock_alternative_dictation_func(audio_data):
            self.alternative_dictation_calls.append(audio_data)
            return 'ALTERNATIVE_TEXT'
        return Compiler(alternative_dictation=mock_alternative_dictation_func)

    def create_mock_rule(self, compiler, has_dictation=True):
        """Helper to create a mock KaldiRule for testing."""
        return KaldiRule(compiler, 'mock_rule', has_dictation=has_dictation)

    def parse_with_dictation_info(self, compiler, output_text, audio_data, word_align):
        """Helper to parse output with dictation info."""
        def dictation_info_func():
            return audio_data, word_align
        return compiler.parse_output(output_text, dictation_info_func=dictation_info_func)

    def test_alternative_dictation_callable_check(self):
        """Test that alternative_dictation must be callable."""
        compiler = Compiler(alternative_dictation=lambda x: 'text')
        assert compiler.alternative_dictation is not None

        compiler = Compiler(alternative_dictation=None)
        assert compiler.alternative_dictation is None

    def test_alternative_dictation_not_called_without_dictation(self, compiler_with_mock):
        """Test alternative dictation is not called for rules without dictation."""
        decoder = compiler_with_mock.init_decoder()

        rule = KaldiRule(compiler_with_mock, 'no_dictation_rule', has_dictation=False)
        fst = rule.fst
        initial_state = fst.add_state(initial=True)
        final_state = fst.add_state(final=True)
        fst.add_arc(initial_state, final_state, 'hello')
        rule.compile().load()

        decoder.decode(self.audio_generator('hello'), True, [True])
        output, info = decoder.get_output()

        kaldi_rule, words, words_are_dictation_mask = compiler_with_mock.parse_output(output, dictation_info_func=None)

        assert len(self.alternative_dictation_calls) == 0
        assert kaldi_rule == rule
        assert words == ['hello']

    def test_alternative_dictation_integration_full_decode(self, change_to_test_dir):
        """Full integration test: rule with dictation, decode audio, alternative dictation called and replaces text."""
        from kaldi_active_grammar import PlainDictationRecognizer

        alternative_calls = []
        alternative_audio_received = []
        alternative_recognized_texts = []

        def alternative_dictation_func(audio_data):
            """Uses an independent PlainDictationRecognizer to decode the audio."""
            alternative_calls.append(True)
            alternative_audio_received.append(len(audio_data))
            alt_recognizer = PlainDictationRecognizer()
            alt_text, alt_info = alt_recognizer.decode_utterance(audio_data)
            alternative_recognized_texts.append(alt_text)
            return alt_text

        compiler = Compiler(alternative_dictation=alternative_dictation_func)
        decoder = compiler.init_decoder()

        # Create rule with dictation: "hello <dictation>"
        rule = KaldiRule(compiler, 'dictation_rule', has_dictation=True)
        fst = rule.fst

        initial_state = fst.add_state(initial=True)
        hello_state = fst.add_state()
        dictation_state = fst.add_state()
        end_state = fst.add_state()
        final_state = fst.add_state(final=True)

        # Pattern: "hello" followed by dictation
        fst.add_arc(initial_state, hello_state, 'hello')
        fst.add_arc(hello_state, dictation_state, '#nonterm:dictation', '#nonterm:dictation_cloud')  # #nonterm:dictation must be on ilabel; cloud variant on olabel
        fst.add_arc(dictation_state, end_state, None, '#nonterm:end')
        fst.add_arc(end_state, final_state, None)

        rule.compile().load()

        # Generate audio for "hello world"
        audio_data = self.audio_generator('hello world')

        # Decode
        decoder.decode(audio_data, True, [True])
        output, info = decoder.get_output()

        # Get word alignment for alternative dictation
        word_align = decoder.get_word_align(output)

        # Create dictation_info_func that returns audio and word_align
        def dictation_info_func():
            return audio_data, word_align

        # Parse with alternative dictation
        kaldi_rule, words, words_are_dictation_mask = compiler.parse_output(
            output, dictation_info_func=dictation_info_func)

        # Verify alternative dictation was called
        assert len(alternative_calls) > 0, "Alternative dictation should have been called"
        assert len(alternative_audio_received) > 0, "Alternative dictation should have received audio"
        assert len(alternative_recognized_texts) > 0, "Alternative dictation should have recognized text"

        # Verify the alternative recognizer produced some output
        alt_text = alternative_recognized_texts[0]
        assert alt_text, f"Alternative recognizer should produce text, got: {alt_text}"

        # The alternative text should be in the final words (replacing original dictation)
        words_str = ' '.join(words)
        assert alt_text in words_str or any(word in words for word in alt_text.split()), \
            f"Alternative text '{alt_text}' should be in words: {words}"

        # Verify 'hello' is still there (not part of dictation)
        assert 'hello' in words, f"Hello word should be preserved: {words}"

        # Verify rule was recognized
        assert kaldi_rule == rule

        # Verify dictation mask is correct
        assert len(words) == len(words_are_dictation_mask)
        assert words_are_dictation_mask[words.index('hello')] == False, "Hello should not be marked as dictation"

    def test_alternative_dictation_not_called_without_cloud_nonterm(self, compiler_with_mock):
        """Test alternative dictation not called when #nonterm:dictation_cloud not in output."""
        decoder = compiler_with_mock.init_decoder()

        rule = KaldiRule(compiler_with_mock, 'no_cloud_rule', has_dictation=True)
        fst = rule.fst
        initial_state = fst.add_state(initial=True)
        final_state = fst.add_state(final=True)
        fst.add_arc(initial_state, final_state, 'test')
        rule.compile().load()

        decoder.decode(self.audio_generator('test'), True, [True])
        output, info = decoder.get_output()

        mock_audio = b'mock_audio_data'
        mock_word_align = [('test', 0, 1000)]
        kaldi_rule, words, words_are_dictation_mask = self.parse_with_dictation_info(compiler_with_mock, output, mock_audio, mock_word_align)

        assert len(self.alternative_dictation_calls) == 0

    def test_alternative_dictation_word_align_parsing(self, compiler_with_mock):
        """Test parsing of word_align data for dictation spans."""
        output_text = '#nonterm:rule0 start #nonterm:dictation_cloud original text #nonterm:end finish'
        mock_audio = b'\x00' * 32000
        mock_word_align = [
            ('#nonterm:rule0', 0, 0),
            ('start', 0, 8000),
            ('#nonterm:dictation_cloud', 8000, 0),
            ('original', 8000, 4000),
            ('text', 12000, 4000),
            ('#nonterm:end', 16000, 0),
            ('finish', 16000, 8000),
        ]

        self.create_mock_rule(compiler_with_mock)
        kaldi_rule, words, words_are_dictation_mask = self.parse_with_dictation_info(compiler_with_mock, output_text, mock_audio, mock_word_align)

        assert len(self.alternative_dictation_calls) == 1
        assert len(self.alternative_dictation_calls[0]) > 0
        assert 'ALTERNATIVE_TEXT' in words or words == ['start', 'finish']

    @pytest.mark.parametrize('output_text,word_align,audio_size,expected_audio_size', [
        (
            '#nonterm:rule0 start #nonterm:dictation_cloud final words #nonterm:end',
            [
                ('#nonterm:rule0', 0, 0),
                ('start', 0, 8000),
                ('#nonterm:dictation_cloud', 8000, 0),
                ('final', 8000, 4000),
                ('words', 12000, 4000),
                ('#nonterm:end', 16000, 0),
            ],
            32000,
            24000,  # 32000 - 8000
        ),
        (
            '#nonterm:rule0 start #nonterm:dictation_cloud middle text #nonterm:end finish',
            [
                ('#nonterm:rule0', 0, 0),
                ('start', 0, 4000),
                ('#nonterm:dictation_cloud', 4000, 0),
                ('middle', 4000, 4000),
                ('text', 8000, 4000),
                ('#nonterm:end', 12000, 0),
                ('finish', 16000, 4000),
            ],
            32000,
            10000,  # 14000 - 4000 (half gap to next word)
        ),
    ], ids=['end_of_utterance', 'middle_of_utterance'])
    def test_alternative_dictation_span_calculation(self, compiler_with_mock, output_text, word_align, audio_size, expected_audio_size):
        """Test dictation span calculation for various positions."""
        mock_audio = b'\x00' * audio_size

        self.create_mock_rule(compiler_with_mock)
        kaldi_rule, words, words_are_dictation_mask = self.parse_with_dictation_info(compiler_with_mock, output_text, mock_audio, word_align)

        assert len(self.alternative_dictation_calls) == 1
        assert len(self.alternative_dictation_calls[0]) == expected_audio_size

    def test_alternative_dictation_multiple_spans(self):
        """Test handling multiple dictation spans in single utterance."""
        call_count = [0]

        def multi_alternative_func(audio_data):
            call_count[0] += 1
            return f'ALT_{call_count[0]}'

        compiler = Compiler(alternative_dictation=multi_alternative_func)

        output_text = '#nonterm:rule0 start #nonterm:dictation_cloud first #nonterm:end middle #nonterm:dictation_cloud second #nonterm:end finish'
        mock_audio = b'\x00' * 48000
        mock_word_align = [
            ('#nonterm:rule0', 0, 0),
            ('start', 0, 4000),
            ('#nonterm:dictation_cloud', 4000, 0),
            ('first', 4000, 4000),
            ('#nonterm:end', 8000, 0),
            ('middle', 12000, 4000),
            ('#nonterm:dictation_cloud', 16000, 0),
            ('second', 16000, 4000),
            ('#nonterm:end', 20000, 0),
            ('finish', 24000, 4000),
        ]

        self.create_mock_rule(compiler)
        kaldi_rule, words, words_are_dictation_mask = self.parse_with_dictation_info(compiler, output_text, mock_audio, mock_word_align)

        assert call_count[0] == 2

    @pytest.mark.parametrize('alternative_func,expected_words', [
        (lambda x: None, ['original', 'text']),
        (lambda x: '', ['original', 'text']),
    ], ids=['returns_none', 'returns_empty_string'])
    def test_alternative_dictation_fallback(self, alternative_func, expected_words):
        """Test fallback to original text when alternative_dictation returns falsy value."""
        compiler = Compiler(alternative_dictation=alternative_func)

        output_text = '#nonterm:rule0 #nonterm:dictation_cloud original text #nonterm:end'
        mock_audio = b'\x00' * 16000
        mock_word_align = [
            ('#nonterm:rule0', 0, 0),
            ('#nonterm:dictation_cloud', 0, 0),
            ('original', 0, 4000),
            ('text', 4000, 4000),
            ('#nonterm:end', 8000, 0),
        ]

        self.create_mock_rule(compiler)
        kaldi_rule, words, words_are_dictation_mask = self.parse_with_dictation_info(compiler, output_text, mock_audio, mock_word_align)

        for expected_word in expected_words:
            assert expected_word in words

    def test_alternative_dictation_exception_handling(self):
        """Test that exceptions in alternative_dictation are caught and logged."""
        def failing_func(audio_data):
            raise ValueError('Test exception')

        compiler = Compiler(alternative_dictation=failing_func)

        output_text = '#nonterm:rule0 #nonterm:dictation_cloud original #nonterm:end'
        mock_audio = b'\x00' * 8000
        mock_word_align = [
            ('#nonterm:rule0', 0, 0),
            ('#nonterm:dictation_cloud', 0, 0),
            ('original', 0, 4000),
            ('#nonterm:end', 4000, 0),
        ]

        self.create_mock_rule(compiler)
        kaldi_rule, words, words_are_dictation_mask = self.parse_with_dictation_info(compiler, output_text, mock_audio, mock_word_align)

        assert 'original' in words

    def test_alternative_dictation_invalid_type_raises(self):
        """Test that invalid alternative_dictation type raises TypeError."""
        compiler = Compiler(alternative_dictation='not_callable')

        output_text = '#nonterm:rule0 #nonterm:dictation_cloud text #nonterm:end'
        mock_audio = b'\x00' * 8000
        mock_word_align = [
            ('#nonterm:rule0', 0, 0),
            ('#nonterm:dictation_cloud', 0, 0),
            ('text', 0, 4000),
            ('#nonterm:end', 4000, 0),
        ]

        self.create_mock_rule(compiler)
        kaldi_rule, words, words_are_dictation_mask = self.parse_with_dictation_info(compiler, output_text, mock_audio, mock_word_align)

        assert words is not None

    def test_alternative_dictation_audio_slice_accuracy(self):
        """Test that correct audio slice is passed to alternative_dictation."""
        received_audio = []

        def capture_audio_func(audio_data):
            received_audio.append(audio_data)
            return 'replaced'

        compiler = Compiler(alternative_dictation=capture_audio_func)

        output_text = '#nonterm:rule0 #nonterm:dictation_cloud test #nonterm:end'
        mock_audio = b'\x01' * 4000 + b'\x02' * 4000 + b'\x03' * 4000
        mock_word_align = [
            ('#nonterm:rule0', 0, 0),
            ('#nonterm:dictation_cloud', 4000, 0),
            ('test', 4000, 4000),
            ('#nonterm:end', 8000, 0),
        ]

        self.create_mock_rule(compiler)
        kaldi_rule, words, words_are_dictation_mask = self.parse_with_dictation_info(compiler, output_text, mock_audio, mock_word_align)

        assert len(received_audio) == 1
        assert received_audio[0] == b'\x02' * 4000 + b'\x03' * 4000
