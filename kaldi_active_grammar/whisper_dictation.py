# A crude way of using OpenAI Whisper for dictation in KaldiAG.
# By Shervin Emami (www.shervinemami.com) 2022
# Based on "alternative_dictation.py" from KaldiAG v1.8, when KaldiAG had some basic support for GCloud dictation.
#
# KaldiAG is (c) Copyright 2019 by David Zurow
# Licensed under the AGPL-3.0; see LICENSE.txt file.
#
from __future__ import print_function


# Allow to lazily load the model upon first actual use, so that startup is fast for times when we just want command-mode, not whisper dictation.
# TODO: Allow passing the model name from the user
lazily_load_model = True

# Choose between Whisper models: "tiny.en", "base.en", "small.en", "medium.en" or "large".
# If you have a powerful GPU, try "medium.en".
# If you don't have a GPU, stick to "tiny.en" or "base.en".
# TODO: Allow passing the model name from the user
#model_filename = "tiny.en"
model_filename = "medium.en"

verbose = False


import io
import time
try:
    import whisper
    whisper_imported = True
except ImportError:
    whisper_imported = False

from . import _log
_log = _log.getChild('whisper_dictation')


def load_whisper_model(filename):
    print("Loading whisper pytorch model '" + filename + "' during startup. Takes a long time. Also expect the first transciption to be slower than usual, since the GPU must load drivers and ramp up its clocks.")
    model = whisper.load_model(filename)
    if model:
        print("Finished loading whisper model.")
    return model

if lazily_load_model:
    whisper_model = None
else:
    whisper_model = load_whisper_model(model_filename)


# FIXME: Hard-coded file that's used for transferring audio from Kaldi/Dragonfly to Whisper, and probably isn't portable to Windows!
audio_filename = "/tmp/whisper.wav"

# Whisper allows passing "prompt" that is intended to be the previous sentence or some similar related text, to give a hint
# about what it should expect. This includes formatting, so for example giving a hint of "40's" can push whisper closer to
# decoding the phrase "forties" as "40's" instead of "40s".
# Since I want a lot of commas but not fullstops or capitalising of phrases, I'm using a hint_prompt this way.
# TODO: Allow passing whisper args from the user script.
hint_prompt="oh OK yeah sure, in my 40's I mostly benchmarked a profile of ARM CPU core optimisation"

# Decode the audio.
# "decode" will use GreedyDecoder (fast) if beam_size=None, or it will use BeamSearch (slower but more reliable) if beam_size=5 or similar.
# Set fp16=True for RTX GPUs, or False for GTX GPUs. Because GTX & older GPUs are extremely fast at FP32 but terrible at FP16,
# whereas new GPUs such as RTX GPUs are extremely fast at both FP32 and FP16, and in fact slightly faster at FP16.
# Set beam_size=5 if you can handle the slower speed, or use beam_size of 0-3 if you want faster results, but with more chance that whisper
# will get stuck in a repetetive mental loop for a while.
# TODO: Allow passing whisper args from the user script.
options = whisper.DecodingOptions(language="en", fp16=False, prompt=hint_prompt, best_of=None, beam_size=3, temperature=0.0, patience=1.3)


def write_wav(filename, audio_data, sample_rate=16000):
    wf = wave.open(filename, 'wb')
    wf.setnchannels(1)
    wf.setsampwidth(2)
    wf.setframerate(sample_rate)
    wf.writeframes(audio_data)
    wf.close()


def testCUDA():
    print("Test CUDA")

    import torch

    # Making the code device-agnostic
    device_name = 'cuda' if torch.cuda.is_available() else 'cpu'
    if device_name == 'cuda':
        print(f"CUDA version: {torch.version.cuda}")
        print(f"Name of current CUDA device: {torch.cuda.get_device_name(torch.cuda.current_device())}")

    # Creating a test tensor
    x = torch.randint(1, 100, (100, 1000))
    # Checking the device name:
    # Should return 'cpu' by default
    print("Default pytorch device (should be 'CPU'): ", x.device)
    # Transferring tensor to GPU
    x = x.to(torch.device(device_name))
    # Checking the device name:
    # Should return 'cuda:0'
    print("CUDA pytorch device (should be 'cuda:0'): ", x.device)
    # Applying same GPU-accelerated tensor operation
    res_gpu = x ** 2
    res_cpu = res_gpu.cpu()
    print("result: ", res_cpu)



class Whisper(object):

    @staticmethod
    def transcribe_data_sync(speech_data, model='default', language_code='en-US'):

        # For debugging latency of GPU-accelerated PyTorch:
        #testCUDA()
        #return "words"

        if not whisper_imported:
            _log.error("Cannot find one of the Whisper packages!")
            return None

        # Allow to lazily load the model upon first actual use, so that startup is fast for times when we just want command-mode, not whisper dictation.
        global whisper_model
        if not whisper_model:
            whisper_model = load_whisper_model(model_filename)

        start_inference = time.perf_counter()

        transcript = "Unknown"
        # Whisper is much faster when using 'model.decode' instead of 'model.transcribe'. See "https://github.com/openai/whisper/discussions/391"
        #result = whisper_model.transcribe(audio_filename, language='english')
        audio = whisper.load_audio(audio_filename)
        audio = whisper.pad_or_trim(audio)

        # Make log-mel spectrogram and move it to the same device as the model (GPU)
        mel = whisper.log_mel_spectrogram(audio).to(whisper_model.device)

        # Decode the audio.
        result = whisper.decode(whisper_model, mel, options)
        if result:
            transcript = result.text

        elapsed_inference = time.perf_counter() - start_inference

        print(u"According to OpenAI Whisper after {elapsed_inference:.1f}s, you said: {}".format(transcript))
        if verbose:
            print(result)
        return transcript
