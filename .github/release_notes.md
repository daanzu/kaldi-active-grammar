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





This should be included the next dragonfly update, or you can try a self-contained distribution available below.
