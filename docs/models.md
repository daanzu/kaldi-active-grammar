# Speech Recognition Models

## Comparison

* Metric: [Word Error Rate (WER)](https://en.wikipedia.org/wiki/Word_error_rate)
* Data sets:
    * LibriSpeech Test "Clean"
    * TestSet1: my test set combining multiple sources
    * SpeechComm: test set from [Google's Speech Commands Dataset](http://download.tensorflow.org/data/speech_commands_v0.02.tar.gz), consisting of short single-word commands

**Note**: The tests on commands are not necessarily fair, because they were performed using a full dictation grammar, rather than a reduced command-specific grammar. This is a worst case scenario for accuracy; in practice, speaking commands would perform much more accurately.

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

## Fine tuning for individual speakers

Fine tuning a generic model for an individual speaker can greatly increase accuracy, at the small cost of recording some training data from the speaker themself. This training data can be recorded specifically for training purposes, or it can be retained from normal use while using another model (or even another engine).

### David

| Model | David Commands (test set) | David Dictation (test set)
:---:|:---:|:---:
KaldiAG dgesr-f-1ep generic | 84.94 | 70.59
KaldiAG dgesr-f-1ep fine tuned on ~34hr of mixed commands + dictation | 7.11 | 14.46
Custom model trained only on ~34hr of mixed commands + dictation | 10.04 | 10.29

### Shervin

* Shervin Commands: ~1 hour, ~4000 utterances
* Shervin Dictation: ~30 minutes, ~500 utterances

| Model | Shervin Commands | Shervin Dictation
:---:|:---:|:---:
KaldiAG dgesr-f-1ep generic | 59.30 | 50.77
KaldiAG dgesr-f-1ep fine tuned on Shervin Commands + Dictation | 7.19 | 46.74

