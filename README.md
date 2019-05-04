# Kaldi Active Grammar

> **Kaldi speech recognition with grammars that can be set active/inactive dynamically at decode-time**

[![PyPI - Status](https://img.shields.io/pypi/status/kaldi-active-grammar.svg)](https://pypi.python.org/pypi/kaldi-active-grammar/)
[![PyPI - Version](https://img.shields.io/pypi/v/kaldi-active-grammar.svg)](https://pypi.python.org/pypi/kaldi-active-grammar/)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/kaldi-active-grammar.svg)](https://pypi.python.org/pypi/kaldi-active-grammar/)
[![PyPI - Wheel](https://img.shields.io/pypi/wheel/kaldi-active-grammar.svg)](https://pypi.python.org/pypi/kaldi-active-grammar/)

> Python package developed to enable context-based command & control of computer applications, as in the [Dragonfly](https://github.com/dictation-toolbox/dragonfly) speech recognition framework, using the [Kaldi](https://github.com/kaldi-asr/kaldi) automatic speech recognition engine.

> **_ALPHA RELEASE_**

Normally, Kaldi decoding graphs are monolithic, require expensive up-front off-line compilation, and are static during decoding. Kaldi's new grammar framework allows multiple separate grammars with nonterminals, to be compiled separately and stitched together dynamically at decode-time, but all the grammars are always active and capable of being recognized during any utterance.

This project extends that to allow each grammar/rule to be independently marked as active/inactive dynamically on a per-utterance basis (declared at the beginning of each utterance). Dragonfly is then capable of activating only the appropriate grammars for the current environment, resulting in increased accuracy due to fewer possible recognitions. Furthermore, the large dictation grammar can be shared between all the command grammars, which can be compiled quickly without needing to include large-vocabulary dictation directly.

The Python package includes all necessary binaries for decoding. A compatible general English Kaldi nnet3 chain model is available. A compatible backend for Dragonfly is under development.

## Setup

Requirements:
* Python 2.7, 3.?+ (only 2.7 tested currently); 64-bit required
* OS: Windows only currently; Linux & MacOS planned
* Only supports Kaldi left-biphone models, specifically nnet3 chain models

Install Python package, which includes necessary Kaldi binaries:

```
pip install kaldi-active-grammar
```

Download generic English Kaldi nnet3 chain model.

Or use your own model. Standard Kaldi models must be converted to be usable. Conversion can be performed automatically, but this hasn't been fully implemented yet.

## Contributing

Please feel free to submit issues, suggestions, and feature requests. Pull requests considered, but project structure is in flux.

## License

This project is licensed under the GNU Affero General Public License v3 (AGPL-3.0), with the exception of the associated binaries, whose source is currently unreleased and which are only to be used by this project. See the LICENSE.txt file for details.

## Acknowledgments

* Based on and including code from [Kaldi ASR](https://github.com/kaldi-asr/kaldi), under the Apache-2.0 license.
* Code from [OpenFST](http://www.openfst.org/), under the Apache-2.0 license.
* Modified generic English Kaldi nnet3 chain model from [Zamia Speech](https://github.com/gooofy/zamia-speech), under the LGPL-3.0 license.

## Author

* David Zurow [(daanzu)](https://github.com/daanzu)
