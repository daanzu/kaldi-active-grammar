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

## Long-term stress harness

`tests/stress/longterm.py` models extended power-user sessions far beyond the
prolonged test above: one compiler and decoder stay alive while many grammars
(groups of rules, including dictation-bearing rules) are decoded against with
per-utterance activity changes, and are periodically closed and recreated
(exercising rule-ID recycling, FileCache-hit recompilation, and the lazy
compile/load queues), and reloaded in place via `KaldiRule.reload()`. Resource
metrics are sampled at checkpoints after `gc.collect()` and `malloc_trim`:
cross-platform process RSS/HWM and file-descriptor or Windows handle counts
(via `psutil`), thread count, Python object count, live rule and decoder grammar
counts, and tmp-dir/cache disk usage. Per-utterance latency is recorded
throughout. A gated run fails explicitly if required process metrics are not
available; `--allow-missing-process-metrics` is available for diagnostic-only
environments.

A run fails on any recognition mismatch, incomplete workload, or (unless
`--observe`) within-run drift after a discarded warmup window: RSS growth slope
(with a noise floor, since decode-graph working sets wobble), descriptor/handle
growth, Python object growth slope, p95 latency drift (last vs first
post-warmup quarter), RSS failing to return to the post-build baseline after
all rules are closed, or rules failing to release at teardown. Truncation due
to the workload time cap fails the completion gate by default; use
`--allow-truncated` only when a deliberately partial run should pass.

Unexpected setup, compile, decode, and teardown exceptions still trigger
best-effort cleanup and JSON report generation before being re-raised. Both
`--framework both` and the pytest wrappers run every framework case in a fresh
subprocess so allocator state cannot contaminate another measurement.

For performance regression gating, `--max-p95-ms`,
`--max-real-time-factor`, and `--max-prepare-seconds` provide absolute limits.
`--baseline-json` compares p95 latency, real-time factor, and preparation time
with a compatible prior schema-2 report; `--max-baseline-regression-pct`
controls the allowed increase (25% by default). With `--framework both`, pass
the common baseline stem and the runner selects the corresponding
`-agf-direct.json` and `-laf.json` reports.

Run it directly for full knob control (population size, utterance count or
wall-clock cap, activity pattern, churn/reload cadence, utterance mix, seed,
thresholds — see `--help`):

```sh
just stress --profile smoke --framework both
just stress --profile standard --framework agf --json-out report.json
just stress --profile standard --framework agf --baseline-json baseline.json --max-baseline-regression-pct 15
just stress --profile standard --framework agf --max-p95-ms 500 --max-real-time-factor 0.5
just stress --profile overnight --framework laf --max-minutes 480 --observe
```

Or as scripted regression tests through pytest (marked `stress`, excluded by
default; JSON reports land in `tests/.stress_reports/`):

```sh
just test -m stress                # smoke + standard, both frameworks
just test -m stress -k 'smoke'     # quick harness validation only
```

The `standard` profile (12 grammars × 8 rules, 5,000 utterances with churn
every 250, roughly ten minutes per healthy framework) is the intended
regression gate; `smoke` is a minutes-scale end-to-end check; `overnight`
(24 × 10, 200,000 utterances) is for soak testing. Every profile carries a
`--max-minutes` measured-workload cap. A truncated run still reports and runs
all available gates, but it fails completion unless explicitly allowed.
