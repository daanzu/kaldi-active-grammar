
from pathlib import Path


__all__ = [
    'LAF_MODEL_FILES', 'missing_laf_model_files',
    'expected_info_keys_and_types', 'assert_info_shape', 'play_audio_on_windows',
]

LAF_MODEL_FILES = (
    'HCLr.fst', 'Gr.fst', 'disambig_tid.int',
    'relabel_ilabels.int', 'words.relabeled.txt',
)


def missing_laf_model_files(model_dir=None):
    """Return the LAF model files missing from the test model directory."""
    model_dir = Path(model_dir) if model_dir else (Path(__file__).parent / 'kaldi_model')
    return [name for name in LAF_MODEL_FILES if not (model_dir / name).is_file()]


expected_info_keys_and_types = {
    'likelihood': float,
    'am_score': float,
    'lm_score': float,
    'confidence': float,
    'expected_error_rate': float,
}

def assert_info_shape(info):
    assert isinstance(info, dict)
    for key, expected_type in expected_info_keys_and_types.items():
        assert key in info, f"Missing key: {key}"
        assert isinstance(info[key], expected_type), f"Incorrect type for {key}: expected {expected_type}, got {type(info[key])}"

def play_audio_on_windows(audio_bytes: bytes, sample_rate: int = 16000):
    """ Play raw PCM audio bytes on Windows using winsound. For interactive debugging only. """
    import io
    import wave
    import winsound
    with io.BytesIO() as buf:
        with wave.open(buf, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(audio_bytes)
        wav_data = buf.getvalue()
    winsound.PlaySound(wav_data, winsound.SND_MEMORY)
