# Changelog

All notable changes to this project will be documented in this file.
Note that the project (and python wheel) is built from a duorepo (2 separate repos used together), so changes from both will be reflected here, but the commits are spread between both.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html) since v1.0.0.

## [Unreleased] - Changes: [KaldiAG](https://github.com/daanzu/kaldi-active-grammar/compare/v3.2.0...master) [KaldiFork](https://github.com/daanzu/kaldi-fork-active-grammar/compare/kag-v3.2.0...master)

### Added

* Direct text mimicking is now available through `Compiler.mimic(...)` and the active decoder wrappers. `Compiler.mimic(...)` matches across exported active rule IDs and returns output with the outer rule marker expected by `Compiler.parse_output(...)`; the lower-level wrapper can instead select one rule with `grammar_fst_index`, in which case its marker-free output must be handled directly. Optional dictation-grammar matching is configured separately through `init_decoder(..., dictation_g_fst_file=...)`. The wrappers support zero-length match-only probes, and `Compiler.mimic(...)` exposes `output_max_length` to configure its output buffer size.
  * **Known limitation:** ordinary LAF rules use relabeled input-word IDs while the shared mimic path currently tokenizes against the original word table, so direct mimic does not yet match those rules in either all-rule or selected-rule mode.
* `KaldiRule(..., exported=False)` now supports non-exported subrules that are referenced by other grammars without being added to the top-level recognition graph. Exported and non-exported rules use separate ID pools (currently IDs `0–999` and `1000–9999`, respectively).

### Changed

* LAF decoding now uses an activity-aware native replacement/composition pipeline (`ActiveReplaceFst`, `ActiveComposeFst`, `ActiveArcMapFst`, `ActiveLookaheadFst`, and `ActiveCache`). Grammar activity changes between utterances incrementally invalidate affected graph state instead of requiring a complete rebuild; `decode_fst_incremental` controls that behavior and `decode_fst_naive` remains available as a rebuild-based comparison mode. LAF initialization now also rejects an `HCLr.fst` that does not support the required output-label lookahead composition.
* Rule-specific mimic FST copies have their epsilon-disambiguation and output-end labels transformed when grammars are loaded, and the dictation grammar is retained as a lazy output projection instead of being eagerly converted to a constant FST. This moves reusable preprocessing out of `mimic()`; each call still constructs its input-specific replacement/composition graph.
* **Breaking: LAF lexicons are now fixed at compiler construction.** Adding words or pronunciations at runtime is rejected; rebuild the LAF graph bundle, including `HCLr.fst`, `Gr.fst`, `disambig_tid.int`, and `relabel_ilabels.int`, before constructing the compiler. When relabeling data is present, a missing `words.relabeled.txt` is generated automatically.
* Native AGF and LAF decoders now copy and own caller-provided rule FSTs independently and safely replace decoder-owned graphs. LAF dictation loading preserves specialized serialized FST representations such as `NGramFst`, and native linking retains the OpenFST n-gram library needed by those representations.
* **Breaking: the supported distribution is platform-specific wheels only.** Source distributions (`sdist`) are intentionally unsupported because a usable installation must contain the matching native Kaldi library.
* Python 3.9 through 3.14 are the declared support range; CI exercises 3.9 through 3.13 (3.14 currently lacks the required Piper test wheels), and Python 3.6 through 3.8 are no longer classified as supported. Installation metadata remains permissive for compatibility.
* Native builds now use OpenBLAS 0.3.34 where OpenBLAS is selected; Darwin uses Kaldi's Accelerate path and no longer builds the unused OpenBLAS dependency. Shared-library, LAPACK hidden Fortran string-length, Intel macOS dylib-header, and Darwin linker handling were updated across the supported build paths.
* Native FST hash computation now sorts arcs by input label and hashes a compact binary structural representation, improving hashing performance; existing native FST cache filenames may change. The standalone `WFST.get_fst_text()` is cache-independent and no longer takes a cache argument, while the new `WFST.compute_hash(seed)` accepts the dependency-hash seed directly.
* Cache hits no longer touch cached FST timestamps, and warm model setup no longer changes the timestamp of an existing `user_lexicon.txt`. Cache persistence and generated relabeled-word-table replacement are atomic, malformed or legacy cache state is rebuilt safely, incomplete-rebuild markers are scoped to their rebuild transactions, and optional missing dependencies are recorded explicitly.
* Symbol tables are now loaded and validated in one pass, with one-pass multi-symbol lookup replacing repeated phone-table scans. Loading preserves last-entry-wins duplicate behavior and the dictionary identities used by native FST label lookup, while rejecting malformed, empty, or nonterminal-only tables and inconsistent nonterminal offsets. This also removes redundant vocabulary copies and base-word-table scans during compiler startup.
* Python commits now lock their matching Kaldi fork to an exact commit in `kaldi-native-revision.txt`; local development helpers, native build selection, CI checkouts, and cache keys all use that recorded revision instead of inferred matching branch names.
* Package version resolution moved into `_version.py` with an exposed `__version_base__` release target and a `.dev0` source-checkout fallback. Development wheels now receive unique, sortable PEP 440 versions containing a UTC build timestamp and Git revision (plus a dirty-tree marker when applicable). Multi-platform CI builds share one resolved version, tagged builds use the tag exactly, and the installed package reports the same version as its wheel metadata.
* `NativeWFST.add_arc()` now buffers arc construction in bounded native batches, flushing before graph inspection, hashing, output, compilation, or decoder loading. `NativeWFST.add_arcs()` is available for callers that can supply arcs as an iterable, and universal grammar construction uses that bulk path. Native batch insertion validates every source and destination state before appending any arc, so an invalid batch cannot partially mutate the graph.
* **Changed: dependency cache validation now uses canonical identities and a schema-versioned content hash.** Existing caches are rebuilt once when the schema changes, and the new `dependencies_hash` representation causes one full AGF recompilation on its first use; subsequent warm starts retain stable FST filenames. `Compiler(..., strict_content_validation=True)` is available when every dependency must be content-hashed so same-size, same-mtime replacements are detected.
* **Breaking: cache invalidation is now a construction-time compiler option.** Use `Compiler(..., invalidate=True)` to rebuild model lexicon state and, when FST caching is enabled, discard cached grammar FSTs. `Compiler.fst_cache`, `KaldiRule.fst_cache`, and the public `FSTFileCache`/generic file-cache manipulation surface are no longer supported; cache state is private implementation detail.
* **Breaking: grammar activity is now a sparse set of active rule IDs instead of a positional Boolean mask.** `decoder.decode(...)`, `decoder.mimic(...)`, and `Compiler.mimic(...)` now expect `grammars_activity` to be an iterable of `KaldiRule.id` values (e.g. `[rule.id]`) rather than one Boolean per loaded rule (e.g. `[True, False, ...]`). `None` still means "keep the current native activity" (use it for utterance continuation chunks); an empty iterable explicitly disables all rules. IDs are deduplicated and sorted before the native call; booleans, negative IDs, and non-integers are rejected instead of being silently misread.
  * Rule IDs are stable for a rule's lifetime and do not shift when another rule is unloaded; a freed ID may later be reused by a new rule.
  * **This requires a matching Kaldi fork build.** The declared native decode interface changed from a `bool*` positional mask to an `int32_t*` rule-ID array (with unsigned 32-bit sample/activity counts). The binary calling convention is still similar enough that mixing this Python version with an older native library may load and run while silently misinterpreting activity rather than failing clearly.
* **Breaking: lifecycle cleanup now uses `close()` exclusively.** The obsolete `destroy()` and `NativeWFST.destruct()` aliases were removed. Native resource owners including `Compiler`, `KaldiRule`, `PlainDictationRecognizer`, decoder wrappers, and `NativeWFST` now provide idempotent deterministic close, context-manager cleanup, and explicit use-after-close errors. Owned CFFI pointers also have non-owner-retaining garbage-collection finalizers, so resources in Python reference cycles can be reclaimed; `Compiler.close()` closes every rule it created, including unloaded and non-exported rules.
* **Breaking: the example `MicAudio` helper also replaces `destroy()` with `close()` and context-manager cleanup.** Closing now stops and joins its worker thread before closing the stream and wakes blocked readers; reconnecting stops the old worker before replacing its stream.
* **Breaking: compiler FSTs are now native-only.** `Compiler` no longer accepts `native_fst`, `agf-indirect`, or non-native rule graphs; every `KaldiRule.fst` is a `NativeWFST`. `WFST` remains available as a standalone utility, while AGF graph caching continues to use native graph hashes and `NativeWFST.load_file`.
  * AGF graph compilation is unavailable when `framework='laf'`; LAF receives native rule FSTs directly and does not construct an AGF compiler.
  * Python AGF/LAF grammar add/reload and AGF top-graph decoder inputs now use explicit rule IDs and native FST pointers; file-backed inputs remain for AGF graph compilation and dictation graphs. Legacy Python text-FST paths (`grammar_fst_text`, `add_grammar_fst_text`), non-native rule insertion interfaces, `Compiler.num_kaldi_rules`, `Compiler.nonterminals`, `Compiler.alloc_rule_id()`, `Compiler.free_rule_id()`, `KaldiRule.fst_cache`, and `KaldiRule.fst_wrapper` were removed.
* **Breaking: the legacy token-side mimic parser was removed.** `Compiler.parse_output_for_rule()` previously matched decoder text against a Python-side rule FST; the replacement all-rule path is native `Compiler.mimic(...)` followed by `Compiler.parse_output(...)`.
* `Compiler.parse_output(...)` now raises `ValueError` when non-empty output lacks the expected leading `#nonterm:rule<ID>` marker.
* The native nnet3 `get_output` path now logs a warning when its caller-provided output buffer truncates a decoded hypothesis. Its legacy return contract is otherwise unchanged; direct mimic overflow uses the distinct error behavior described below.
* Native Dragonfly linking now explicitly includes Kaldi's `kaldi-gmm` archive for remaining `online2`/i-vector symbols, while the legacy Dragonfly GMM implementations remain removed.

### Fixed

* Fixed LAF decoding of dictation graphs whose word labels were relabeled for composition; decoded dictation words are restored to the original word IDs.
* Fixed empty-activity decoding and active-grammar/mimic-graph invalidation around grammar add, reload, and removal, including rejection of graph mutation while an utterance decoder is active.
* Fixed direct-mimic edge cases involving epsilon-disambiguation labels, non-exported rules, output nonterminal boundaries, and off-by-one rule indexing.
* Fixed direct-mimic output overflow handling: the native interface now reports the required buffer length, and both `Compiler.mimic(...)` and the decoder wrapper raise `KaldiError` instead of returning a truncated string or treating overflow as a genuine no-match. This changes the native `nnet3_active_base__mimic` ABI and requires the matching Kaldi fork revision.
* Fixed `Compiler.parse_output(...)` treating `None` decoder output as a result instead of no recognition.
* Fixed symbol-table lookups to require complete symbol matches rather than prefixes; loading now rejects malformed, empty, or nonterminal-only tables and mismatched nonterminal offsets while preserving the map identities captured by native FSTs.
* Fixed duplicate shared native declarations when multiple decoder backends are initialized through the same CFFI handle.
* Fixed native AGF compiler ownership leaks: its large lexicon FST and optional symbol table are now RAII-owned, and temporary prepend/append nonterminal FSTs are released after graph compilation instead of accumulating across compiler constructions.
* Fixed native decoder grammar ownership on teardown and failed or partially completed add/reload paths. Grammar maps now use RAII ownership, reload/removal release the prior graph deterministically, and graph invalidation occurs before borrowed pointers are replaced or released.
* Fixed `PlainDictationRecognizer` with a caller-supplied `fst_file` dereferencing a nonexistent internal compiler while removing silence words; it now uses the plain recognizer's `!SIL` fallback.
* Fixed `Compiler.compile_universal_grammar()` constructing a nonterminal-free rule with an incompatible exported-rule flag.
* **Fixed: failed model initialization no longer leaves a warm dependency cache.** Cache commits are now deferred until lexicon generation, optional LAF file generation, and word-table loading all complete, so a later startup retries after an initialization failure; failed relabeled-word generation also removes partial output before retry.

### Removed

* **Breaking: removed the Python `KaldiGmmDecoder` and `KaldiOtfGmmDecoder` wrappers and the native direct, on-the-fly (OTF), active-grammar (AGF), and active-union (AUF) GMM implementations and C entry points.** The supported decoder interfaces are the nnet3-based plain, AGF, and LAF paths.

### Development

* Added long-term and released-wheel compatibility stress harnesses covering prolonged grammar activity changes, rule-ID recycling, reloads, cache-hit recompilation, dictation-bearing rules, native resource metrics, phrase separability screening, correctness gates, and performance regression baselines.
* Expanded regression coverage for cache transactions, lifecycle cleanup, symbol tables, native revision locking, generated versions, batched FST construction, plain dictation, AGF/LAF behavior, and wheel installation. The default test command excludes the prolonged and stress workloads; they are opt-in through pytest markers and Just recipes.
* Added dedicated architecture, building, testing, and release documentation, including historical Python/native commit pairings and standalone native CI artifacts. Wheel CI now tests producer-specific artifacts directly and summarizes per-platform test results.
* Added an examples index documenting the runnable scripts and supporting utilities; the root README and architecture documentation now point to the examples directory.
* Added reusable local test-environment and stress recipes; separate-process runners are now legacy diagnostics with fail-fast opt-in, source-build tests are excluded from installed-wheel validation, and native development builds use `ccache` automatically when available. CI also moved to current macOS runners and Node 24-compatible action versions.
* Documented `KALDIAG_BUILD_SKIP_NATIVE=1` for source-tree wheel builds whose matching native artifacts have already been staged, while published and supported distributions remain platform-specific wheels only.

## [3.2.0](https://github.com/daanzu/kaldi-active-grammar/releases/tag/v3.2.0) - 2025-11-02 - Changes: [KaldiAG](https://github.com/daanzu/kaldi-active-grammar/compare/v3.1.0...v3.2.0) [KaldiFork](https://github.com/daanzu/kaldi-fork-active-grammar/compare/kag-v3.1.0...kag-v3.2.0)

### Added

* Comprehensive test suite with 80+ tests covering grammar compilation, plain dictation, and alternative dictation
* Test infrastructure using pytest with TTS-generated test audio (Piper)
* `AGENTS.md` documentation for AI coding agents with project architecture and development guidance
* Exposed `NativeWFST` at package top-level for easier importing
* Support for testing with multiple platforms and Python versions (3.9-3.13)

### Changed

* **CI/CD Improvements**:
  * Implemented comprehensive caching of native binaries by commit hash
  * Added caching of test setup data
  * Updated build workflow to run on all pushes and PRs
  * Modified macOS wheel builds to use delocate instead of ad-hoc manual library handling
  * Improved Linux wheel build with cleaner output and better caching
  * Updated CI to support latest GitHub Actions runners (Ubuntu 24.04, Windows 2025, macOS 13/15/26)
  * Moved tests into main build workflow for faster feedback
  * Added notices for built wheels in CI output
* Relaxed Python package requirements version specifiers for better compatibility
* Updated setup.py classifiers to include Python 3.11, 3.12, 3.13, 3.14
* Dropped Python 2 from wheel tag (py3 instead of py2.py3), as Python 2 is no longer supported
* Improved comments and cleanup in Justfile

### Fixed

* Updated CI workflows to properly handle latest runner environments
* Fixed Linux build configuration and wrapper script
* Cleaned up and standardized build processes across all platforms

### Development

* Refactored test structure for better organization and maintainability
* Added test generators for creating synthetic speech using Piper TTS and Google TTS
* Added helper utilities for test fixtures and audio generation
* Improved test coverage for edge cases (empty audio, garbage audio, very short/long audio)
* Added tests for complex grammar patterns (diamond, cascade, hub-and-spoke, etc.)
* Added comprehensive alternative dictation tests with mocking

## [3.1.0](https://github.com/daanzu/kaldi-active-grammar/releases/tag/v3.1.0) - 2021-11-24 - Changes: [KaldiAG](https://github.com/daanzu/kaldi-active-grammar/compare/v3.0.0...v3.1.0) [KaldiFork](https://github.com/daanzu/kaldi-fork-active-grammar/compare/kag-v3.0.0...kag-v3.1.0)

### Fixed

* Fix updating of SymbolTable multiple times for new words, so that there is only one instance for a single Model.

### Changed

* Only mark lexicon stale if it was successfully modified.
* Removed deprecated CLI binaries from Windows build, reducing wheel size by ~65%.

## [3.0.0](https://github.com/daanzu/kaldi-active-grammar/releases/tag/v3.0.0) - 2021-10-31 - Changes: [KaldiAG](https://github.com/daanzu/kaldi-active-grammar/compare/v2.1.0...v3.0.0) [KaldiFork](https://github.com/daanzu/kaldi-fork-active-grammar/compare/kag-v2.1.0...kag-v3.0.0)

### Changed

* Pronunciation generation for lexicon now better supports local mode (using the `g2p_en` package), which is now also the default mode. It is also preferred over the online mode (using CMU's web service), which is now disabled by default. See the Setup section of the README for details. The new models now include the data files for `g2p_en`.
* `PlainDictation` output now discards any silence words from transcript.
* `lattice_beam` default value reduced from `6.0` to `5.0`, to hopefully avoid occasional errors.
* Removed deprecated CLI binaries from build for linux/mac.

### Fixed

* Whitespace in the model path is once again handled properly (thanks [@matthewmcintire](https://github.com/matthewmcintire)).
* `NativeWFST.has_path()` now handles loops.
* Linux/Mac binaries are now more stripped.

## [2.1.0](https://github.com/daanzu/kaldi-active-grammar/releases/tag/v2.1.0) - 2021-04-04 - Changes: [KaldiAG](https://github.com/daanzu/kaldi-active-grammar/compare/v2.0.2...v2.1.0) [KaldiFork](https://github.com/daanzu/kaldi-fork-active-grammar/compare/kag-v2.0.2...kag-v2.1.0)

### Added

* NativeWFST support for checking for impossible graphs (no successful path), which can then fail to compile.
* Debugging info for NativeWFST.

### Changed

* `lattice_beam` default value reduced from `8.0` to `6.0`, to hopefully avoid occasional errors.

### Fixed

* Reloading grammars with NativeWFST.

## [2.0.2](https://github.com/daanzu/kaldi-active-grammar/releases/tag/v2.0.2) - 2021-03-30 - Changes: [KaldiAG](https://github.com/daanzu/kaldi-active-grammar/compare/v2.0.0...v2.0.2) [KaldiFork](https://github.com/daanzu/kaldi-fork-active-grammar/compare/kag-v2.0.0...kag-v2.0.2)

### Changed

* Minor fix for OpenBLAS compilation for some architectures on linux/mac

## [2.0.0](https://github.com/daanzu/kaldi-active-grammar/releases/tag/v2.0.0) - 2021-03-21 - Changes: [KaldiAG](https://github.com/daanzu/kaldi-active-grammar/compare/v1.8.0...v2.0.0) [KaldiFork](https://github.com/daanzu/kaldi-fork-active-grammar/compare/kag-v1.8.0...kag-v2.0.0)

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
