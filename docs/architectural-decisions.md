# Architectural decisions

A running log of decisions that shape the duorepo and are expensive or confusing
to rediscover — particularly ones where the obvious course was investigated and
rejected. The intent is that a future reader who is about to reopen a settled
question finds the measurement that closed it first.

Decisions about the native engine are recorded here as well as those about the
Python package; the two repositories are developed together, and a decision in
one is rarely legible without the other. See
[kaldi-fork-architecture.md](kaldi-fork-architecture.md) for the structural
description these entries assume.

## Adding an entry

Newest first, under a `## YYYY-MM-DD — <short decision>` heading, with:

- **Status** — Accepted, Superseded by <entry>, or Revisited <date>.
- **Scope** — which repository and subsystem.
- **Context** — what prompted the question.
- **Findings** — what was actually measured or proven, with numbers.
- **Decision** — what was chosen, stated as an instruction to a future maintainer.
- **Consequences** — what this forecloses, and what would justify revisiting.
- **Evidence** — commits, probes, or reports someone could re-run.

Entries are point-in-time records. Do not silently edit an entry once it has
been acted on; add a new one and mark the old `Superseded`.

---

## 2026-08-30 — `ActiveReplaceFstMatcher` stays disabled

**Status:** Accepted
**Scope:** `kaldi-fork-active-grammar`, LAF decoding (`active-replace-fst.h`)

### Context

`ActiveReplaceFst::InitMatcher()` returns `nullptr`, forcing composition onto the
default `SortedMatcher` over the caching arc iterator instead of the non-caching
`ActiveReplaceFstMatcher`. Its comment gives one reason: every visited replace
state must be cached so it carries an activity-volatility flag, which the
compose-layer invalidation predicate reads.

Computing volatility from graph structure instead of from cache contents removes
that stated reason. Restoring the matcher therefore looked like a free win —
stop caching every visited replace state, and both cold expansion and the
working set that thrashes against the 32 MiB replace GC limit should improve.

### Findings

**1. It could not have been enabled as written.** Two latent defects, both
dormant only because the matcher is unreachable:

- `Value()` called `ComputeArc()` and returned `arc_` while discarding the
  boolean. Unlike stock `ReplaceFst`, `ActiveReplaceFst` *deletes* arcs into
  inactive nonterminals — `ComputeArc()` returns false and leaves the output
  untouched. So for a deactivated rule the matcher returned whatever `arc_` held
  from the previous call: a wrong arc, not a missing one, meaning silent
  mis-recognition rather than a clean non-match.
- The exit-recursion arc shared the `arc_` buffer with the component arc.

**2. With those fixed, it buys nothing.** Flat workload, 60 utterances, novel
dictation text, activity churn every utterance:

| Matcher | all median | dictation median | cold dictation | first utt | RSS growth |
|---|---|---|---|---|---|
| Default (`nullptr`) | 0.151 s | 2.968 s | 5.511 s | 10.90 s | +259 MiB |
| `ActiveReplaceFstMatcher` | 0.151 s | 3.167 s | 5.639 s | 11.13 s | +263 MiB |
| + non-forcing `Priority()` | 0.142 s | 3.094 s | 5.651 s | 11.14 s | +262 MiB |

Output was byte-identical in every case. The cold path is marginally *worse* and
the working set is unchanged to within 4 MiB.

**3. The premise was wrong.** The matcher was never what forced replace states
into the cache. `ComposeFstImpl::Expand()` calls `filter_->SetState(s1, s2, fs)`
before any matching happens, and `AltSequenceComposeFilter::SetState()` then
evaluates `NumArcs`, `NumInputEpsilons` and `Final` on the fst2 state — each of
which expands and caches it, whichever matcher is installed.
`ActiveReplaceFstMatcher::Priority()` (inherited from stock `ReplaceFstMatcher`)
is a second forcing call; removing it is the third row above and changes
nothing, which confirms the filter is the binding constraint.

**4. It is actively incompatible with pre-registered rule slots.**
`InitMatchers()` builds one `MultiEpsMatcher` per `fst_array_` entry and inserts
every nonterminal into each one's own label set, copied again on every matcher
`Copy()`. Pre-registration makes `fst_array_` `max_num_rules` long, so startup
goes from **4.77 s / 826 MiB** to **57.35 s / 10.2 GiB** peak resident, scaling
with `max_num_rules`. Correctness survives (reload, remove and id-recycling
checks pass 15/15), so this is a cost rather than a defect.

### Decision

Leave `InitMatcher()` returning `nullptr`. Fix the two `Value()` defects in
place anyway, so the disabled code is not a trap for the next reader of that
comment.

### Consequences

Anything aiming to stop caching every visited replace state must address
`AltSequenceComposeFilter::SetState()`, which is stock OpenFst and on the far
side of the fork boundary — not the matcher. Reopen this entry only if that
call site changes, or if a workload appears in which composition is dominated by
matcher-mediated `Find()` rather than by filter-driven expansion.

The reason originally given in `InitMatcher()`'s comment is still true — the
shipped invalidation predicate does read cache flags — but it is not the reason
the matcher stays disabled, and it stops being true the moment volatility is
derived from graph structure instead. Stated alone it therefore read as a
conditional: remove the dependency and the matcher may return. The comment now
carries both reasons so that reading is no longer available.

### Evidence

- Defect fix: `kaldi-fork-active-grammar` `0ffe2c553`; comment recording this
  decision: `7a02ac636`. Both on `develop`. The defect fix was type-checked via
  a forced explicit template instantiation, since nothing else instantiates the
  matcher and its members are otherwise never compiled.
- Correctness: 200 utterances on a grammar where one exported rule calls another
  with the callee's activity toggled every other utterance — 200/200, output
  byte-identical to the default matcher.
- Measurements were taken behind a temporary `decode_fst_replace_matcher` knob
  (0 = default, 1 = matcher, 2 = matcher with non-forcing `Priority()`), which
  was not committed.

---

## 2026-08-29 — Warm-up is the only tuning lever; beam and cache size are not

**Status:** Accepted — guidance and a bound on alternatives; no code change
**Scope:** `kaldi-active-grammar` + `kaldi-fork-active-grammar`, LAF decoding latency

### Context

LAF dictation decodes run one to two orders of magnitude slower than AGF on the
same audio. Before attributing that to the invalidation predicate, the three
obvious tuning knobs had to be excluded: search width (`beam` / `max_active`),
the lazy-FST cache budget (`decode_fst_cache_size`), and simply decoding a few
utterances before the ones that matter.

### Findings

**1. Warm-up works, and it is not a caching artifact.** 12 measured dictation
utterances, 2 grammars / 2 dictation rules, static activity, a novel dictation
text every utterance:

| Untimed warm-up utts | First measured | Median | Median RTF | RSS at first measurement |
|---|---|---|---|---|
| 0 | 10.449 s | 3.447 s | 1.10 | 1002 MiB |
| 8 | 2.684 s | 2.165 s | 0.725 | 1179 MiB |
| 24 | 1.963 s | 1.622 s | 0.52 | 1355 MiB |

The warm-up texts are drawn from the opposite end of the payload pool from the
measured ones, so no measured utterance is ever a repeat — the gain is graph
expansion that persists across utterances, not a cache hit on the same words.
24 utterances cut the first measured decode 5.3x and the steady-state median
2.1x, and the curve has not flattened at 24. The cost is resident set: roughly
350 MiB of working set is moved earlier, not avoided.

**2. Cache size is not the lever it looks like.** 72 novel dictation utterances,
default 1 GiB versus 128 MiB `decode_fst_cache_size`:

| Cache budget | Median | Peak RSS |
|---|---|---|
| 1 GiB (default) | 1.874 s | 1639 MiB |
| 128 MiB | 1.986 s | 1628 MiB |

An 8x cut in the configured limit made latency 6% *worse* and moved peak
resident set by 11 MiB — 0.7%. Whatever governs the working set, it is not the
compose/arcmap cache budget.

**3. Beam and max-active cannot close the gap.** 24 novel dictation utterances:

| Configuration | Median | Median RTF |
|---|---|---|
| LAF beam 14 / max_active 14000 (default) | 2.372 s | 0.73 |
| LAF beam 11 / max_active 7000 | 2.221 s | 0.675 |
| LAF beam 9 / max_active 4000 | 1.983 s | 0.665 |
| AGF beam 14 (reference) | 0.288 s | 0.09 |

Narrowing beam 14 to 9 and max-active 14000 to 4000 buys 16%, and output stayed
byte-identical across all three LAF settings (0/24 differences). So even
granting the most generous possible assumption — that the narrowing is free —
LAF at its most aggressive remains 6.9x slower than AGF at the *default* beam.
The byte-identical result is on clean synthetic TTS audio; on real speech beam 9
would be expected to cost accuracy, which only strengthens the conclusion.

**4. Cold start is insensitive to both.** The first utterance cost 10.46 s,
10.96 s and 11.05 s across the three beam settings and 10.68 s / 10.91 s across
the two cache budgets. Cold cost is graph construction and expansion; neither
search width nor cache budget touches it.

### Decision

Do not spend further effort tuning `beam`, `max_active`, or
`decode_fst_cache_size` to address LAF dictation latency — the numbers above
bound what is available there, and none of it is close to the size of the
problem. Where LAF must be used with broad dictation, warm the decoder with
disjoint dictation utterances at startup and budget resident set for it.

### Consequences

There is no warm-up facility in the product; `--warmup` exists only in the
probe harness. This entry is therefore a bound on the alternatives and guidance
for whoever builds one, not a description of shipped behavior. Note also the
naming collision: "warm" elsewhere in this repository means the warm dependency
/ file cache, which is unrelated — grepping for it will not find any of this.

Revisit if the actual owner of the working set is identified (finding 2 says it
is not the cache budget, but does not say what it is), or once a warm-up
facility exists and the curve can be pushed past 24 utterances to locate its
plateau.

### Evidence

- Probe `threadB.sh` sections B2/B3/B4 driving `probe.py`, run 2026-08-29;
  results in `b2_default.json`, `b2_small.json`, `b3_w{0,8,24}.json`,
  `b4_{d,m,s,agf}.json`.
- Every LAF row ran with `decode_fst_invalidation_mode: 3`, the
  structural-volatility prototype, which is **not in the tree**. Shipped
  invalidation is slower still, so these bounds are if anything generous to the
  knobs being ruled out.
- Audio is Piper TTS at fixed `length_scale=1.5, noise_scale=0.0,
  noise_w_scale=0.0`, so runs are repeatable and differences are attributable to
  the decoder rather than the audio.
