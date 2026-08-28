# Examples

These examples assume the default Kaldi model and temporary-directory locations. Edit the model and file paths in an example when using a custom setup.

## Runnable examples

- [`full_example.py`](full_example.py) — Build a grammar rule and recognize it from live microphone audio.
- [`mimic.py`](mimic.py) — Match text against a loaded grammar without decoding audio.
- [`mix_dictation.py`](mix_dictation.py) — Build a grammar that combines strict command words with free dictation.
- [`plain_dictation.py`](plain_dictation.py) — Decode a WAV file with the plain dictation recognizer.

## Supporting utilities

- [`audio.py`](audio.py) — Microphone capture and voice-activity-detection support used by the live-audio examples.
- [`util.py`](util.py) — Shared compiler initialization and recognition-loop helpers.

Install the additional audio dependencies listed in [`requirements_audio.txt`](requirements_audio.txt) before running the microphone examples.
