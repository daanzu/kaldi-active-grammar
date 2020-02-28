import sys, wave
from kaldi_active_grammar import PlainDictationRecognizer

recognizer = PlainDictationRecognizer()  # Or supply non-default model_dir, tmp_dir, or fst_file
filename = sys.argv[1] if len(sys.argv) > 1 else 'test.wav'
wave_file = wave.open(filename, 'rb')
data = wave_file.readframes(wave_file.getnframes())
output_str, likelihood = recognizer.decode_utterance(data)
print(repr(output_str), likelihood)  # -> 'alpha bravo charlie' 1.1923989057540894
