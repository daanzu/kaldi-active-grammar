#
# This file is part of kaldi-active-grammar.
# (c) Copyright 2019 by David Zurow
# Licensed under the AGPL-3.0, with exceptions; see LICENSE.txt file.
#

import wave

try:
    # google-cloud-speech==0.36.3
    from google.cloud import speech
    from google.cloud.speech import enums
    from google.cloud.speech import types
    gcloud_imported = True
except ImportError:
    gcloud_imported = False

from . import _log

_log = _log.getChild('cloud')

class GCloud(object):

    @staticmethod
    def transcribe_data_sync(speech_data, model='default'):
        # model in ['video', 'phone_call', 'command_and_search', 'default']

        if not gcloud_imported:
            _log.error("cloud_dictation failed because cannot find google.cloud package!")
            return None
        client = speech.SpeechClient()

        audio = types.RecognitionAudio(content=speech_data)
        config = types.RecognitionConfig(
            encoding=enums.RecognitionConfig.AudioEncoding.LINEAR16,
            sample_rate_hertz=16000,
            language_code='en-US',
            model=model,
        )

        response = client.recognize(config, audio)
        # Each result is for a consecutive portion of the audio. Iterate through
        # them to get the transcripts for the entire audio file.
        assert len(response.results) <= 1
        for result in response.results:
            # The first alternative is the most likely one for this portion.
            # print(u'Transcript: {}'.format(result.alternatives[0].transcript))
            return result.alternatives[0].transcript

    @staticmethod
    def transcribe_data_streaming(speech_data, model=None):
        # model in ['video', 'phone_call', 'command_and_search', 'default']

        if not gcloud_imported:
            _log.error("cloud_dictation failed because cannot find google.cloud package!")
            return None
        client = speech.SpeechClient()

        # In practice, stream should be a generator yielding chunks of audio data.
        stream = [speech_data]
        requests = (types.StreamingRecognizeRequest(audio_content=chunk) for chunk in stream)

        config = types.RecognitionConfig(
            encoding=enums.RecognitionConfig.AudioEncoding.LINEAR16,
            sample_rate_hertz=16000,
            language_code='en-US',
            # model=model,
        )
        streaming_config = types.StreamingRecognitionConfig(
            config=config,
            single_utterance=True,
            interim_results=False,
        )

        # streaming_recognize returns a generator.
        responses = client.streaming_recognize(streaming_config, requests)

        if True:
            responses = list(responses)
            if not responses:
                return
            assert len(responses) == 1
            response = responses[0]
            assert len(response.results) == 1
            result = response.results[0]
            return result.alternatives[0].transcript

        else:
            for response in responses:
                # Once the transcription has settled, the first result will contain the
                # is_final result. The other results will be for subsequent portions of
                # the audio.
                for result in response.results:
                    print('Finished: {}'.format(result.is_final))
                    print('Stability: {}'.format(result.stability))
                    alternatives = result.alternatives
                    # The alternatives are ordered from most likely to least.
                    for alternative in alternatives:
                        print('Confidence: {}'.format(alternative.confidence))
                        print(u'Transcript: {}'.format(alternative.transcript))

def write_wav(filename, audio_data, sample_rate=16000):
    wf = wave.open(filename, 'wb')
    wf.setnchannels(1)
    wf.setsampwidth(2)
    wf.setframerate(sample_rate)
    wf.writeframes(audio_data)
    wf.close()
