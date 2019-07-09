# Kaldi Active Grammar

> **Python Kaldi speech recognition with grammars that can be set active/inactive dynamically at decode-time**

[![PyPI - Status](https://img.shields.io/pypi/status/kaldi-active-grammar.svg)](https://pypi.python.org/pypi/kaldi-active-grammar/)
[![PyPI - Version](https://img.shields.io/pypi/v/kaldi-active-grammar.svg)](https://pypi.python.org/pypi/kaldi-active-grammar/)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/kaldi-active-grammar.svg)](https://pypi.python.org/pypi/kaldi-active-grammar/)
[![PyPI - Wheel](https://img.shields.io/pypi/wheel/kaldi-active-grammar.svg)](https://pypi.python.org/pypi/kaldi-active-grammar/)
[![PyPI - Downloads](https://img.shields.io/pypi/dw/kaldi-active-grammar.svg)](https://pypi.python.org/pypi/kaldi-active-grammar/)
[![Donate](https://img.shields.io/badge/donate-PayPal-green.svg)](https://paypal.me/daanzu)
[![Donate](https://img.shields.io/badge/donate-Patreon-orange.svg)](https://www.patreon.com/daanzu)

> Python package developed to enable context-based command & control of computer applications, as in the [Dragonfly](https://github.com/dictation-toolbox/dragonfly) speech recognition framework, using the [Kaldi](https://github.com/kaldi-asr/kaldi) automatic speech recognition engine.

> **_BETA RELEASE_**

Normally, Kaldi decoding graphs are **monolithic**, require **expensive up-front off-line** compilation, and are **static during decoding**. Kaldi's new grammar framework allows **multiple independent** grammars with nonterminals, to be compiled separately and **stitched together dynamically** at decode-time, but all the grammars are **always active** and capable of being recognized.

This project extends that to allow each grammar/rule to be **independently marked** as active/inactive **dynamically** on a **per-utterance** basis (set at the beginning of each utterance). Dragonfly is then capable of activating **only the appropriate grammars for the current environment**, resulting in increased accuracy due to fewer possible recognitions. Furthermore, the dictation grammar can be **shared** between all the command grammars, which can be **compiled quickly** without needing to include large-vocabulary dictation directly.

* The Python package **includes all necessary binaries** for decoding on **Linux or Windows**.
* A compatible **general English Kaldi nnet3 chain model** is available, under [releases](https://github.com/daanzu/kaldi-active-grammar/releases), trained on ~1200 hours of open audio.
* A compatible [**backend for Dragonfly**](https://github.com/daanzu/dragonfly/tree/kaldi/dragonfly/engines/backend_kaldi) is under development, currently in the kaldi branch of my fork.
    * A beta version has been merged as of Dragonfly **v0.15.0**! See its [documentation](https://dragonfly2.readthedocs.io/en/latest/kaldi_engine.html), and try out a [demo](https://github.com/daanzu/dragonfly/blob/kaldi/dragonfly/examples/kaldi_demo.py).

**Donations are appreciated to encourage development (see badges above).**

## Setup

Requirements:
* Python 2.7 (3.x support planned); *64-bit required!*
    * Microphone support provided by [pyaudio](https://pypi.org/project/PyAudio/) package
* OS: *Linux or Windows*; macOS planned if there is interest
* Only supports Kaldi left-biphone models, specifically *nnet3 chain* models, with specific modifications
* ~1GB+ disk space for model plus temporary storage and cache, depending on your grammar complexity
* ~500MB+ RAM for model and grammars, depending on your model and grammar complexity

Install Python package, which includes necessary Kaldi binaries:

```
pip install kaldi-active-grammar
```

Download compatible generic English Kaldi nnet3 chain model from [project releases](https://github.com/daanzu/kaldi-active-grammar/releases). Unzip the model and pass the directory path to kaldi-active-grammar constructor.

Or use your own model. Standard Kaldi models must be converted to be usable. Conversion can be performed automatically, but this hasn't been fully implemented yet.

### Troubleshooting

* Errors installing
    * Make sure you're using a 64-bit Python.
    * Update your `pip` by executing `pip install --upgrade pip`.

## Documentation

Documentation is sorely lacking currently. To see example usage, examine the [**backend for Dragonfly**](https://github.com/daanzu/dragonfly/tree/kaldi/dragonfly/engines/backend_kaldi).

## Contributing

Issues, suggestions, and feature requests are welcome & encouraged. Pull requests are considered, but project structure is in flux.

Donations are appreciated to encourage development.

[![Donate](https://img.shields.io/badge/donate-PayPal-green.svg)](https://paypal.me/daanzu)
[![Donate](https://img.shields.io/badge/donate-Patreon-orange.svg)](https://www.patreon.com/daanzu)

## Author

* David Zurow ([@daanzu](https://github.com/daanzu))

## License

This project is licensed under the GNU Affero General Public License v3 (AGPL-3.0), with the exception of the associated binaries, whose source is currently unreleased and which are only to be used by this project. See the LICENSE.txt file for details.

If this license is problematic for you, please contact me.

## Acknowledgments

* Based on and including code from [Kaldi ASR](https://github.com/kaldi-asr/kaldi), under the Apache-2.0 license.
* Code from [OpenFST](http://www.openfst.org/) and [OpenFST port for Windows](https://github.com/kkm000/openfst), under the Apache-2.0 license.
* [Intel Math Kernel Library](https://software.intel.com/en-us/mkl), copyright (c) 2018 Intel Corporation, under the [Intel Simplified Software License](https://software.intel.com/en-us/license/intel-simplified-software-license).
* Modified generic English Kaldi nnet3 chain model from [Zamia Speech](https://github.com/gooofy/zamia-speech), under the LGPL-3.0 license.
