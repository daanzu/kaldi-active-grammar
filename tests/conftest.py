
import os
from pathlib import Path

import piper
import pytest


@pytest.fixture
def change_to_test_dir(monkeypatch):
        monkeypatch.chdir(Path(__file__).parent)  # Where model is

def get_piper_model_path():
    """ Get Piper model path from environment or use default. """
    model_name = os.environ.get('PIPER_MODEL', 'en_US-ryan-low.onnx')
    model_path = Path(__file__).parent / model_name
    if not model_path.is_file():
        raise FileNotFoundError(f"Piper model file '{model_path}' not found.")
        # from piper.download_voices import download_voice
        # download_voice(model_name, model_path.parent)
    return model_path

@pytest.fixture(scope="session")
def piper_voice():
    """ Load Piper TTS voice model once per test session. """
    piper_model_path = get_piper_model_path()
    return piper.PiperVoice.load(piper_model_path)

@pytest.fixture
def audio_generator(piper_voice):
    """ Generate audio data from text using Piper TTS. """
    def _generate_audio(text, syn_config=None):
        if syn_config is None:
            syn_config = piper.SynthesisConfig(
                length_scale=1.5,  # Slow down
                noise_scale=0.0,  # No audio variation, for repeatable testing
                noise_w_scale=0.0,  # No speaking variation, for repeatable testing
            )
        audio_chunks = []
        for chunk in piper_voice.synthesize(text, syn_config=syn_config):
            audio_chunks.append(chunk.audio_int16_bytes)
        return b''.join(audio_chunks)
    return _generate_audio
