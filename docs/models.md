# Speech Recognition Models

[![Donate](https://img.shields.io/badge/donate-GitHub-pink.svg)](https://github.com/sponsors/daanzu)
[![Donate](https://img.shields.io/badge/donate-Patreon-orange.svg)](https://www.patreon.com/daanzu)
[![Donate](https://img.shields.io/badge/donate-PayPal-green.svg)](https://paypal.me/daanzu)
[![Donate](https://img.shields.io/badge/preferred-GitHub-black.svg)](https://github.com/sponsors/daanzu)
[**GitHub** is matching (only) my **GitHub Sponsors** donations.]

## Available Models

* For **kaldi-active-grammar**
    * [kaldi_model_daanzu_20200328_1ep-mediumlm](https://github.com/daanzu/kaldi-active-grammar/releases/download/v1.4.0/kaldi_model_daanzu_20200328_1ep-mediumlm.zip)
* For **generic kaldi**, or [**vosk**](https://github.com/alphacep/vosk-api)
    * [vosk-model-en-us-daanzu-20200328](https://github.com/daanzu/kaldi-active-grammar/releases/download/v1.4.0/vosk-model-en-us-daanzu-20200328.zip)
    * [vosk-model-en-us-daanzu-20200328-lgraph](https://github.com/daanzu/kaldi-active-grammar/releases/download/v1.4.0/vosk-model-en-us-daanzu-20200328-lgraph.zip)

## Basic info for KaldiAG models

* **Latency**: I have yet to do formal latency testing, but for command grammars, the latency between the end of the utterance (as determined by the Voice Activity Detector) and receiving the final recognition results is in the range of 10-20ms.

## General Comparison

* Metric: [Word Error Rate (WER)](https://en.wikipedia.org/wiki/Word_error_rate)
* Data sets:
    * [LibriSpeech](http://www.openslr.org/12) Test Clean
    * [Mozilla Common Voice](https://voice.mozilla.org/en/datasets) English Test
    * [TED-LIUM Release 3](https://www.openslr.org/51/) Legacy Test
    * TestSet1: my test set combining multiple sources
    * Speech Comm: test set from [Google's Speech Commands Dataset](http://download.tensorflow.org/data/speech_commands_v0.02.tar.gz), consisting of short single-word commands

**Note**: The tests on commands are not necessarily fair, because they were performed using a full dictation grammar, rather than a reduced command-specific grammar. This is a worst case scenario for accuracy; in practice, speaking commands would perform much more accurately.

|                       Engine                       | LS Test Clean | CV4 Test  | Ted3 Test | TestSet1  | Speech Comm |
|:--------------------------------------------------:|:-------------:|:---------:|:---------:|:---------:|:-----------:|
|        KaldiAG dgesr2-f-1ep LibriSpeech LM         |     4.77      | **30.91** | **12.98** | **10.16** |  **11.67**  |
|        vosk-model-en-us-aspire-0.2 [carpa]         |     17.90     |   69.76   |           |           |    55.90    |
|             vosk-model-small-en-us-0.3             |     19.30     |           |           |           |    45.57    |
|                Zamia LibriSpeech LM                |   **4.56**    |   34.28   |           |   10.34   |    30.16    |
|                wav2letter-talonweb                 |     10.03     |           |           |   16.27   |    16.21    |
|             Amazon Transcribe **\*\***             |     8.21%     |           |           |           |             |
|         CMU PocketSphinx (0.1.15) **\*\***         |    31.82%     |           |           |           |             |
|           Google Speech-to-Text **\*\***           |    12.23%     |           |           |           |             |
|        Mozilla DeepSpeech (0.6.1) **\*\***         |     7.55%     |           |           |           |             |
|        Picovoice Cheetah (v1.2.0) **\*\***         |    10.49%     |           |           |           |             |
| Picovoice Cheetah LibriSpeech LM (v1.2.0) **\*\*** |     8.25%     |           |           |           |             |
|        Picovoice Leopard (v1.0.0) **\*\***         |     8.34%     |           |           |           |             |
| Picovoice Leopard LibriSpeech LM (v1.0.0) **\*\*** |     6.58%     |           |           |           |             |

<!-- |         KaldiAG dgesr-f-1ep LibriSpeech LM         |     5.07      |          |               | **10.23** | **13.75**  | -->

**\*\***: not tested by me; from [Picovoice speech-to-text-benchmark](https://github.com/Picovoice/speech-to-text-benchmark#results)

## Fine tuning for individual speakers

Fine tuning a generic model for an individual speaker can greatly increase accuracy, at the small cost of recording some training data from the speaker themself. This training data can be recorded specifically for training purposes, or it can be retained from normal use while using another model (or even another engine).

### David

* Very difficult speech.

|                                 Model                                 | David Commands (test set) | David Dictation (test set) |
|:---------------------------------------------------------------------:|:-------------------------:|:--------------------------:|
|                      KaldiAG dgesr-f-1ep generic                      |           84.94           |           70.59            |
| KaldiAG dgesr-f-1ep fine tuned on ~34hr of mixed commands + dictation |           7.11            |           14.46            |
|   Custom model trained only on ~34hr of mixed commands + dictation    |           10.04           |           10.29            |

### Shervin

* Accented speech.
* Shervin Commands: ~1 hour, ~4000 utterances.
* Shervin Dictation: ~20 minutes, ~250 utterances.

|                              Model                              | Shervin Commands | Shervin Dictation |
|:---------------------------------------------------------------:|:----------------:|:-----------------:|
|                  KaldiAG dgesr2-f-1ep generic                   |      46.98       |       9.21        |
| KaldiAG dgesr2-f-1ep fine tuned on Shervin Commands + Dictation |       9.76       |       2.40        |





