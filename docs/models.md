# Speech Recognition Models

## Comparison

* Metric: [Word Error Rate (WER)](https://en.wikipedia.org/wiki/Word_error_rate)
* Data sets:
    * LibriSpeech Test "Clean"
    * TestSet1: my test set combining multiple sources
    * SpeechComm: test set from [Google's Speech Commands Dataset](http://download.tensorflow.org/data/speech_commands_v0.02.tar.gz), consisting of short single-word commands

| Engine | LS-Test-Clean | TestSet1 | SpeechComm
:---:|:---:|:---:|:---:
KaldiAG dgesr-f-1ep LibriSpeech LM | 5.07 | **10.23** | **13.75**
Zamia LibriSpeech LM | **4.56** | 10.34 | 30.16
wav2letter-talonweb | 10.03 | 16.27 | 16.21
Amazon Transcribe **\*\*** | 8.21%
CMU PocketSphinx (0.1.15) **\*\*** | 31.82%
Google Speech-to-Text **\*\*** | 12.23%
Mozilla DeepSpeech (0.6.1) **\*\*** | 7.55%
Picovoice Cheetah (v1.2.0) **\*\*** | 10.49%
Picovoice Cheetah LibriSpeech LM (v1.2.0) **\*\*** | 8.25%
Picovoice Leopard (v1.0.0) **\*\*** | 8.34%
Picovoice Leopard LibriSpeech LM (v1.0.0) **\*\*** | 6.58%

**\*\***: not tested by me; from [Picovoice speech-to-text-benchmark](https://github.com/Picovoice/speech-to-text-benchmark#results)
