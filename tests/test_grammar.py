
from pathlib import Path
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
