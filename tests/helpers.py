
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

