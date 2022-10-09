# A crude way of using OpenAI Whisper for dictation in KaldiAG.
# By Shervin Emami (www.shervinemami.com) 2022
# Based on "alternative_dictation.py" from KaldiAG v1.8, when KaldiAG had some basic support for GCloud dictation.
#
# (c) Copyright 2019 by David Zurow
# Licensed under the AGPL-3.0; see LICENSE.txt file.
#

from __future__ import print_function
import wave

try:
    import io
    from pydub import AudioSegment
    import speech_recognition as sr
    import whisper
    whisper_imported = True
except ImportError:
    whisper_imported = False

from . import _log

_log = _log.getChild('whisper_dictation')


def write_wav(filename, audio_data, sample_rate=16000):
    wf = wave.open(filename, 'wb')
    wf.setnchannels(1)
    wf.setsampwidth(2)
    wf.setframerate(sample_rate)
    wf.writeframes(audio_data)
    wf.close()

# Choose between Whisper models: "tiny.en", "base.en", "small.en", "medium.en" or "large.en".
# If you don't have a powerful GPU, stick to tiny or base.
audio_model = whisper.load_model("base.en")
input_wav = "/tmp/whisper.wav"

#load the speech recognizer and set the initial energy threshold and pause threshold
r = sr.Recognizer()
r.energy_threshold = 300
r.pause_threshold = 0.8
r.dynamic_energy_threshold = False

verbose = False

class Whisper(object):

    @staticmethod
    def transcribe_data_sync(speech_data, model='default', language_code='en-US'):

        if not whisper_imported:
            _log.error("Cannot find one of the Whisper packages!")
            return None

        transcript = "Unknown"
        result = audio_model.transcribe(input_wav, language='english')

        if not verbose:
            if result:
                transcript = result["text"]
            print("According to OpenAI Whisper, you said: " + transcript)
        else:
            print(result)

        print(u'Transcript: {}'.format(transcript))
        return transcript
