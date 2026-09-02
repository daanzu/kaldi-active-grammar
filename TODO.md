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

- Fix LAF direct mimic, which currently does not match ordinary rules whose
  input labels use the relabeled-word table.
- Add a memory regression test that repeatedly loads and closes real AGF and
  LAF grammars, checking that process memory reaches a stable plateau rather
  than only testing an empty `Compiler` context.
- Correct and enforce the paired Python/native commit metadata and lockstep
  release workflow; record the exact native fork revision used to build and
  test each Python revision.

## AGF activity-update scaling

Nested activity invalidation is now correct, but each changed activity set scans
all cached expanded states across every FST instance, filtering for user-call
boundaries. This costs O(all cached expanded states) per change.

- Measure activity-update cost on large, deeply nested grammar caches.
- If material, replace the scan with either a reverse index from destination
  ifst to cached user-call boundaries, or activity-independent cached topology
  gated when arcs are read. Preserve unconditional `#nonterm_end` returns.

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

## LAF dictation call-site duplication

_Measured 2026-08-29._

`ReplaceFst` interns the return stack into the state tuple
(`prefix_id`, `fst_id`, `fst_state`), so a sub-FST reached from several call
sites gets a disjoint set of state ids per site. `ActiveComposeFst` keys on
those ids, so the whole `HCLr`-composed sub-graph is expanded, computed, and
cached once per call site. The return address affects no arc inside the
sub-FST; it matters only on the arc leaving it, so the repeated work is
entirely redundant.

- Measured with seven `<word> <dictation>` rules, all active on every
  utterance (so grammar activity never changes): 963,386 composition states in
  the dictation region against 194,551 distinct (`HCLr` state, `Gr.fst` state)
  pairs, i.e. **4.87x duplication**, still climbing toward its ceiling of 7.
  Compose-filter multiplicity over the same states is 1.017, so nothing else
  contributes. Reproduce by decoding the same dictation text through two
  different rules with static activity: the second pays the full cold cost
  again (10.6 s vs 0.17 s warm).
- This is independent of the invalidation-predicate and grammar-teardown
  defects; fixing either leaves it intact. It was previously masked by them
  because the symptom is identical.
- The axis is neither dictation-versus-command nor exported-versus-non-exported.
  `PushPrefix` interns the whole return stack, not just the immediate return, so
  a sub-FST is duplicated once per distinct call *path* that reaches it. Being
  exported only decides whether the top FST is one of those paths: an exported
  rule also referenced from two other rules has three, which is worse than the
  equivalent non-exported rule referenced twice. Nesting therefore multiplies
  rather than adds — a shared leaf reached through two levels of sharing gets one
  copy per path through both. Only a sub-FST with a single call path measures
  1.00.
- Measured with a 300-alternative non-exported callee referenced by four parents,
  one of them twice, so five call sites: **2.82x**, five prefixes, 2,883
  composition states against 972 needed. It reaches 2.20x after a single
  utterance, because every call site is touched while all rules are active. The
  four parents each measure 1.00, being top-called only.
- Both consequences of the path rule are now measured, and the predicted prefix
  counts came out exact. A 300-alternative **exported** callee also referenced by
  two other rules: **3 prefixes** (top, plus each referrer), **2.82x**, 1,370
  composition states against 485 needed — being exported confers no protection
  once a rule is referenced. Two-level nesting, with a non-exported `MID`
  referenced by two parents that itself calls a non-exported `LEAF` twice: `MID`
  gets **2 prefixes** (1.75x), and `LEAF` gets **4** — the product, not the sum —
  at **2.73x**, 2,873 states against 968. Every rule with a single call path
  measured 1.00 in the same run.
- That instance is cheap in absolute terms (~1,900 wasted states, no
  measurable latency), but it scales with callee size times reference count, so
  a large shared list referenced by many commands is worth re-measuring. The
  dictation case is ~400x larger in wasted states.
- No fix is possible without changing the state key, which `ReplaceFst` and
  `ComposeFst` do not allow. Evaluate a purpose-built lazy FST that interns the
  shared expansion on (`HCLr` state, `fst_id`, `fst_state`) and carries the
  return context outside that key, in the manner of `ActiveGrammarFst`'s
  instance tags. The depth-1 result for this composition bounds the states
  needing per-call-site correction to sub-FST exits plus their immediate
  predecessors.
- Diagnostics: a census that walks the composition state table (monotonic, so
  it counts work done rather than what survived GC) and decodes each `s2`
  through the replace-layer state table gives these counts directly. Note that
  the native log handler drops everything above `kWarning`, so such
  diagnostics must use `KALDI_WARN` to appear at all.

## LAF activity for non-exported rules

_Raised 2026-08-29; partial probe 2026-08-30._

- Verify whether the Dragonfly front-end includes non-exported rule IDs in the
  activity list. `LafNNet3OnlineModelWrapper` builds
  `grammars_activity_by_label` only from caller-provided IDs, and
  `ActiveReplaceFst::UpdateActivity` marks only those IDs active. A non-exported
  rule omitted from the list is therefore inactive, so `ComputeArc` drops call
  arcs into it; nested non-exported rules would then never match under LAF.
  The size guard (`> max_num_exported_rules`) allows such IDs, but the caller
  has not yet been checked. Existing nested probes use exported callees and do
  not cover this case.
- Partially probed only: creating a non-exported rule (id 1000, above
  `max_num_exported_rules`) left a pre-existing exported rule still matching, in
  both the shipped and structural-invalidation arms. That shows the id range does
  not break unrelated rules; it does **not** exercise a non-exported rule being
  *called* from another rule, which is the case at risk. A probe needs a parent
  rule referencing a non-exported callee, with the callee expected to match.

## LAF compose-cache invalidation predicate

_Measured 2026-08-29._

`ActiveComposeFst::IsActivityDependent` (`active-compose-fst.h:106-111`) decides
whether a cached composition state survives an activity change by asking whether
the corresponding replace-layer state is *present in the replace cache* and
carries a volatility flag. Beam search leaves a huge unexpanded frontier, so
almost every successor is absent, and absence is read as "may depend on
activity". Measured: 99.7% of deleted compose states die from that clause, while
genuinely activity-volatile states number 5-44 per change (0.1-0.3%). Raising the
replace GC limit to 8 GiB left `succ_missing` flat and drove `self_missing` to
zero, proving the successors were never expanded rather than GC-evicted.

- Compute volatility from graph structure instead: test the tuple
  (`prefix_id`, `fst_id`, `fst_state`) against a precomputed per-sub-FST bitset
  of states with nonterminal-calling arcs. A state's only activity-varying
  property is its exposed arc set, since `ComputeArc` drops arcs into inactive
  nonterminals; final weight and return-arc structure are activity-independent.
- **Do not** instead relax the predicate so cache absence is never evidence of
  dependence. That was the round-1 candidate and it is only accidentally correct:
  it fails as soon as a compose cache entry outlives the replace state it was
  derived from, which is exactly what happens once grammar add/remove stops
  rebuilding the graph (see the teardown item below).
- Check successors to depth 1 — no more, no less. Composition reads the replace
  layer at exactly one arc-step past `s2`, via
  `LookAheadComposeFilter::LookAheadFilterArc` calling `LookAheadFst(fst2,
  arcb->nextstate)`, which only iterates that state's arcs and final weight.
  Label pushing writes a depth-2 state *id* into the cached arc but reads nothing
  there. Deleting the successor clause (depth 0) wrongly keeps 319 of 872
  activity-dependent states on the nested probe; extending to depth 2 adds 39
  deletions that provably cannot matter. Depth 1 costs 0.013% of the cache.
- Enumerate successors as internal arcs plus the return arc
  (`PopPrefix(stack)`, `top.fst_id`, `top.nextstate`) from `ComputeFinalArc`.
  Call successors need no check: such a state is itself volatile.
- Justify the work by the right baseline. The shipped incremental path is only
  4.6% faster than clearing the whole cache (5.752 s vs 6.032 s per activity
  change); the structural predicate is 0.149 s. Incremental invalidation
  currently buys essentially nothing.
- The prototype exists only as `laf-round3-full-prototype.patch` in the session
  scratchpad and applies to `033fbe43e` alone; rebase it onto `develop` before
  reusing it. It carries the `decode_fst_invalidation_mode` knob
  (0 = shipped, 1/2 = relaxations, 3/4/5 = structural at depth 1/0/2), which was
  deliberately not committed.
- Raise or expose `active_replace_options.gc_limit`, hardcoded to `1ULL<<25`
  (32 MiB) at `laf-sub-nnet3.cc:256` while compose and arcmap get 1 GiB. The
  replace cache therefore evicts continuously underneath the compose cache. This
  is a secondary cause, not the main one — raising it alone does not fix the
  pathology.

## LAF grammar add/remove tears down the whole decode FST

_Measured 2026-08-29; pre-registration startup cost 2026-08-30._

`AddGrammarFst`, `ReloadGrammarFst` and `RemoveGrammarFst` all call
`InvalidateDecodeFst()`, which destroys all three lazy FSTs. With the
invalidation fix applied *and* static activity, creating and closing one rule
every three utterances restores the full pathology on its own.

- Pre-register all `max_num_rules` nonterminal slots against a shared empty
  placeholder FST so that add and remove swap a pointer. An inactive rule can
  have no cached dependents, so no invalidation is needed at all.
- Pre-registration must span the full `max_num_rules` (10000), not just the
  exported range: non-exported rule ids start at `max_num_exported_rules`, so a
  partial span drops them.
- Measured cost of the prototype at full span: startup 4.77 s / 826 MiB peak
  resident. Correctness held across reload, remove and id-recycling checks
  (15/15).
- Note the hard constraint recorded in
  `docs/architectural-decisions.md` (2026-08-30): pre-registration is
  incompatible with enabling `ActiveReplaceFstMatcher`, which would take the same
  startup to 57.35 s / 10.2 GiB.

## `decode_fst_naive` ignores activity for nested rules

_Found 2026-08-29._

`BuildDecodeFstNaive` adds a top-FST arc only for rules in `grammars_activity_`,
but registers *every* entry of `grammar_fsts_` in `label_fst_pairs`. A
nonterminal called from inside another rule therefore resolves regardless of its
activity. On a nested grammar the naive path matched the caller in 100 of 200
utterances where the callee was deactivated; every active-path mode passed
200/200.

- Fix the naive path to filter `label_fst_pairs` by activity, or document it as a
  structural baseline that is not activity-correct.
- Until then, do not use `decode_fst_naive` as a correctness oracle despite the
  name. The correct reference is `decode_fst_incremental: false`.
- End-to-end differential testing cannot validate an invalidation predicate at
  all: a deliberately unsound depth-0 predicate scores identically to the sound
  one, because the call-site state is volatile under every depth, so a stale arc
  leads into an already-corrected state and the path dies one step later. Use a
  structural census over the composition state table instead. The census needs
  `FLAGS_v` set, since fst-layer logging is OpenFst's `VLOG` rather than Kaldi
  verbosity.

## LAF replace-state caching

_Settled 2026-08-30; residual lookahead profile 2026-08-29._

Reducing how much of the replace layer gets cached cannot be done at the matcher;
`ActiveReplaceFst::InitMatcher()` stays returning `nullptr`. Full measurements
and rationale are in `docs/architectural-decisions.md` (2026-08-30).

- The binding constraint is `AltSequenceComposeFilter::SetState`, which evaluates
  `NumArcs`, `NumInputEpsilons` and `Final` on the fst2 state before any matching
  happens, expanding and caching it whichever matcher is installed. That call
  site is stock OpenFst, on the far side of the fork boundary.
- Investigate the residual lookahead cost separately. With both fixes above
  applied and novel dictation text every utterance, LAF still costs 1.9-10.5 s
  and decays only slowly, while AGF stays flat at 0.27 s. gdb sampling put 35 of
  40 samples in `LabelLookAheadMatcher::LookAheadFst` → `LabelReachable::Reach` →
  `FastLogAccumulator` → `log`/`exp`; the `kLookAheadWeight` bit in the
  `StdOLabelLookAheadFst` flags (1760u) is what pays for it.

## LAF decoder warm-up

_Measured 2026-08-29._

Warm-up is the only tuning lever that works; beam, max-active and
`decode_fst_cache_size` are bounded and cannot close the gap to AGF. Numbers are
in `docs/architectural-decisions.md` (2026-08-29).

- Provide a supported warm-up entry point that decodes throwaway dictation
  utterances at startup. Today `--warmup` exists only in the probe harness, and
  the word "warm" elsewhere in this repository refers to the warm dependency
  cache, so nothing in the codebase implements or documents this.
- Budget resident set for it: 24 warm-up utterances moved roughly 350 MiB of
  working set earlier (it is front-loaded, not avoided).
- Re-measure past 24 utterances once such a facility exists — the latency curve
  had not flattened there, so the plateau is still unlocated.
- Identify what actually governs the working set. Cutting
  `decode_fst_cache_size` 8x (1 GiB to 128 MiB) moved peak RSS by 11 MiB (0.7%)
  while making latency 6% worse, so it is not the cache budget.

## LAF accuracy has never been measured

_Filed 2026-08-30; not yet measured._

Every LAF/AGF comparison so far is latency and memory only. Correctness checks
were exact-match against expected transcripts on clean synthetic TTS audio, which
is not a WER measurement.

- Measure LAF and AGF word error rate on the same real-speech corpus, with
  matched beam settings.
- This decides the framework positioning question. LAF is 8.2x slower than AGF on
  dictation at default beam and still 6.9x slower at its most aggressive setting;
  if it also carries no accuracy advantage, there is no dictation-breadth
  threshold at which LAF is the right recommendation and the guidance can simply
  say so.
- Note that beam 14 → 9 and max-active 14000 → 4000 produced byte-identical
  output on 24 synthetic dictation utterances. That is a property of clean TTS
  audio and should not be read as evidence that the narrow beam is safe on real
  speech.
