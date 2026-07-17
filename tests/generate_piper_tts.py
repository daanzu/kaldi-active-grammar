#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "piper-tts",
#     "kaldi-active-grammar",
#     "fire",
# ]
# ///

import os

import piper

piper_model_path = os.path.join(os.path.dirname(__file__), 'en_US-ryan-low.onnx')
voice = piper.PiperVoice.load(piper_model_path)

# with wave.open("test.wav", "wb") as wav_file:
#     voice.synthesize_wav("Welcome to the world of speech synthesis!", wav_file)

syn_config = piper.SynthesisConfig(
    # volume=0.5,  # half as loud
    # length_scale=2.0,  # twice as slow
    # noise_scale=1.0,  # more audio variation
    # noise_w_scale=1.0,  # more speaking variation
    length_scale=1.5,
    noise_scale=0.0,
    noise_w_scale=0.0,
    # normalize_audio=False, # use raw audio from voice
)

# voice.synthesize_wav(..., syn_config=syn_config)

text = "Welcome to the world of speech synthesis!"
text = "it depends on the context"
text = "up down left right"

for chunk in voice.synthesize(text, syn_config=syn_config):
    print(chunk.sample_rate, chunk.sample_width, chunk.sample_channels)
    print("audio", len(chunk.audio_int16_bytes))
    audio_data = chunk.audio_int16_bytes

    if True:
        from io import BytesIO
        import wave
        import winsound
        audio_buffer = BytesIO()
        with wave.open(audio_buffer, 'wb') as wav_file:
            wav_file.setnchannels(chunk.sample_channels)
            wav_file.setsampwidth(chunk.sample_width)
            wav_file.setframerate(chunk.sample_rate)
            wav_file.writeframes(chunk.audio_int16_bytes)
        audio_buffer.seek(0)
        winsound.PlaySound(audio_buffer.getvalue(), winsound.SND_MEMORY)

if True:
    import kaldi_active_grammar as kag
    recognizer = kag.PlainDictationRecognizer()
    output_str, info = recognizer.decode_utterance(audio_data)
    print(repr(output_str), info)
