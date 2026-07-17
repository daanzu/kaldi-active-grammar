v0.5.0: User Lexicon! Compilation Optimizations! Better Model!

### Notes

* **User Lexicon**: you can add new words/pronunciations to the model's lexicon to be recognized & used in grammars, and the pronunciations can be either specified explicitly or inferred automatically.
* **Compilation Optimizations**: compilation while loading grammars uses the disk much less, and far fewer passes are made over the graphs, as separate modules have been customized & combined.
* **Better Model**: 50% more training data.

### Artifacts

* **`kaldi_model_zamia`**: [*new model version required!*] A compatible general English Kaldi nnet3 chain model.
* **`kaldi-dragonfly-winpython`**: A self-contained, portable, batteries-included (python & libraries & model) distribution of kaldi-active-grammar + dragonfly2. Just unzip and run!
* **`kaldi-dragonfly-winpython-dev`**: [*more recent development version*] A self-contained, portable, batteries-included (python & libraries & model) distribution of kaldi-active-grammar + dragonfly2. Just unzip and run!
* **`kaldi-caster-winpython-dev`**: [*more recent development version*] A self-contained, portable, batteries-included (python & libraries & model) distribution of kaldi-active-grammar + dragonfly2 + caster. Just unzip and run!

### **Donations are appreciated to encourage development.**

[![Donate](https://img.shields.io/badge/donate-PayPal-green.svg)](https://paypal.me/daanzu)
[![Donate](https://img.shields.io/badge/donate-Patreon-orange.svg)](https://www.patreon.com/daanzu)


v0.6.0: Big Fixes And Optimizations To Get Caster Running

### Artifacts

* **`kaldi_model_zamia`**: A compatible general English Kaldi nnet3 chain model.
* **`kaldi-dragonfly-winpython`**: [*stable release version*] A self-contained, portable, batteries-included (python & libraries & model) distribution of kaldi-active-grammar + dragonfly2. Just unzip and run!
* **`kaldi-dragonfly-winpython-dev`**: [*more recent development version*] A self-contained, portable, batteries-included (python & libraries & model) distribution of kaldi-active-grammar + dragonfly2. Just unzip and run!
* **`kaldi-caster-winpython-dev`**: [*more recent development version*] A self-contained, portable, batteries-included (python & libraries & model) distribution of kaldi-active-grammar + dragonfly2 + caster. Just unzip and run!

If you have trouble downloading, try using `wget --continue`.

### **Donations are appreciated to encourage development.**

[![Donate](https://img.shields.io/badge/donate-PayPal-green.svg)](https://paypal.me/daanzu)
[![Donate](https://img.shields.io/badge/donate-Patreon-orange.svg)](https://www.patreon.com/daanzu)


v0.7.1: Partial Decoding, Parallel Compilation, & Various Optimizations for 15-50% Speedup

Support is now included in dragonfly2 v0.17.0! You can try a self-contained distribution available below, of either stable or development versions.

### Notes

* **Partial Decoding**: support for having **separate Voice Activity Detection timeout values** based on whether the current utterance is complex (dictation) or not.
* **Parallel Compilation**: when compiling grammars/rules that are not cached, multiple can be compiled at once (up to your core count).
    * Example: loading Caster without cache is ~40% faster (in addition to optimizations below).
* **Various Optimizations**: loading even while cached sped up 15%.
* Refactored temporary/cache file handling
* Various bug fixes

### Artifacts

* **`kaldi_model_zamia`**: A compatible general English Kaldi nnet3 chain model.
* **`kaldi-dragonfly-winpython`**: [*stable release version*] A self-contained, portable, batteries-included (python & libraries & model) distribution of kaldi-active-grammar + dragonfly2. Just unzip and run!
* **`kaldi-dragonfly-winpython-dev`**: [*more recent development version*] A self-contained, portable, batteries-included (python & libraries & model) distribution of kaldi-active-grammar + dragonfly2. Just unzip and run!
* **`kaldi-caster-winpython-dev`**: [*more recent development version*] A self-contained, portable, batteries-included (python & libraries & model) distribution of kaldi-active-grammar + dragonfly2 + caster. Just unzip and run!

If you have trouble downloading, try using `wget --continue`.

### **Donations are appreciated to encourage development.**

[![Donate](https://img.shields.io/badge/donate-PayPal-green.svg)](https://paypal.me/daanzu)
[![Donate](https://img.shields.io/badge/donate-Patreon-orange.svg)](https://www.patreon.com/daanzu)


v1.0.0: Faster Loading, Python3, Grammar/Rule Weights, and more

Support is now included in dragonfly2 v0.18.0! You can try a self-contained distribution available below, of either stable or development versions.

### Notes

* **Direct Parsing**: parse recognitions directly on the FST, removing the (slow) `pyparsing` dependency.
    * Caster example: Loading is now **~50%** faster when cached, and the Kaldi backend accounts for only ~15% of loading time.
* **Python3**: both python 2 and 3 should be fully supported now.
    * **Unicode**: this should also fix unicode issues in various places in both python2/3.
* **Grammar/Rule Weights**: can specify weight, where grammars/rules with higher weight value are more likely to be recognized, compared to their peers, for an ambiguous recognition.
* **Generalized Alternative Dictation**: the cloud dictation feature has been generalized to make it easier to add other alternatives in the future.
* Various bug fixes & optimizations

### Artifacts

* **`kaldi_model_zamia`**: A compatible general English Kaldi nnet3 chain model.
* **`kaldi-dragonfly-winpython`**: [*stable release version*] A self-contained, portable, batteries-included (python & libraries & model) distribution of kaldi-active-grammar + dragonfly2. Just unzip and run!
* **`kaldi-dragonfly-winpython-dev`**: [*more recent development version*] A self-contained, portable, batteries-included (python & libraries & model) distribution of kaldi-active-grammar + dragonfly2. Just unzip and run!
* **`kaldi-caster-winpython-dev`**: [*more recent development version*] A self-contained, portable, batteries-included (python & libraries & model) distribution of kaldi-active-grammar + dragonfly2 + caster. Just unzip and run!

If you have trouble downloading, try using `wget --continue`.

### Donations are appreciated to encourage development.

[![Donate](https://img.shields.io/badge/donate-GitHub-pink.svg)](https://github.com/sponsors/daanzu) [![Donate](https://img.shields.io/badge/donate-Patreon-orange.svg)](https://www.patreon.com/daanzu) [![Donate](https://img.shields.io/badge/donate-PayPal-green.svg)](https://paypal.me/daanzu) [![Donate](https://img.shields.io/badge/preferred-GitHub-black.svg)](https://github.com/sponsors/daanzu)
[**GitHub** is currently matching all my donations $-for-$.]




v1.2.0: Improved Recognition, Weights on Any Elements, Pluggable Alternative Dictation, Stand-alone Plain Dictation Interface, and More

Support is now included in dragonfly2 v0.20.0! You can try a self-contained distribution available below, of either stable or development versions.

### Notes

* **Improved Recognition**: better graph construction/compilation should give significantly better overall recognition.
* **Weights on Any Elements**: you can now easily add weights to any element (including compound elements in `MappingRule`s), in addition to any rule/grammar.
* **Pluggable Alternative Dictation**: you can optionally pass a `callable` as `alternative_dictation` to define your own, external dictation engine.
* **Stand-alone Plain Dictation Interface**: the library now provides a simple interface for recognizing plain dictation without fancy active grammar features.
* **NOTE**: the default model directory is now `kaldi_model`.
* Various bug fixes & optimizations

### Artifacts

* **`kaldi_model_daanzu`**: A better overall compatible general English Kaldi nnet3 chain model than below.
* **`kaldi_model_zamia_daanzu_mediumlm`**: A compatible general English Kaldi nnet3 chain model, with a larger/better dictation language model than below.
* **`kaldi_model_zamia`**: A compatible general English Kaldi nnet3 chain model.
* **`kaldi-dragonfly-winpython`**: [*stable release version*] A self-contained, portable, batteries-included (python & libraries & model) distribution of kaldi-active-grammar + dragonfly2. Just unzip and run!
* **`kaldi-dragonfly-winpython-dev`**: [*more recent development version*] A self-contained, portable, batteries-included (python & libraries & model) distribution of kaldi-active-grammar + dragonfly2. Just unzip and run!
* **`kaldi-caster-winpython-dev`**: [*more recent development version*] A self-contained, portable, batteries-included (python & libraries & model) distribution of kaldi-active-grammar + dragonfly2 + caster. Just unzip and run!

If you have trouble downloading, try using `wget --continue`.

### Donations are appreciated to encourage development.

[![Donate](https://img.shields.io/badge/donate-GitHub-pink.svg)](https://github.com/sponsors/daanzu) [![Donate](https://img.shields.io/badge/donate-Patreon-orange.svg)](https://www.patreon.com/daanzu) [![Donate](https://img.shields.io/badge/donate-PayPal-green.svg)](https://paypal.me/daanzu) [![Donate](https://img.shields.io/badge/preferred-GitHub-black.svg)](https://github.com/sponsors/daanzu)
[**GitHub** is currently matching all my donations $-for-$.]



v1.3.0: Preparation and Fixes for Next Generation of Models

This should be included the next dragonfly version, or you can try a self-contained distribution available below.

You can subscribe to announcements on Gitter: see [instructions](https://gitlab.com/gitlab-org/gitter/webapp/blob/master/docs/notifications.md#announcements). [![Gitter](https://badges.gitter.im/kaldi-active-grammar/community.svg)](https://gitter.im/kaldi-active-grammar/community)

### Notes

* **Next Generation of Models**: support for a new generation of models, trained on more data, and with hopefully better accuracy.
* **User Lexicon**: if there is a ``user_lexicon.txt`` file in the current working directory of your initial loader script, its contents will be automatically added to the ``user_lexicon.txt`` in the active model when it is loaded.
* Various bug fixes & optimizations

### Artifacts

* **`kaldi_model_daanzu*`**: A better acoustic model, and varying levels of language model for dictation (bigger is generally better).
* **`kaldi_model_zamia`**: A compatible general English Kaldi nnet3 chain model.
* **`kaldi-dragonfly-winpython`**: [*stable release version*] A self-contained, portable, batteries-included (python & libraries & model) distribution of kaldi-active-grammar + dragonfly2. Just unzip and run!
* **`kaldi-dragonfly-winpython-dev`**: [*more recent development version*] A self-contained, portable, batteries-included (python & libraries & model) distribution of kaldi-active-grammar + dragonfly2. Just unzip and run!
* **`kaldi-caster-winpython-dev`**: [*more recent development version*] A self-contained, portable, batteries-included (python & libraries & model) distribution of kaldi-active-grammar + dragonfly2 + caster. Just unzip and run!

If you have trouble downloading, try using `wget --continue`.

### Donations are appreciated to encourage development.

[![Donate](https://img.shields.io/badge/donate-GitHub-pink.svg)](https://github.com/sponsors/daanzu) [![Donate](https://img.shields.io/badge/donate-Patreon-orange.svg)](https://www.patreon.com/daanzu) [![Donate](https://img.shields.io/badge/donate-PayPal-green.svg)](https://paypal.me/daanzu) [![Donate](https://img.shields.io/badge/preferred-GitHub-black.svg)](https://github.com/sponsors/daanzu)
[**GitHub** is matching (only) my **GitHub Sponsors** donations.]





v1.4.0: MacOS Support, And Faster Graph Compilation

Support is now included in dragonfly2 v0.22.0! You can try a self-contained distribution available below.

You can subscribe to announcements on Gitter: see [instructions](https://gitlab.com/gitlab-org/gitter/webapp/blob/master/docs/notifications.md#announcements). [![Gitter](https://badges.gitter.im/kaldi-active-grammar/community.svg)](https://gitter.im/kaldi-active-grammar/community)

### Notes

* **MacOS Support**
* **Faster Graph Compilation**
* **Dictation**: the dictation model now does not recognize a zero-word sequence
* Various bug fixes & optimizations

### Artifacts

* **`kaldi_model_daanzu*`**: A better acoustic model, and varying levels of language model for dictation (bigger is generally better).
* **`kaldi_model_zamia`**: A compatible general English Kaldi nnet3 chain model.
* **`kaldi-dragonfly-winpython`**: [*stable release version*] A self-contained, portable, batteries-included (python & libraries & model) distribution of kaldi-active-grammar + dragonfly2. Just unzip and run!
* **`kaldi-caster-winpython-dev`**: [*more recent development version*] A self-contained, portable, batteries-included (python & libraries & model) distribution of kaldi-active-grammar + dragonfly2 + caster. Just unzip and run!

If you have trouble downloading, try using `wget --continue`.

### Donations are appreciated to encourage development.

[![Donate](https://img.shields.io/badge/donate-GitHub-pink.svg)](https://github.com/sponsors/daanzu) [![Donate](https://img.shields.io/badge/donate-Patreon-orange.svg)](https://www.patreon.com/daanzu) [![Donate](https://img.shields.io/badge/donate-PayPal-green.svg)](https://paypal.me/daanzu) [![Donate](https://img.shields.io/badge/preferred-GitHub-black.svg)](https://github.com/sponsors/daanzu)
[**GitHub** is matching (only) my **GitHub Sponsors** donations.]





v1.5.0: Improved Recognition Confidence Estimation

You can subscribe to announcements on Gitter: see [instructions](https://gitlab.com/gitlab-org/gitter/webapp/blob/master/docs/notifications.md#announcements). [![Gitter](https://badges.gitter.im/kaldi-active-grammar/community.svg)](https://gitter.im/kaldi-active-grammar/community)

### Notes

* **Improved Recognition Confidence Estimation**: two new, different measures:
    * `confidence`: basically the difference in how much "better" the returned recognition was, compared to the second best guess (`>0`)
    * `expected_error_rate`: an estimate of how often similar utterances are incorrect (roughly out of `1.0`, but can be greater)
* Refactoring in preparation for future improvements
* Various bug fixes & optimizations

### Artifacts

* **Models are available [here](https://github.com/daanzu/kaldi-active-grammar/blob/master/docs/models.md)**
* **`kaldi-dragonfly-winpython`**: [*stable release version*] A self-contained, portable, batteries-included (python & libraries & model) distribution of kaldi-active-grammar + dragonfly2. Just unzip and run!
* **`kaldi-caster-winpython-dev`**: [*more recent development version*] A self-contained, portable, batteries-included (python & libraries & model) distribution of kaldi-active-grammar + dragonfly2 + caster. Just unzip and run!

If you have trouble downloading, try using `wget --continue`.

### Donations are appreciated to encourage development.

[![Donate](https://img.shields.io/badge/donate-GitHub-pink.svg)](https://github.com/sponsors/daanzu) [![Donate](https://img.shields.io/badge/donate-Patreon-orange.svg)](https://www.patreon.com/daanzu) [![Donate](https://img.shields.io/badge/donate-PayPal-green.svg)](https://paypal.me/daanzu) [![Donate](https://img.shields.io/badge/preferred-GitHub-black.svg)](https://github.com/sponsors/daanzu)
[**GitHub** is matching (only) my **GitHub Sponsors** donations.]




v1.6.0: Easier Configuration; Public Automated Builds

You can subscribe to announcements on GitHub (see Watch panel above), or on Gitter (see [instructions](https://gitlab.com/gitlab-org/gitter/webapp/blob/master/docs/notifications.md#announcements) [![Gitter](https://badges.gitter.im/kaldi-active-grammar/community.svg)](https://gitter.im/kaldi-active-grammar/community))

### Added
* Can now pass configuration dict to `KaldiAgfNNet3Decoder`, `PlainDictationRecognizer` (without `HCLG.fst`).
* Continuous Integration builds run on GitHub Actions for Windows (x64), MacOS (x64), Linux (x64).

### Changed
* Refactor of passing configuration to initialization.
* `PlainDictationRecognizer.decode_utterance` can take `chunk_size` parameter.
* Smaller binaries: MacOS 11MB -> 7.6MB, Linux 21MB -> 18MB.

### Fixed
* Confidence measurement in the presence of multiple, redundant rules.
* Python3 int division bug for cloud dictation.

### Artifacts

* **Models are available [here](https://github.com/daanzu/kaldi-active-grammar/blob/master/docs/models.md)**
* **`kaldi-dragonfly-winpython`**: [*stable release version*] A self-contained, portable, batteries-included (python & libraries & model) distribution of kaldi-active-grammar + dragonfly2. Just unzip and run!
* **`kaldi-caster-winpython-dev`**: [*more recent development version*] A self-contained, portable, batteries-included (python & libraries & model) distribution of kaldi-active-grammar + dragonfly2 + caster. Just unzip and run!

If you have trouble downloading, try using `wget --continue`.

### Donations are appreciated to encourage development.

[![Donate](https://img.shields.io/badge/donate-GitHub-pink.svg)](https://github.com/sponsors/daanzu) [![Donate](https://img.shields.io/badge/donate-Patreon-orange.svg)](https://www.patreon.com/daanzu) [![Donate](https://img.shields.io/badge/donate-PayPal-green.svg)](https://paypal.me/daanzu) [![Donate](https://img.shields.io/badge/preferred-GitHub-black.svg)](https://github.com/sponsors/daanzu)
[**GitHub** is matching (only) my **GitHub Sponsors** donations.]



v2.0.0: Faster Grammar Compilation; Cleaner Codebase; Preparation For New Features


v2.1.0

Minor fix for OpenBLAS compilation for some architectures on linux/mac.

See [major changes introduced in v2.0.0 and associated downloads](https://github.com/daanzu/kaldi-active-grammar/releases/tag/v2.0.0).


v3.2.0

Functionality-wise, only one small bug-fix: to the broken alternative dictation interface. But extensive build and infrastructure changes lead me to make this a minor release rather than just a patch release, out of an abundance of caution.

Active development has resumed after a long break! (While development paused, the project was continuously maintained and actively used in production.) Look forward to more frequent releases in the hopefully-near future.



You can subscribe to announcements on GitHub (see Watch panel above), or on Gitter (see [instructions](https://gitlab.com/gitlab-org/gitter/webapp/blob/master/docs/notifications.md#announcements) [![Gitter](https://badges.gitter.im/kaldi-active-grammar/community.svg)](https://gitter.im/kaldi-active-grammar/community))

#### Donations are appreciated to encourage development.

[![Donate](https://img.shields.io/badge/donate-GitHub-EA4AAA.svg?logo=githubsponsors)](https://github.com/sponsors/daanzu) [![Donate](https://img.shields.io/badge/donate-PayPal-002991.svg?logo=paypal)](https://paypal.me/daanzu) [![Donate](https://img.shields.io/badge/donate-GitHub-EA4AAA.svg?logo=githubsponsors)](https://github.com/sponsors/daanzu)


### Artifacts

* **Models are available [here](https://github.com/daanzu/kaldi-active-grammar/blob/master/docs/models.md)** and below.
* **`kaldi-dragonfly-winpython`**: A self-contained, portable, batteries-included (python & libraries & model) distribution of kaldi-active-grammar + dragonfly2. Just unzip and run!
* **`kaldi-caster-winpython`**: A self-contained, portable, batteries-included (python & libraries & model) distribution of kaldi-active-grammar + dragonfly2 + caster. Just unzip and run!

If you have trouble downloading, try using `wget --continue`.




* **`kaldi-dragonfly-winpython`**: [*stable release version*] A self-contained, portable, batteries-included (python & libraries & model) distribution of kaldi-active-grammar + dragonfly2. Just unzip and run!
* **`kaldi-caster-winpython`**: [*more recent development version*] A self-contained, portable, batteries-included (python & libraries & model) distribution of kaldi-active-grammar + dragonfly2 + caster. Just unzip and run!

This should be included the next dragonfly version, or you can try a self-contained distribution available below.
