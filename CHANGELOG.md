# Changelog

All notable changes to this project will be documented in this file.
Note that the project (and python wheel) is built from a duorepo (2 separate repos used together), so changes from both will be reflected here, but the commits are spread between both.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html) since v1.0.0.

## [Unreleased] - Changes: [KaldiAG](https://github.com/daanzu/kaldi-active-grammar/compare/v2.0.0...master) [KaldiFork](https://github.com/daanzu/kaldi-fork-active-grammar/compare/kag-v2.0.0...master)

## [2.0.2](https://github.com/daanzu/kaldi-active-grammar/releases/tag/v2.0.2) - 2020-09-05 - Changes: [KaldiAG](https://github.com/daanzu/kaldi-active-grammar/compare/v2.0.0...v2.0.2) [KaldiFork](https://github.com/daanzu/kaldi-fork-active-grammar/compare/kag-v2.0.0...kag-v2.0.2)

### Changed

* Minor fix for OpenBLAS compilation for some architectures on linux/mac

## [2.0.0](https://github.com/daanzu/kaldi-active-grammar/releases/tag/v2.0.0) - 2020-09-05 - Changes: [KaldiAG](https://github.com/daanzu/kaldi-active-grammar/compare/v1.8.0...v2.0.0) [KaldiFork](https://github.com/daanzu/kaldi-fork-active-grammar/compare/kag-v1.8.0...kag-v2.0.0)

### Added

* Native FST support, via direct wrapping of OpenFST, rather than Python text-format implementation
    * Eliminates grammar (G) FST compilation step
* Internalized many graph construction steps, via direct use of native Kaldi/OpenFST functions, rather than invoking separate CLI processes
    * Eliminates need for many temporary files (FSTs, `.conf`s, etc) and pipes
* Example usage for allowing mixing of free dictation with strict command phrases
* Experimental support for "look ahead" graphs, as an alternative to full HCLG compilation
* Experimental support for rescoring with CARPA LMs
* Experimental support for rescoring with RNN LMs
* Experimental support for "priming" RNNLM previous left context for each utterance

### Changed

* OpenBLAS is now the default linear algebra library (rather than Intel MKL) on Linux/MacOS
    * Because it is open source and provides good performance on all hardware (including AMD)
    * Windows is more difficult for this, and will be implemented soon in a later release
* Default `tmp_dir` is now set to `[model_dir]/cache.tmp`
* `tmp_dir` is now optional, and only needed if caching compiled FSTs (or for certain framework/option combinations)
* File cache is now stored at `[model_dir]/file_cache.json`
* Optimized adding many new words to the lexicon, in many different grammars, all in one loading session: only rebuild `L_disambig.fst` once at the end.
* External interfaces: `Compiler.__init__()`, decoding setup, etc.
* Internal interfaces: wrappers, etc.
* Major refactoring of C++ components, with a new inheritance hierarchy and configuration mechanism, making it easier to use and test features with and without "activity"
* Many build changes

### Removed

* Python 2.7 support: it may still work, but will not be a focus.
* Google cloud speech-to-text removed, as an unneeded dependency. Alternative dictation is still supported as an option, via a callback to an external provider.

### Deprecated

* Separate CLI Kaldi/OpenFST executables
* Indirect AGF graph compilation (framework==`agf-indirect`)
* Non-native FSTs
* parsing_framework==`text`

## [1.8.0](https://github.com/daanzu/kaldi-active-grammar/releases/tag/v1.8.0) - 2020-09-05 - Changes: [KaldiAG](https://github.com/daanzu/kaldi-active-grammar/compare/v1.7.0...v1.8.0) [KaldiFork](https://github.com/daanzu/kaldi-fork-active-grammar/compare/kag-v1.7.0...kag-v1.8.0)

### Added
* New speech models (should be better in general, and support new noise resistance)
* Make failed AGF graph compilation save and output stderr upon failure automatically
* Example of complete usage with a grammar and microphone audio
* Various documentation

### Changed
* Top FST now accepts various noise phones (if present in speech model), making it more resistant to noise
* Cleanup error handling in compiler, supporting Dragonfly backend automatically printing excerpt of the Rule that failed

### Fixed
* Mysterious windows newline bug in some environments

## [1.7.0](https://github.com/daanzu/kaldi-active-grammar/releases/tag/v1.7.0) - 2020-08-01 - Changes: [KaldiAG](https://github.com/daanzu/kaldi-active-grammar/compare/v1.6.2...v1.7.0) [KaldiFork](https://github.com/daanzu/kaldi-fork-active-grammar/compare/kag-v1.6.2...kag-v1.7.0)

### Added
* Add automatic saving of text FST & compiled FST files with log level 5

### Changed
* Miscellaneous naming

### Fixed
* Support compiling some complex grammars (Caster text manipulation), by simplifying during compilation (remove epsilons, and determinize)

## [1.6.2](https://github.com/daanzu/kaldi-active-grammar/releases/tag/v1.6.2) - 2020-07-20 - Changes: [KaldiAG](https://github.com/daanzu/kaldi-active-grammar/compare/v1.6.1...v1.6.2) [KaldiFork](https://github.com/daanzu/kaldi-fork-active-grammar/compare/kag-v1.6.1...kag-v1.6.2)

### Fixed
* Add missing rnnlm library file in MacOS build

## [1.6.1](https://github.com/daanzu/kaldi-active-grammar/releases/tag/v1.6.1) - 2020-07-19 - Changes: [KaldiAG](https://github.com/daanzu/kaldi-active-grammar/compare/v1.6.0...v1.6.1) [KaldiFork](https://github.com/daanzu/kaldi-fork-active-grammar/compare/kag-v1.6.0...kag-v1.6.1)

### Changed
* Windows wheels now only require the VS2017 (not VS2019) redistributables to be installed

## [1.6.0](https://github.com/daanzu/kaldi-active-grammar/releases/tag/v1.6.0) - 2020-07-11 - Changes: [KaldiAG](https://github.com/daanzu/kaldi-active-grammar/compare/v1.5.0...v1.6.0) [KaldiFork](https://github.com/daanzu/kaldi-fork-active-grammar/compare/kag-v1.5.0...kag-v1.6.0)

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

## Earlier versions

See [GitHub releases notes](https://github.com/daanzu/kaldi-active-grammar/releases).
