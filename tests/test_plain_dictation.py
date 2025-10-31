
import math
import random

import pytest

from kaldi_active_grammar import PlainDictationRecognizer
from tests.helpers import *


@pytest.fixture
def recognizer(change_to_test_dir):
    return PlainDictationRecognizer()


def test_initialization(recognizer):
    assert isinstance(recognizer, PlainDictationRecognizer)
    assert hasattr(recognizer, 'decoder')
    assert hasattr(recognizer, '_compiler')


@pytest.mark.parametrize("test_text", [
    "hello world",
    "this is a longer sentence to test the speech recognition capabilities",
    "testing active grammar framework",
    "hello there",
    "one two three four five",
    "testing numbers and words",
])
def test_basic_dictation(recognizer, audio_generator, test_text):
    audio_data = audio_generator(test_text)
    output_str, info = recognizer.decode_utterance(audio_data)
    assert isinstance(output_str, str)
    assert output_str == test_text
    assert_info_shape(info)


def test_empty_audio(recognizer):
    output_str, info = recognizer.decode_utterance(b'')
    assert isinstance(output_str, str)
    assert output_str == ""
    assert_info_shape(info)


def test_garbage_audio(recognizer):
    random.seed(42)
    audio_data = bytes(random.randint(0, 255) for _ in range(32768))
    output_str, info = recognizer.decode_utterance(audio_data)
    assert isinstance(output_str, str)
    assert output_str == ""
    assert_info_shape(info)


def test_multiple_utterances(recognizer, audio_generator):
    test_utterances = [
        "first utterance",
        "second utterance here",
        "and a third one",
    ]
    for test_text in test_utterances:
        audio_data = audio_generator(test_text)
        output_str, info = recognizer.decode_utterance(audio_data)
        assert isinstance(output_str, str)
        assert output_str == test_text
        assert_info_shape(info)


class TestPlainDictationWithFST:
    """Test PlainDictationRecognizer using HCLG.fst file"""

    @pytest.fixture(autouse=True)
    def setup(self, change_to_test_dir):
        try:
            self.recognizer = PlainDictationRecognizer(fst_file='HCLG.fst')
            self.has_hclg = True
        except Exception:
            self.has_hclg = False
            pytest.skip("HCLG.fst not available for testing")

    def test_initialization(self):
        if not self.has_hclg:
            pytest.skip("HCLG.fst not available")
        assert isinstance(self.recognizer, PlainDictationRecognizer)
        assert hasattr(self.recognizer, 'decoder')
        assert hasattr(self.recognizer, '_model')

    def test_basic_dictation(self, audio_generator):
        if not self.has_hclg:
            pytest.skip("HCLG.fst not available")
        test_text = "testing plain decoder"
        audio_data = audio_generator(test_text)
        output_str, info = self.recognizer.decode_utterance(audio_data)
        assert isinstance(output_str, str)
        assert_info_shape(info)


@pytest.mark.parametrize("chunk_size", [512, 1024, 2048, 4096, 8192, 16384])
@pytest.mark.parametrize("test_text", [
    "testing small chunk size",
    "medium chunk size testing",
    "large chunk size for testing",
])
def test_chunked_decode(recognizer, audio_generator, chunk_size, test_text):
    audio_data = audio_generator(test_text)
    output_str, info = recognizer.decode_utterance(audio_data, chunk_size=chunk_size)
    assert isinstance(output_str, str)
    assert output_str == test_text
    assert_info_shape(info)


def test_custom_tmp_dir(change_to_test_dir, audio_generator, tmp_path):
    recognizer = PlainDictationRecognizer(tmp_dir=str(tmp_path))
    test_text = "custom temporary directory"
    audio_data = audio_generator(test_text)
    output_str, info = recognizer.decode_utterance(audio_data)
    assert isinstance(output_str, str)
    assert output_str == test_text
    assert_info_shape(info)


def test_custom_config(change_to_test_dir, audio_generator):
    config = {
        'beam': 13.0,
        'max_active': 7000,
    }
    recognizer = PlainDictationRecognizer(config=config)
    test_text = "custom configuration test"
    audio_data = audio_generator(test_text)
    output_str, info = recognizer.decode_utterance(audio_data)
    assert isinstance(output_str, str)
    assert output_str == test_text
    assert_info_shape(info)


def test_very_short_audio(recognizer, audio_generator):
    test_text = "hi"
    audio_data = audio_generator(test_text)
    output_str, info = recognizer.decode_utterance(audio_data)
    assert isinstance(output_str, str)
    assert_info_shape(info)


def test_very_long_audio(recognizer, audio_generator):
    test_text = " ".join([
        "this is a very long sentence that goes on and on",
        "with many words to test the handling of extended audio",
        "and ensure that the decoder can process lengthy utterances",
        "without any issues or errors occurring during processing",
    ])
    audio_data = audio_generator(test_text)
    output_str, info = recognizer.decode_utterance(audio_data)
    assert isinstance(output_str, str)
    assert_info_shape(info)


def test_repeated_words(recognizer, audio_generator):
    test_text = "repeat repeat repeat the words"
    audio_data = audio_generator(test_text)
    output_str, info = recognizer.decode_utterance(audio_data)
    assert isinstance(output_str, str)
    assert_info_shape(info)


def test_sequential_empty_audio(recognizer):
    for _ in range(3):
        output_str, info = recognizer.decode_utterance(b'')
        assert isinstance(output_str, str)
        assert output_str == ""
        assert_info_shape(info)


def test_alternating_empty_and_valid(recognizer, audio_generator):
    test_text = "valid audio"

    output_str, info = recognizer.decode_utterance(b'')
    assert output_str == ""
    assert_info_shape(info)

    audio_data = audio_generator(test_text)
    output_str, info = recognizer.decode_utterance(audio_data)
    assert output_str == test_text
    assert_info_shape(info)

    output_str, info = recognizer.decode_utterance(b'')
    assert output_str == ""
    assert_info_shape(info)


def test_info_structure(recognizer, audio_generator):
    test_text = "check info dictionary"
    audio_data = audio_generator(test_text)
    output_str, info = recognizer.decode_utterance(audio_data)

    assert_info_shape(info)

    assert 0.0 <= info['confidence'] <= 1.0 or math.isnan(info['confidence'])
    assert 0.0 <= info['expected_error_rate'] <= 1.0 or math.isnan(info['expected_error_rate'])


def test_info_consistency(change_to_test_dir, audio_generator):
    test_text = "consistent info values"
    audio_data = audio_generator(test_text)

    recognizer1 = PlainDictationRecognizer()
    output_str1, info1 = recognizer1.decode_utterance(audio_data)

    recognizer2 = PlainDictationRecognizer()
    output_str2, info2 = recognizer2.decode_utterance(audio_data)

    assert output_str1 == output_str2

    assert_info_shape(info1)
    assert_info_shape(info2)
    threshold_pct = 0.01
    assert abs(info1['likelihood'] - info2['likelihood']) / abs(info1['likelihood']) < threshold_pct
    assert abs(info1['am_score'] - info2['am_score']) / abs(info1['am_score']) < threshold_pct
    assert abs(info1['lm_score'] - info2['lm_score']) / abs(info1['lm_score']) < threshold_pct
