import wave

from google.cloud import speech
from google.cloud.speech import enums
from google.cloud.speech import types

def transcribe_data(speech_data):
    client = speech.SpeechClient()

    audio = types.RecognitionAudio(content=speech_data)
    config = types.RecognitionConfig(
        encoding=enums.RecognitionConfig.AudioEncoding.LINEAR16,
        sample_rate_hertz=16000,
        language_code='en-US')

    response = client.recognize(config, audio)
    # Each result is for a consecutive portion of the audio. Iterate through
    # them to get the transcripts for the entire audio file.
    for result in response.results:
        # The first alternative is the most likely one for this portion.
        # print(u'Transcript: {}'.format(result.alternatives[0].transcript))
        return result.alternatives[0].transcript

def write_wav(filename, audio_data, sample_rate=16000):
    wf = wave.open(filename, 'wb')
    wf.setnchannels(1)
    wf.setsampwidth(2)
    wf.setframerate(sample_rate)
    wf.writeframes(audio_data)
    wf.close()
