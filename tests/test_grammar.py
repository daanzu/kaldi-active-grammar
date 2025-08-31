
from pathlib import Path

import pytest

from kaldi_active_grammar import Compiler, KaldiRule
from tests.helpers import *


class TestGrammar:

    @pytest.fixture(autouse=True)
    def setup(self, monkeypatch):
        monkeypatch.chdir(Path(__file__).parent)  # Where model is
        self.compiler = Compiler()
        self.decoder = self.compiler.init_decoder()

    def test_simple_rule_creation_and_compilation(self, audio_generator):
        """ Test basic rule creation and compilation """
        rule = KaldiRule(self.compiler, 'TestRule')
        assert rule.name == 'TestRule'
        assert rule.fst is not None

        fst = rule.fst
        initial_state = fst.add_state(initial=True)
        final_state = fst.add_state(final=True)
        fst.add_arc(initial_state, final_state, 'hello')

        rule.compile()
        assert rule.compiled
        rule.load()
        assert rule.loaded

        self.decoder.decode(audio_generator("hello"), True, [True])

        output, info = self.decoder.get_output()
        assert isinstance(output, str)
        assert len(output) > 0
        assert_info_shape(info)

        recognized_rule, words, words_are_dictation_mask = self.compiler.parse_output(output)
        assert recognized_rule == rule
        assert words == ['hello']
        assert words_are_dictation_mask == [False]
