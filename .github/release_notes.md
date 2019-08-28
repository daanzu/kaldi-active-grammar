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

This should be included the next dragonfly update, or you can try a self-contained distribution available on the release page.

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
