
from pathlib import Path

import pytest

from kaldi_active_grammar import PlainDictationRecognizer


class TestPlainDictation:

    expected_info_keys = ('likelihood', 'am_score', 'lm_score', 'confidence', 'expected_error_rate')

    @pytest.fixture(autouse=True)
    def setup(self, monkeypatch):
        monkeypatch.chdir(Path(__file__).parent)  # Where model is
        self.recognizer = PlainDictationRecognizer()

    def test_plain_dictation_comprehensive(self, audio_generator):
        """ Test PlainDictationRecognizer initialization and decode_utterance with various inputs """
        # Test initialization
        assert isinstance(self.recognizer, PlainDictationRecognizer)

        # Test with empty audio data
        empty_data = b''
        output_str, info = self.recognizer.decode_utterance(empty_data)
        assert isinstance(output_str, str)
        assert len(output_str) == 0  # Expecting empty output for empty input
        assert isinstance(info, dict)
        assert all(key in info and isinstance(info[key], float) for key in self.expected_info_keys)

        # Test with short generated audio
        test_text = "hello world"
        audio_data = audio_generator(test_text)
        output_str, info = self.recognizer.decode_utterance(audio_data)
        assert isinstance(output_str, str)
        assert len(output_str) > 0
        assert output_str == test_text
        assert isinstance(info, dict)
        assert all(key in info and isinstance(info[key], float) for key in self.expected_info_keys)

        # Test with longer text
        test_text = "this is a longer sentence to test the speech recognition capabilities"
        audio_data = audio_generator(test_text)
        output_str, info = self.recognizer.decode_utterance(audio_data)
        assert isinstance(output_str, str)
        assert len(output_str) > 0
        assert output_str == test_text
        assert isinstance(info, dict)
        assert all(key in info and isinstance(info[key], float) for key in self.expected_info_keys)
