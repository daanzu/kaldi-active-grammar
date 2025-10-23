
from pathlib import Path
import random

import pytest

from kaldi_active_grammar import PlainDictationRecognizer
from tests.helpers import *


class TestPlainDictation:

    @pytest.fixture(autouse=True)
    def setup(self, change_to_test_dir):
        self.recognizer = PlainDictationRecognizer()

    def test_initialization(self):
        """ Test recognizer initialization """
        assert isinstance(self.recognizer, PlainDictationRecognizer)

    def test_decode_utterance(self, audio_generator):
        """ Test decode_utterance with various inputs """

        # Test with empty audio data
        audio_data = b''
        output_str, info = self.recognizer.decode_utterance(audio_data)
        assert isinstance(output_str, str)
        assert output_str == ""
        assert_info_shape(info)

        # Test with short generated audio
        test_text = "hello world"
        audio_data = audio_generator(test_text)
        output_str, info = self.recognizer.decode_utterance(audio_data)
        assert isinstance(output_str, str)
        assert output_str == test_text
        assert_info_shape(info)

        # Test with longer text
        test_text = "this is a longer sentence to test the speech recognition capabilities"
        audio_data = audio_generator(test_text)
        output_str, info = self.recognizer.decode_utterance(audio_data)
        assert isinstance(output_str, str)
        assert output_str == test_text
        assert_info_shape(info)

        # Test with garbage audio: random but repeatable
        random.seed(42)
        audio_data = bytes(random.randint(0, 255) for _ in range(32768))
        output_str, info = self.recognizer.decode_utterance(audio_data)
        assert isinstance(output_str, str)
        assert output_str == ""
        assert_info_shape(info)
