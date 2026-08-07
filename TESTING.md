# Testing Kaldi Active Grammar

The integration tests use a Piper voice to synthesize repeatable 16 kHz audio
and a compatible Kaldi test model to perform real decoding. From the repository
root, download those assets and create the test environment with:

```sh
just setup-tests
just setup-tests-venv
```

Run the normal suite with `just test`:

```sh
just test
```

The separate-process runners, `just test-separately` and
`just test-package-separately`, are deprecated. They are retained only for
historical native-state or isolation diagnosis; the memory leaks that motivated
them are believed to be fixed. Use `just test` or `just test-package` instead.

If a legacy investigation still requires process isolation, the deprecated
runners remain available:

```sh
just test-separately
just test-package-separately
```

Grammar integration cases are parameterized for the supported native-FST
frameworks: direct active grammar (`agf-direct`) and lookahead (`laf`). Every
case asserts that compiler-managed rules use `NativeWFST`. LAF cases require
`HCLr.fst`, `Gr.fst`, `disambig_tid.int`, `relabel_ilabels.int`, and
`words.relabeled.txt` in `tests/kaldi_model`; pytest reports a skip naming any
missing files.

## Prolonged grammar activity test

`test_prolonged_changing_rule_activity` models an extended application session
in which one compiler and decoder remain alive while grammar context changes
between utterances. It:

* compiles and loads 24 independent command rules;
* synthesizes each command once, keeping speech input stable across repetitions;
* processes 1,000 utterances per framework without recreating the decoder;
* rotates the target across every rule with a coprime stride; and
* changes the active set on every utterance, cycling from one active rule to all
  24 rules.

This coverage is intended to expose failures that short tests may miss, such as
state leaking between utterances, stale activity, rule-ID handling errors,
framework-specific graph reconstruction problems, and failures that emerge
only after repeated decoding. It is marked `prolonged` and excluded by the
default pytest configuration because both framework cases perform substantial
real speech decoding.

Run both framework cases explicitly with:

```sh
just test -m prolonged tests/test_grammar.py::TestGrammar::test_prolonged_changing_rule_activity
```

Run only one framework by selecting its parameter ID. Quote the node ID so
shells do not interpret the square brackets:

```sh
just test -m prolonged 'tests/test_grammar.py::TestGrammar::test_prolonged_changing_rule_activity[agf]'
just test -m prolonged 'tests/test_grammar.py::TestGrammar::test_prolonged_changing_rule_activity[laf]'
```

The test pre-generates only 24 audio samples, so most of its runtime is spent in
the decoder workload. Runtime varies with the platform, model, native build,
and framework; the LAF case also reconstructs its active decode graph at each
utterance boundary.
