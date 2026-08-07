"""Long-term stress harness modeling extended power-user sessions.

One Compiler and one decoder stay alive for the whole run while many grammars
(each a group of rules) are decoded against, activated/deactivated per
utterance, and periodically closed, recreated (with recycled rule IDs and
FileCache hits), and reloaded in place.  Resource metrics are sampled at
checkpoints and the run fails on within-run drift (RSS slope, fd growth,
latency drift) or any recognition error, making it usable both as an
interactive soak test and as a scripted regression gate.

Run directly for full knob control (see ``--help``)::

    .venv/bin/python tests/stress/longterm.py --profile smoke --framework agf
    .venv/bin/python tests/stress/longterm.py --profile standard --framework both --json-out report.json

or through pytest (see ``tests/test_stress_longterm.py``)::

    just test -m stress

The harness assumes the test Kaldi model in ``tests/kaldi_model`` and the
Piper voice used by the rest of the test suite (``just setup-tests``).
"""

from __future__ import annotations

import argparse
import ctypes
import dataclasses
import gc
import json
import math
import os
import platform
import random
import sys
import threading
import time
import weakref
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parents[1]

LAF_MODEL_FILES = (
    'HCLr.fst', 'Gr.fst', 'disambig_tid.int',
    'relabel_ilabels.int', 'words.relabeled.txt',
)

# All words below are known-good in the test model's lexicon (they are already
# exercised by the regular grammar tests).  The universe must stay unambiguous:
# each phrase is unique, and dictation payload words never appear in it.
VERBS = ('go', 'move', 'turn')
DIRECTIONS = ('left', 'right', 'forward', 'back', 'north', 'south', 'east', 'west')
NUMBERS = ('one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten')
# No empty payload: trailing-audio decoding of a zero-word dictation span is
# not reliable enough for a correctness-gated bulk run.
DICTATION_PAYLOADS = ('hello world', 'hello')


def build_phrase_universe():
    universe = [f'{verb} {direction}' for verb in VERBS for direction in DIRECTIONS]
    universe += [f'{verb} {direction} {number}'
                 for verb in VERBS for direction in DIRECTIONS for number in NUMBERS]
    universe += [f'{direction} {number}' for direction in DIRECTIONS for number in NUMBERS]
    universe += [f'{number} {verb} {direction}'
                 for number in NUMBERS for verb in VERBS for direction in DIRECTIONS]
    return universe


def missing_laf_model_files(model_dir=None):
    model_dir = Path(model_dir) if model_dir else (TESTS_DIR / 'kaldi_model')
    return [name for name in LAF_MODEL_FILES if not (model_dir / name).is_file()]


@dataclasses.dataclass
class StressConfig:
    framework: str = 'agf-direct'       # 'agf-direct' or 'laf'
    utterances: int = 2000              # target utterance count
    max_minutes: float = 0.0            # wall-clock cap; 0 disables
    num_grammars: int = 12
    rules_per_grammar: int = 8
    dictation_rules_per_grammar: int = 1

    decode_mode: str = 'audio'          # 'audio' (real decode) or 'mimic' (text-only graph exercise)
    activity_pattern: str = 'bursty'    # 'bursty', 'random', or 'cycling'
    active_grammar_fraction: float = 0.35
    context_switch_prob: float = 0.05   # bursty: full active-set resample probability
    context_drift_prob: float = 0.10    # bursty: single-grammar swap probability
    empty_activity_fraction: float = 0.02
    garbage_audio_fraction: float = 0.02

    churn_every: int = 250              # close+recreate grammars every N utterances; 0 disables
    churn_fraction: float = 0.25        # fraction of grammars churned per cycle
    novel_fraction: float = 0.5         # churned grammars rebuilt with new phrases (vs cache-hit identical)
    phrase_pool_factor: float = 2.0     # command-phrase pool size as a multiple of live command rules
    reload_every: int = 400             # in-place rule reload() every N utterances; 0 disables
    lazy_fraction: float = 0.5          # rules using lazy compile/load queues

    seed: int = 2026
    checkpoint_every: int = 100
    report_every: int = 200
    warmup_fraction: float = 0.25       # leading fraction of run excluded from drift analysis
    max_failures: int = 25              # abort the run after this many recognition failures

    observe_only: bool = False          # collect and report, but never fail on drift verdicts
    max_rss_slope_kib_per_1k: float = 512.0
    rss_noise_floor_kib: float = 4096.0  # ignore slope when net post-warmup growth is under allocator jitter
    max_fd_growth: int = 5
    max_latency_drift_pct: float = 75.0
    max_gc_objects_slope_per_1k: float = 2000.0

    json_out: str = ''
    label: str = ''

    def validate(self):
        if self.framework not in ('agf-direct', 'agf', 'laf'):
            raise ValueError('framework must be agf-direct or laf')
        if self.decode_mode not in ('audio', 'mimic'):
            raise ValueError('decode_mode must be audio or mimic')
        if self.activity_pattern not in ('bursty', 'random', 'cycling'):
            raise ValueError('unknown activity_pattern %r' % self.activity_pattern)
        if not (0 <= self.dictation_rules_per_grammar <= self.rules_per_grammar):
            raise ValueError('dictation_rules_per_grammar out of range')
        if self.phrase_pool_factor < 1.5:
            raise ValueError('phrase_pool_factor must be at least 1.5 so churn can find free phrases')
        universe_size = len(build_phrase_universe())
        if self.command_pool_size + self.reserved_dictation_phrases > universe_size:
            raise ValueError('rule population too large for %d-phrase universe' % universe_size)

    @property
    def live_command_rules(self):
        return self.num_grammars * (self.rules_per_grammar - self.dictation_rules_per_grammar)

    @property
    def reserved_dictation_phrases(self):
        return self.num_grammars * self.dictation_rules_per_grammar

    @property
    def command_pool_size(self):
        return int(math.ceil(self.live_command_rules * self.phrase_pool_factor))


PROFILES = {
    'smoke': dict(
        utterances=200, num_grammars=4, rules_per_grammar=4,
        churn_every=50, reload_every=70, checkpoint_every=20, report_every=50,
        active_grammar_fraction=0.5, max_minutes=10.0,
    ),
    'standard': dict(
        utterances=5000, num_grammars=12, rules_per_grammar=8,
        churn_every=250, reload_every=400, checkpoint_every=100, report_every=250,
        max_minutes=30.0,
    ),
    'overnight': dict(
        utterances=200000, num_grammars=24, rules_per_grammar=10,
        churn_every=200, reload_every=300, checkpoint_every=200, report_every=1000,
        max_minutes=600.0,
    ),
}


def percentile(values, pct):
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (pct / 100.0) * (len(ordered) - 1)
    low = int(math.floor(rank))
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (rank - low)


def linear_slope(xs, ys):
    """Least-squares slope of ys against xs; None with fewer than 4 points."""
    if len(xs) < 4:
        return None
    n = float(len(xs))
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    denominator = sum((x - mean_x) ** 2 for x in xs)
    if denominator == 0:
        return None
    return sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / denominator


def read_proc_status_kib(field):
    try:
        with open('/proc/self/status') as status:
            for line in status:
                if line.startswith(field + ':'):
                    return int(line.split()[1])
    except OSError:
        return None
    return None


def count_open_fds():
    try:
        return len(os.listdir('/proc/self/fd'))
    except OSError:
        return None


def malloc_trim():
    if sys.platform.startswith('linux'):
        try:
            ctypes.CDLL(None).malloc_trim(0)
        except (OSError, AttributeError):
            pass


def directory_stats(path):
    total_bytes = 0
    total_files = 0
    try:
        for entry in Path(path).iterdir():
            if entry.is_file():
                total_files += 1
                total_bytes += entry.stat().st_size
    except OSError:
        return None, None
    return total_files, total_bytes // 1024


def load_piper_voice():
    import piper
    model_name = os.environ.get('PIPER_MODEL', 'en_US-ryan-low.onnx')
    model_path = TESTS_DIR / model_name
    if not model_path.is_file():
        raise FileNotFoundError(f"Piper model file '{model_path}' not found; run 'just setup-tests'.")
    return piper.PiperVoice.load(model_path)


class AudioPool:
    """Synthesize each distinct text once with deterministic Piper settings."""

    def __init__(self, piper_voice):
        import piper
        self.voice = piper_voice
        self.syn_config = piper.SynthesisConfig(
            length_scale=1.5, noise_scale=0.0, noise_w_scale=0.0)
        self.cache = {}
        self.synth_calls = 0
        self.synth_seconds = 0.0

    def get(self, text):
        audio = self.cache.get(text)
        if audio is None:
            started = time.monotonic()
            audio = b''.join(chunk.audio_int16_bytes
                             for chunk in self.voice.synthesize(text, syn_config=self.syn_config))
            self.synth_seconds += time.monotonic() - started
            self.synth_calls += 1
            self.cache[text] = audio
        return audio


@dataclasses.dataclass
class StressRule:
    rule: object                        # KaldiRule
    phrase_index: int
    text: str                           # spoken text for this rule
    expected_words: list
    expected_mask: list
    is_dictation: bool


@dataclasses.dataclass
class StressGrammar:
    index: int
    generation: int
    rules: list                         # list[StressRule]


class LongTermStressSession:
    """One framework's stress run; assumes cwd contains ``kaldi_model``."""

    def __init__(self, config, piper_voice=None, log=None):
        config.validate()
        self.config = config
        self.log = log if log is not None else (lambda message: print(message, flush=True))
        self.rng = random.Random(config.seed)
        self.universe = build_phrase_universe()
        self.piper_voice = piper_voice

        self.compiler = None
        self.decoder = None
        self.audio_pool = None
        self.grammars = []
        # Command rules draw phrases from a bounded pool so the audio cache,
        # FileCache, and tmp dir all saturate early; post-warmup resource
        # samples then measure the package, not TTS or first-compile costs.
        # Dictation rules use dedicated phrases from the end of the universe,
        # fixed per grammar slot, so their texts are pre-synthesizable too.
        self.free_phrase_indices = list(range(config.command_pool_size))
        self.dictation_phrase_base = len(self.universe) - config.reserved_dictation_phrases
        self.rule_refs = []             # weakrefs to every KaldiRule ever created
        self.active_grammar_indices = set()

        self.checkpoints = []
        self.latencies = []             # (utterance_index, seconds)
        self.audio_seconds_decoded = 0.0
        self.failures = []
        self.counters = dict(
            utterances=0, valid_utterances=0, garbage_utterances=0,
            empty_activity_utterances=0, dictation_utterances=0,
            churn_cycles=0, rules_created=0, rules_closed=0,
            identical_recreations=0, novel_recreations=0, reloads=0,
            prepare_calls=0,
        )
        self.prepare_seconds = 0.0
        self.truncated = False
        self.started_at = None

    # ----- population management -------------------------------------------------

    def _take_phrase(self):
        return self.free_phrase_indices.pop(0)

    def _return_phrase(self, index):
        self.free_phrase_indices.append(index)

    def _build_command_fst(self, fst, words):
        states = [fst.add_state(initial=True)]
        states.extend(fst.add_state() for _ in words[:-1])
        states.append(fst.add_state(final=True))
        for position, word in enumerate(words):
            fst.add_arc(states[position], states[position + 1], word)

    def _build_dictation_fst(self, fst, lead_words):
        state = fst.add_state(initial=True)
        for word in lead_words + ['dictate']:
            next_state = fst.add_state()
            fst.add_arc(state, next_state, word)
            state = next_state
        dictation_state = fst.add_state()
        end_state = fst.add_state()
        final_state = fst.add_state(final=True)
        fst.add_arc(state, dictation_state, '#nonterm:dictation')
        fst.add_arc(dictation_state, end_state, None, '#nonterm:end')
        fst.add_arc(end_state, final_state, None)

    def _dictation_slot(self, grammar_index, rule_index):
        """Fixed lead phrase and payload for a grammar's dictation-rule slot."""
        slot = grammar_index * self.config.dictation_rules_per_grammar + rule_index
        phrase_index = self.dictation_phrase_base + slot
        payload = DICTATION_PAYLOADS[slot % len(DICTATION_PAYLOADS)]
        return phrase_index, payload

    def _create_rule(self, grammar_index, rule_index, generation, phrase_index,
                     is_dictation, payload, lazy):
        from kaldi_active_grammar import KaldiRule
        lead_words = self.universe[phrase_index].split()
        name = f'Stress_g{grammar_index}_r{rule_index}_gen{generation}'
        rule = KaldiRule(self.compiler, name, has_dictation=is_dictation or None)
        if is_dictation:
            self._build_dictation_fst(rule.fst, lead_words)
            payload_words = payload.split()
            text = ' '.join(lead_words + ['dictate'] + payload_words)
            expected_words = lead_words + ['dictate'] + payload_words
            expected_mask = [False] * (len(lead_words) + 1) + [True] * len(payload_words)
        else:
            self._build_command_fst(rule.fst, lead_words)
            text = ' '.join(lead_words)
            expected_words = list(lead_words)
            expected_mask = [False] * len(lead_words)
        rule.compile(lazy=lazy)
        rule.load(lazy=lazy)
        self.rule_refs.append(weakref.ref(rule))
        self.counters['rules_created'] += 1
        return StressRule(rule=rule, phrase_index=phrase_index, text=text,
                          expected_words=expected_words, expected_mask=expected_mask,
                          is_dictation=is_dictation)

    def _create_grammar(self, grammar_index, generation, phrase_indices=None):
        config = self.config
        rules = []
        for rule_index in range(config.rules_per_grammar):
            is_dictation = rule_index < config.dictation_rules_per_grammar
            if is_dictation:
                phrase_index, payload = self._dictation_slot(grammar_index, rule_index)
            elif phrase_indices is not None:
                phrase_index, payload = phrase_indices[rule_index], None
            else:
                phrase_index, payload = self._take_phrase(), None
            lazy = self.rng.random() < config.lazy_fraction
            rules.append(self._create_rule(grammar_index, rule_index, generation,
                                           phrase_index, is_dictation, payload, lazy))
        return StressGrammar(index=grammar_index, generation=generation, rules=rules)

    def _presynthesize_audio(self):
        """Synthesize every text this run can ever speak, before measurement starts."""
        for phrase_index in range(self.config.command_pool_size):
            self.audio_pool.get(self.universe[phrase_index])
        for grammar_index in range(self.config.num_grammars):
            for rule_index in range(self.config.dictation_rules_per_grammar):
                phrase_index, payload = self._dictation_slot(grammar_index, rule_index)
                lead_words = self.universe[phrase_index].split()
                self.audio_pool.get(' '.join(lead_words + ['dictate'] + payload.split()))

    def _prepare_for_recognition(self):
        started = time.monotonic()
        self.compiler.prepare_for_recognition()
        self.prepare_seconds += time.monotonic() - started
        self.counters['prepare_calls'] += 1

    def _close_grammar(self, grammar):
        for stress_rule in grammar.rules:
            stress_rule.rule.close()
            self.counters['rules_closed'] += 1

    def _churn(self, utterance_index):
        config = self.config
        victim_count = max(1, round(config.churn_fraction * config.num_grammars))
        victims = self.rng.sample(range(config.num_grammars), victim_count)
        for grammar_index in victims:
            grammar = self.grammars[grammar_index]
            old_phrases = [stress_rule.phrase_index for stress_rule in grammar.rules]
            command_phrases = [stress_rule.phrase_index for stress_rule in grammar.rules
                               if not stress_rule.is_dictation]
            self._close_grammar(grammar)
            novel = self.rng.random() < config.novel_fraction
            if novel:
                for phrase_index in command_phrases:
                    self._return_phrase(phrase_index)
                replacement = self._create_grammar(grammar_index, grammar.generation + 1)
                self.counters['novel_recreations'] += 1
            else:
                # Same phrases and content: exercises FileCache hits and rule-ID reuse.
                replacement = self._create_grammar(grammar_index, grammar.generation + 1,
                                                   phrase_indices=old_phrases)
                self.counters['identical_recreations'] += 1
            self.grammars[grammar_index] = replacement
        self._prepare_for_recognition()
        self.counters['churn_cycles'] += 1

    def _reload_one_rule(self):
        candidates = [stress_rule for grammar in self.grammars
                      for stress_rule in grammar.rules if not stress_rule.is_dictation]
        if not candidates:
            return
        stress_rule = self.rng.choice(candidates)
        new_phrase_index = self._take_phrase()
        self._return_phrase(stress_rule.phrase_index)
        words = self.universe[new_phrase_index].split()
        with stress_rule.rule.reload():
            self._build_command_fst(stress_rule.rule.fst, words)
            stress_rule.rule.compile()
        stress_rule.phrase_index = new_phrase_index
        stress_rule.text = ' '.join(words)
        stress_rule.expected_words = list(words)
        stress_rule.expected_mask = [False] * len(words)
        self.counters['reloads'] += 1

    # ----- activity selection ----------------------------------------------------

    def _coprime_stride(self, count, start):
        stride = start
        while math.gcd(stride, count) != 1:
            stride += 1
        return stride

    def _select_active_grammars(self, utterance_index):
        config = self.config
        grammar_count = config.num_grammars
        if config.activity_pattern == 'cycling':
            first = (utterance_index * self._coprime_stride(grammar_count, 7)) % grammar_count
            count = 1 + utterance_index % grammar_count
            step = self._coprime_stride(grammar_count, 5)
            self.active_grammar_indices = {(first + offset * step) % grammar_count
                                           for offset in range(count)}
        elif config.activity_pattern == 'random':
            count = self.rng.randint(1, grammar_count)
            self.active_grammar_indices = set(self.rng.sample(range(grammar_count), count))
        else:  # bursty
            target_size = max(1, round(config.active_grammar_fraction * grammar_count))
            if not self.active_grammar_indices or self.rng.random() < config.context_switch_prob:
                self.active_grammar_indices = set(self.rng.sample(range(grammar_count), target_size))
            elif self.rng.random() < config.context_drift_prob:
                inactive = list(set(range(grammar_count)) - self.active_grammar_indices)
                if inactive:
                    self.active_grammar_indices.add(self.rng.choice(inactive))
                if len(self.active_grammar_indices) > 1:
                    self.active_grammar_indices.discard(
                        self.rng.choice(sorted(self.active_grammar_indices)))
        return sorted(self.active_grammar_indices)

    # ----- decode + validation ---------------------------------------------------

    def _garbage_audio(self):
        garbage_rng = random.Random(42)
        return bytes(garbage_rng.randint(0, 255) for _ in range(32768))

    def _record_failure(self, utterance_index, kind, expected, got):
        self.failures.append(dict(utterance=utterance_index, kind=kind,
                                  expected=str(expected), got=str(got)))
        self.log('FAILURE at utterance %d (%s): expected %s, got %s'
                 % (utterance_index, kind, expected, got))

    def _decode_and_validate(self, utterance_index, text_or_audio, active_rule_ids,
                             expected_rule, expected_words, expected_mask, kind):
        started = time.monotonic()
        if self.config.decode_mode == 'mimic':
            output = self.decoder.mimic(text_or_audio, active_rule_ids)
            output = output if output is not False else ''
        else:
            self.decoder.decode(text_or_audio, True, active_rule_ids)
            output, info = self.decoder.get_output()
            self.audio_seconds_decoded += len(text_or_audio) / (2.0 * 16000.0)
        recognized_rule, words, mask = self.compiler.parse_output(output)
        elapsed = time.monotonic() - started
        self.latencies.append((utterance_index, elapsed))

        if expected_rule is None:
            if recognized_rule is not None:
                self._record_failure(utterance_index, kind, 'no recognition',
                                     '%r -> %r' % (recognized_rule, words))
        else:
            if recognized_rule is not expected_rule:
                self._record_failure(utterance_index, kind, expected_rule, recognized_rule)
            elif words != expected_words or mask != expected_mask:
                self._record_failure(utterance_index, kind,
                                     (expected_words, expected_mask), (words, mask))

    def _run_one_utterance(self, utterance_index):
        config = self.config
        active_indices = self._select_active_grammars(utterance_index)
        active_rules = [stress_rule for grammar_index in active_indices
                        for stress_rule in self.grammars[grammar_index].rules]
        active_rule_ids = [stress_rule.rule.id for stress_rule in active_rules]
        self._last_active_count = len(active_rule_ids)

        roll = self.rng.random()
        garbage_cutoff = config.garbage_audio_fraction if config.decode_mode == 'audio' else 0.0
        if roll < garbage_cutoff:
            self.counters['garbage_utterances'] += 1
            self._decode_and_validate(utterance_index, self._garbage_bytes, active_rule_ids,
                                      None, None, None, 'garbage-audio')
            return
        if roll < garbage_cutoff + config.empty_activity_fraction:
            self.counters['empty_activity_utterances'] += 1
            victim = self.rng.choice(active_rules)
            payload = (victim.text if config.decode_mode == 'mimic'
                       else self.audio_pool.get(victim.text))
            self._decode_and_validate(utterance_index, payload, [],
                                      None, None, None, 'empty-activity')
            return

        candidates = ([stress_rule for stress_rule in active_rules if not stress_rule.is_dictation]
                      if config.decode_mode == 'mimic' else active_rules)
        target = self.rng.choice(candidates)
        if target.is_dictation:
            self.counters['dictation_utterances'] += 1
        self.counters['valid_utterances'] += 1
        payload = (target.text if config.decode_mode == 'mimic'
                   else self.audio_pool.get(target.text))
        self._decode_and_validate(utterance_index, payload, active_rule_ids,
                                  target.rule, target.expected_words, target.expected_mask,
                                  'dictation' if target.is_dictation else 'command')

    def _log_alive_rule_referrers(self):
        """Name the reference chains keeping supposedly-dead KaldiRule objects alive."""
        for reference in self.rule_refs:
            rule = reference()
            if rule is None:
                continue
            chain = []
            current = rule
            seen = set()
            for _ in range(6):
                referrers = [referrer for referrer in gc.get_referrers(current)
                             if id(referrer) not in seen
                             and type(referrer).__name__ not in ('frame', 'list_iterator')
                             and referrer is not self.rule_refs and referrer is not chain]
                if not referrers:
                    break
                current = referrers[0]
                seen.add(id(current))
                description = type(current).__name__
                if isinstance(current, dict):
                    keys = [key for key, value in current.items()
                            if value is chain or True][:6]
                    description += str(keys)
                chain.append(description)
            self.log('  alive: %r held via %s' % (rule, ' <- '.join(chain)))

    # ----- metrics ---------------------------------------------------------------

    def _sample(self, phase, utterance_index):
        gc.collect()
        malloc_trim()
        checkpoint = dict(
            phase=phase,
            utterance=utterance_index,
            elapsed_s=round(time.monotonic() - self.started_at, 3),
            rss_kib=read_proc_status_kib('VmRSS'),
            hwm_kib=read_proc_status_kib('VmHWM'),
            fds=count_open_fds(),
            threads=threading.active_count(),
            gc_objects=len(gc.get_objects()),
            active_rules=getattr(self, '_last_active_count', 0),
        )
        if self.compiler is not None and not self.compiler._closed:
            checkpoint['live_rules'] = len(self.compiler.kaldi_rule_by_id_dict)
            checkpoint['decoder_grammars'] = self.decoder.num_grammars if self.decoder else None
            tmp_dir = self.compiler.tmp_dir
            if tmp_dir:
                files, kib = directory_stats(tmp_dir)
                checkpoint['tmp_dir_files'] = files
                checkpoint['tmp_dir_kib'] = kib
            cache_path = Path(self.compiler.model_dir) / 'file_cache.json'
            checkpoint['cache_json_kib'] = (cache_path.stat().st_size // 1024
                                            if cache_path.is_file() else None)
        self.checkpoints.append(checkpoint)
        return checkpoint

    def _progress_line(self, utterance_index):
        config = self.config
        run_points = [checkpoint for checkpoint in self.checkpoints if checkpoint['phase'] == 'run']
        rss_now = run_points[-1]['rss_kib'] if run_points else None
        rss_first = run_points[0]['rss_kib'] if run_points else None
        rss_text = 'n/a'
        if rss_now is not None and rss_first is not None:
            rss_text = '%dMiB %+.1f' % (rss_now // 1024, (rss_now - rss_first) / 1024.0)
        recent = [seconds for _, seconds in self.latencies[-config.report_every:]]
        rate = (utterance_index + 1) / max(time.monotonic() - self.started_at, 1e-9)
        p95_ms = percentile(recent, 95)
        live_rules = sum(len(grammar.rules) for grammar in self.grammars)
        self.log('[%s] utt %d/%d | %.1f/s | rules %d act %d | churn %d reload %d | rss %s | p95 %s'
                 % (self.config.framework, utterance_index + 1, config.utterances, rate,
                    live_rules, getattr(self, '_last_active_count', 0),
                    self.counters['churn_cycles'], self.counters['reloads'], rss_text,
                    ('%.0fms' % (p95_ms * 1000)) if p95_ms is not None else 'n/a'))

    # ----- analysis --------------------------------------------------------------

    def _analyze(self, teardown_stats):
        config = self.config
        completed = self.counters['utterances']
        warmup_cutoff = completed * config.warmup_fraction
        run_points = [checkpoint for checkpoint in self.checkpoints
                      if checkpoint['phase'] == 'run' and checkpoint['utterance'] >= warmup_cutoff]

        def series(field):
            pairs = [(checkpoint['utterance'], checkpoint[field]) for checkpoint in run_points
                     if checkpoint.get(field) is not None]
            return [pair[0] for pair in pairs], [pair[1] for pair in pairs]

        verdicts = []

        def verdict(name, value, threshold, passed, detail=''):
            verdicts.append(dict(name=name, value=value, threshold=threshold,
                                 passed=bool(passed), detail=detail))

        verdict('correctness', len(self.failures), 0, len(self.failures) == 0,
                'recognition mismatches')

        xs, ys = series('rss_kib')
        slope = linear_slope(xs, ys)
        if slope is not None:
            slope_per_1k = slope * 1000.0
            net_growth = ys[-1] - ys[0]
            # A slope fitted through allocator jitter is meaningless when the
            # net movement is inside the noise floor; short runs cannot
            # resolve sub-noise leaks, long runs (overnight) can.
            within_noise = abs(net_growth) <= config.rss_noise_floor_kib
            verdict('rss-slope', round(slope_per_1k, 1), config.max_rss_slope_kib_per_1k,
                    within_noise or slope_per_1k <= config.max_rss_slope_kib_per_1k,
                    'KiB RSS growth per 1000 utterances, post-warmup (net %+d KiB, noise floor %d)'
                    % (net_growth, config.rss_noise_floor_kib))
        else:
            verdict('rss-slope', None, config.max_rss_slope_kib_per_1k, True,
                    'insufficient checkpoints or platform data')

        xs, ys = series('fds')
        if len(ys) >= 2:
            fd_growth = ys[-1] - ys[0]
            verdict('fd-growth', fd_growth, config.max_fd_growth,
                    fd_growth <= config.max_fd_growth, 'open fd change post-warmup')

        xs, ys = series('gc_objects')
        slope = linear_slope(xs, ys)
        if slope is not None:
            slope_per_1k = slope * 1000.0
            verdict('gc-objects-slope', round(slope_per_1k, 1),
                    config.max_gc_objects_slope_per_1k,
                    slope_per_1k <= config.max_gc_objects_slope_per_1k,
                    'Python object growth per 1000 utterances, post-warmup')

        post_warmup = [(index, seconds) for index, seconds in self.latencies
                       if index >= warmup_cutoff]
        latency_drift_pct = None
        if len(post_warmup) >= 40:
            quarter = len(post_warmup) // 4
            first_p95 = percentile([seconds for _, seconds in post_warmup[:quarter]], 95)
            last_p95 = percentile([seconds for _, seconds in post_warmup[-quarter:]], 95)
            if first_p95 and first_p95 > 0:
                latency_drift_pct = (last_p95 / first_p95 - 1.0) * 100.0
                verdict('latency-drift', round(latency_drift_pct, 1),
                        config.max_latency_drift_pct,
                        latency_drift_pct <= config.max_latency_drift_pct,
                        'p95 change, last vs first post-warmup quarter (%)')

        verdict('rule-registry-empty', teardown_stats['allocator_rules'], 0,
                teardown_stats['allocator_rules'] == 0,
                'rule IDs still allocated after closing all rules')
        verdict('python-rules-collected', teardown_stats['alive_rule_objects'], 0,
                teardown_stats['alive_rule_objects'] == 0,
                'KaldiRule objects alive after compiler close + gc')

        return verdicts, latency_drift_pct

    def _summarize_latency(self):
        seconds = [latency for _, latency in self.latencies]
        if not seconds:
            return {}
        summary = dict(
            count=len(seconds),
            p50_ms=round(percentile(seconds, 50) * 1000, 1),
            p95_ms=round(percentile(seconds, 95) * 1000, 1),
            p99_ms=round(percentile(seconds, 99) * 1000, 1),
            max_ms=round(max(seconds) * 1000, 1),
            mean_ms=round(sum(seconds) / len(seconds) * 1000, 1),
        )
        if self.audio_seconds_decoded > 0:
            summary['real_time_factor'] = round(sum(seconds) / self.audio_seconds_decoded, 3)
        return summary

    # ----- main entry ------------------------------------------------------------

    def run(self):
        from kaldi_active_grammar import Compiler, disable_donation_message
        config = self.config
        disable_donation_message()
        self.started_at = time.monotonic()

        if config.decode_mode == 'audio':
            if self.piper_voice is None:
                self.piper_voice = load_piper_voice()
            self.audio_pool = AudioPool(self.piper_voice)
            self._garbage_bytes = self._garbage_audio()

        self.compiler = Compiler(framework=config.framework)
        self.decoder = self.compiler.init_decoder()
        self._sample('startup', -1)

        for grammar_index in range(config.num_grammars):
            self.grammars.append(self._create_grammar(grammar_index, generation=0))
        self._prepare_for_recognition()
        if self.audio_pool is not None:
            self._presynthesize_audio()
            self.log('[%s] pre-synthesized %d texts in %.1fs'
                     % (config.framework, self.audio_pool.synth_calls,
                        self.audio_pool.synth_seconds))
        self._sample('built', -1)
        self.log('[%s] population built: %d grammars x %d rules (%d dictation each); starting %d utterances'
                 % (config.framework, config.num_grammars, config.rules_per_grammar,
                    config.dictation_rules_per_grammar, config.utterances))

        deadline = (self.started_at + config.max_minutes * 60.0) if config.max_minutes else None
        try:
            for utterance_index in range(config.utterances):
                if deadline is not None and time.monotonic() > deadline:
                    self.truncated = True
                    self.log('[%s] wall-clock cap reached; stopping at utterance %d'
                             % (config.framework, utterance_index))
                    break
                if len(self.failures) > config.max_failures:
                    self.truncated = True
                    self.log('[%s] aborting: more than %d failures'
                             % (config.framework, config.max_failures))
                    break
                if config.churn_every and utterance_index and utterance_index % config.churn_every == 0:
                    self._churn(utterance_index)
                if config.reload_every and utterance_index and utterance_index % config.reload_every == 0:
                    self._reload_one_rule()
                    self._prepare_for_recognition()
                self._run_one_utterance(utterance_index)
                self.counters['utterances'] += 1
                if (utterance_index + 1) % config.checkpoint_every == 0:
                    self._sample('run', utterance_index)
                if (utterance_index + 1) % config.report_every == 0:
                    self._progress_line(utterance_index)
        except KeyboardInterrupt:
            self.truncated = True
            self.log('[%s] interrupted; producing report from partial run' % config.framework)

        # Teardown: everything must release cleanly.  Pop rather than iterate
        # so no loop variable in this live frame pins the last grammar.
        while self.grammars:
            self._close_grammar(self.grammars.pop())
        allocator_rules = self.compiler._kaldi_rule_id_allocator.num_rules
        self._sample('drained', self.counters['utterances'])
        self.compiler.close()
        self.compiler = None
        self.decoder = None
        for _ in range(3):  # multiple passes: weakref/cffi finalizers can defer collection
            gc.collect()
        alive_rule_objects = sum(1 for reference in self.rule_refs if reference() is not None)
        if alive_rule_objects:
            self._log_alive_rule_referrers()
        self._sample('closed', self.counters['utterances'])

        teardown_stats = dict(allocator_rules=allocator_rules,
                              alive_rule_objects=alive_rule_objects)
        verdicts, latency_drift_pct = self._analyze(teardown_stats)
        report = self._build_report(verdicts, teardown_stats)
        self._print_summary(report, latency_drift_pct)
        if config.json_out:
            Path(config.json_out).parent.mkdir(parents=True, exist_ok=True)
            Path(config.json_out).write_text(json.dumps(report, indent=2))
            self.log('[%s] JSON report written to %s' % (config.framework, config.json_out))
        return report

    def _build_report(self, verdicts, teardown_stats):
        config = self.config
        failed = [verdict for verdict in verdicts if not verdict['passed']]
        counters = dict(self.counters)
        if self.audio_pool is not None:
            counters['synth_calls'] = self.audio_pool.synth_calls
            counters['synth_seconds'] = round(self.audio_pool.synth_seconds, 1)
        counters['prepare_seconds'] = round(self.prepare_seconds, 2)
        return dict(
            schema=1,
            label=config.label,
            timestamp=time.strftime('%Y-%m-%dT%H:%M:%S'),
            config=dataclasses.asdict(config),
            environment=dict(
                platform=platform.platform(),
                python=platform.python_version(),
            ),
            truncated=self.truncated,
            counters=counters,
            latency=self._summarize_latency(),
            teardown=teardown_stats,
            checkpoints=self.checkpoints,
            failures=self.failures,
            verdicts=verdicts,
            failed_verdicts=[verdict['name'] for verdict in failed],
            gated=not config.observe_only,
            passed=(not failed) or config.observe_only,
        )

    def _print_summary(self, report, latency_drift_pct):
        lines = ['', '=== long-term stress summary [%s] ===' % self.config.framework]
        counters = report['counters']
        lines.append('utterances: %d (%d valid, %d dictation, %d garbage, %d empty-activity)%s'
                     % (counters['utterances'], counters['valid_utterances'],
                        counters['dictation_utterances'], counters['garbage_utterances'],
                        counters['empty_activity_utterances'],
                        ' [TRUNCATED]' if report['truncated'] else ''))
        lines.append('churn: %d cycles (%d identical, %d novel grammar rebuilds), %d reloads, '
                     '%d rules created / %d closed'
                     % (counters['churn_cycles'], counters['identical_recreations'],
                        counters['novel_recreations'], counters['reloads'],
                        counters['rules_created'], counters['rules_closed']))
        latency = report['latency']
        if latency:
            rtf = latency.get('real_time_factor')
            lines.append('latency: p50 %.0fms p95 %.0fms p99 %.0fms max %.0fms%s'
                         % (latency['p50_ms'], latency['p95_ms'], latency['p99_ms'],
                            latency['max_ms'],
                            (' | RTF %.3f' % rtf) if rtf is not None else ''))
        run_points = [checkpoint for checkpoint in report['checkpoints']
                      if checkpoint['phase'] == 'run' and checkpoint.get('rss_kib') is not None]
        if run_points:
            lines.append('rss: first %d MiB, last %d MiB, high-water %s MiB'
                         % (run_points[0]['rss_kib'] // 1024, run_points[-1]['rss_kib'] // 1024,
                            (run_points[-1].get('hwm_kib') or 0) // 1024))
        for verdict in report['verdicts']:
            status = 'PASS' if verdict['passed'] else 'FAIL'
            lines.append('  [%s] %-24s value=%-10s threshold=%-8s %s'
                         % (status, verdict['name'], verdict['value'], verdict['threshold'],
                            verdict['detail']))
        lines.append('overall: %s%s' % ('PASS' if report['passed'] else 'FAIL',
                                        ' (observe-only)' if self.config.observe_only else ''))
        for line in lines:
            self.log(line)


# ----- CLI -----------------------------------------------------------------------

def build_config(profile=None, **overrides):
    values = dict(PROFILES[profile]) if profile else {}
    values.update({key: value for key, value in overrides.items() if value is not None})
    return StressConfig(**values)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--profile', choices=sorted(PROFILES), default='standard')
    parser.add_argument('--framework', choices=['agf', 'agf-direct', 'laf', 'both'], default='agf-direct')
    parser.add_argument('--json-out', default=None, help='write JSON report(s); with --framework both, the framework name is appended')
    parser.add_argument('--observe', action='store_true', help='report drift but never fail on it')
    parser.add_argument('--label', default=None, help='free-form label recorded in the report')

    knobs = parser.add_argument_group('workload knobs (override the profile)')
    for field in dataclasses.fields(StressConfig):
        if field.name in ('framework', 'observe_only', 'json_out', 'label'):
            continue
        option = '--' + field.name.replace('_', '-')
        if field.type == 'bool':
            knobs.add_argument(option, action='store_true', default=None)
        else:
            knobs.add_argument(option, type=type(field.default), default=None)
    args = parser.parse_args(argv)

    os.chdir(TESTS_DIR)
    frameworks = ['agf-direct', 'laf'] if args.framework == 'both' else \
        ['agf-direct' if args.framework == 'agf' else args.framework]

    overrides = {field.name: getattr(args, field.name)
                 for field in dataclasses.fields(StressConfig)
                 if hasattr(args, field.name) and field.name not in
                 ('framework', 'observe_only', 'json_out', 'label')}

    piper_voice = None
    all_passed = True
    for framework in frameworks:
        if framework == 'laf':
            missing = missing_laf_model_files()
            if missing:
                print('skipping laf: missing model files: %s' % ', '.join(missing))
                continue
        config = build_config(profile=args.profile, framework=framework, **overrides)
        config.observe_only = args.observe
        if args.label:
            config.label = args.label
        if args.json_out:
            path = Path(args.json_out)
            if len(frameworks) > 1:
                path = path.with_name('%s-%s%s' % (path.stem, framework, path.suffix or '.json'))
            config.json_out = str(path)
        if config.decode_mode == 'audio' and piper_voice is None:
            piper_voice = load_piper_voice()
        session = LongTermStressSession(config, piper_voice=piper_voice)
        report = session.run()
        all_passed = all_passed and report['passed']
    return 0 if all_passed else 1


if __name__ == '__main__':
    sys.exit(main())
