# TODO

Test CLI path that still uses file-based AGF compilation: python -m kaldi_active_grammar compile_agf_dictation_graph.

## Mac ARM stress-test memory usage

Investigate the high memory usage reported by the Mac ARM stress tests.

- Correct `rss-drain-return`: it currently measures the `drained` sample before
  `compiler.close()`, while the later `closed` sample occurs after compiler
  close and garbage collection. Compare against `closed`; retain `drained` only
  as diagnostic data.
- Do not enforce RSS slope on the 200-utterance smoke profile. Its few
  checkpoints produce unstable regressions. Keep smoke focused on correctness
  and teardown; enforce slope on standard and overnight runs.
- Improve macOS diagnostics before relaxing thresholds. Apple exposes
  `malloc_zone_pressure_relief()` for allocator reclamation and recommends
  `leaks`, malloc stack logging, and Instruments for distinguishing retained
  allocator pages from genuine leaks. See the [libmalloc API](https://github.com/apple-oss-distributions/libmalloc/blob/main/include/malloc/malloc.h)
  and [Apple leak guidance](https://developer.apple.com/library/archive/documentation/Performance/Conceptual/ManagingMemory/Articles/FindingLeaks.html).

## Develop-to-master merge follow-up

- Fix the parser regression in `Compiler.parse_output_for_rule_token`, or
  remove the stale path and update its callers and tests so parser output is
  handled through the supported rule-matching API.
- Add a memory regression test that repeatedly loads and closes real AGF and
  LAF grammars, checking that process memory reaches a stable plateau rather
  than only testing an empty `Compiler` context.
- Correct and enforce the paired Python/native commit metadata and lockstep
  release workflow; record the exact native fork revision used to build and
  test each Python revision.

## LAF grammar FST storage

- Benchmark the private mutable-copy path against conversion to `StdConstFst` with
  representative small, medium, and large grammars. Record add/reload latency,
  steady-state native memory, and decode throughput.
- Decide whether freezing should be selectable, rather than unconditional. A
  possible API is a decoder/model construction option with `auto` (default),
  `mutable`, and `frozen` modes.
- If an option is added, document that it changes only the LAF-owned copy: the
  Python `NativeWFST` remains Python-owned and is never mutated or transferred.
- Keep the default based on measurements: favor frozen FSTs for load-once,
  decode-many grammars only if their memory/locality benefit outweighs conversion
  cost; otherwise retain a private `StdVectorFst` copy.
- Add regression coverage for adding, removing, and reloading a grammar while
  the original Python-owned `NativeWFST` is subsequently destroyed.

## LAF lexicon updates

- Provide a supported full LAF graph rebuild workflow for adding words or
  pronunciations. It must regenerate `HCLr.fst`, `Gr.fst`,
  `relabel_ilabels.int`, and `words.relabeled.txt` together; runtime updates
  are deliberately rejected until that workflow exists.
