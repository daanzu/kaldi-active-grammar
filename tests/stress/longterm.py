"""Long-term stress harness modeling extended power-user sessions.

One Compiler and one decoder stay alive for the whole run while many grammars
(each a group of rules) are decoded against, activated/deactivated per
utterance, and periodically closed, recreated (with recycled rule IDs and
FileCache hits), and reloaded in place.  Resource metrics are sampled at
checkpoints and the run fails on incomplete execution, resource drift,
performance regression, or any recognition error, making it usable both as an
interactive soak test and as a scripted regression gate.

Run directly for full knob control (see ``--help``)::

    .venv/bin/python tests/stress/longterm.py --profile smoke --framework agf
    .venv/bin/python tests/stress/longterm.py --profile standard --framework both --json-out report.json

or through pytest (see ``tests/test_stress_longterm.py``)::

    just test -m stress

It can also run against a released wheel, for cross-version baselines (AGF
only; see ``just stress-release`` and ``tests/stress/compat.py``)::

    just stress-release 3.2.0 --profile standard --json-out v3.2.0.json --observe
    just stress --profile standard --framework agf --lazy-fraction 1 --baseline-json v3.2.0.json

The harness assumes the test Kaldi model in ``tests/kaldi_model`` and the
Piper voice used by the rest of the test suite (``just setup-tests``).
"""

from __future__ import annotations

import argparse
import ctypes
import dataclasses
import gc
import hashlib
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

try:
    import psutil
except ImportError:  # Reported as an explicit failed verdict in gated runs.
    psutil = None

try:  # Imported as ``tests.stress.longterm``...
    from .compat import build_adapter, check_workload_supported, UnsupportedByPackage
except ImportError:  # ...or run as a script, with tests/stress on sys.path.
    from compat import build_adapter, check_workload_supported, UnsupportedByPackage

TESTS_DIR = Path(__file__).resolve().parents[1]

try:  # Imported by pytest from the repository root...
    from tests.helpers import missing_laf_model_files
except ModuleNotFoundError:  # ...or run directly as a script.
    sys.path.insert(0, str(TESTS_DIR))
    from helpers import missing_laf_model_files

PROCESS_METRIC_ERRORS = (OSError, RuntimeError)
if psutil is not None:
    PROCESS_METRIC_ERRORS += (psutil.Error,)

# All words below are known-good in the test model's lexicon (they are already
# exercised by the regular grammar tests).  The universe must stay unambiguous:
# each phrase is unique, and dictation payload words never appear in it.
VERBS = ('go', 'move', 'turn')
DIRECTIONS = ('left', 'right', 'forward', 'back', 'north', 'south', 'east', 'west')
NUMBERS = ('one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten')
# No empty payload: trailing-audio decoding of a zero-word dictation span is
# not reliable enough for a correctness-gated bulk run.
DICTATION_PAYLOADS = ('hello world', 'hello')

# Failure categories.  INVARIANT covers what the package must hold however
# poor the acoustic model is: rejecting garbage and inactive rules, parsing an
# alignment that matches the rule that won, and tearing down cleanly.
# MISRECOGNITION is one active rule losing to another, which is a property of
# the model and the phrase set rather than of the code under test.
INVARIANT = 'invariant'
MISRECOGNITION = 'misrecognition'

BASELINE_CONFIG_KEYS = (
    'framework', 'utterances', 'num_grammars', 'rules_per_grammar',
    'dictation_rules_per_grammar', 'decode_mode', 'activity_pattern',
    'active_grammar_fraction', 'context_switch_prob', 'context_drift_prob',
    'empty_activity_fraction', 'garbage_audio_fraction', 'churn_every',
    'churn_fraction', 'novel_fraction', 'phrase_pool_factor', 'reload_every',
    'lazy_fraction', 'seed', 'skip_phrase_screen',
)

PHRASE_SCREEN_FILENAME = 'phrase_screen.json'
# Model files that decide which phrases are separable and that the package
# never regenerates; the derived lexicon and graph artifacts are excluded
# because switching versions rewrites them without changing the acoustics.
PHRASE_SCREEN_MODEL_FILES = ('final.mdl', 'lexicon.txt', 'KAG_VERSION')


def phrase_screen_signature(config, universe, model_dir, voice_path):
    """Identify everything that can change which phrases survive screening.

    The package version is deliberately absent: a screened pool is meant to be
    shared across versions, so that a ``--baseline-json`` comparison runs the
    very same workload on both.  A decoder change large enough to move the
    separability boundary surfaces as budgeted misrecognitions instead.
    """
    def file_size(path):
        return path.stat().st_size if path.is_file() else None

    return dict(
        universe=hashlib.sha1('\n'.join(universe).encode()).hexdigest()[:16],
        command_pool_size=config.command_pool_size,
        dictation_slots=config.reserved_dictation_phrases,
        payloads=list(DICTATION_PAYLOADS),
        framework=config.framework,
        model={name: file_size(Path(model_dir) / name)
               for name in PHRASE_SCREEN_MODEL_FILES},
        voice=[Path(voice_path).name, file_size(Path(voice_path))],
    )


def phrase_screen_key(signature):
    return hashlib.sha1(json.dumps(signature, sort_keys=True).encode()).hexdigest()[:16]


def read_phrase_screen_cache(path):
    try:
        cached = json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return {}
    return cached if isinstance(cached.get('results'), dict) else {}


def load_phrase_screen(path, signature):
    """Return the cached screen result for this signature, or None."""
    return read_phrase_screen_cache(path).get('results', {}).get(phrase_screen_key(signature))


def save_phrase_screen(path, signature, payload):
    """Add one result, keeping the entries for other profiles and frameworks.

    Every profile and framework screens a different candidate set, so a
    single-entry file would thrash between them.
    """
    cached = read_phrase_screen_cache(path) or {'results': {}}
    cached['results'][phrase_screen_key(signature)] = dict(payload, signature=signature)
    try:
        Path(path).write_text(json.dumps(cached, indent=2))
    except OSError:  # A read-only model dir only costs a rescreen next run.
        pass


def build_phrase_universe():
    universe = [f'{verb} {direction}' for verb in VERBS for direction in DIRECTIONS]
    universe += [f'{verb} {direction} {number}'
                 for verb in VERBS for direction in DIRECTIONS for number in NUMBERS]
    universe += [f'{direction} {number}' for direction in DIRECTIONS for number in NUMBERS]
    universe += [f'{number} {verb} {direction}'
                 for number in NUMBERS for verb in VERBS for direction in DIRECTIONS]
    return universe


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
    skip_phrase_screen: bool = False    # skip the pre-run acoustic separability screen
    rescreen_phrases: bool = False      # ignore any cached screen result
    max_screen_rounds: int = 4          # phrase-replacement rounds before giving up

    max_failures: int = 25              # abort the run after this many invariant failures
    # Recognizing the wrong active rule is acoustic-model quality, not a
    # package invariant, so it gets a whole-run budget rather than a hard zero.
    max_misrecognition_rate: float = 0.001

    observe_only: bool = False          # collect and report, but never fail on drift verdicts
    allow_truncated: bool = False       # allow a partial workload to pass its completion gate
    allow_missing_process_metrics: bool = False
    max_rss_slope_kib_per_1k: float = 512.0
    rss_noise_floor_kib: float = 4096.0  # ignore slope when net post-warmup growth is under allocator jitter
    max_rss_drain_return_kib: float = 32768.0  # RSS retained after closing all rules, vs post-build baseline
    max_fd_growth: int = 5
    max_latency_drift_pct: float = 75.0
    max_gc_objects_slope_per_1k: float = 2000.0
    max_p95_ms: float = 0.0             # absolute performance gates; 0 disables
    max_real_time_factor: float = 0.0
    max_prepare_seconds: float = 0.0
    baseline_json: str = ''             # compare performance with a compatible prior report
    max_baseline_regression_pct: float = 25.0

    model_dir: str = ''                 # Kaldi model directory; empty uses tests/kaldi_model
    json_out: str = ''
    label: str = ''

    def validate(self):
        if self.framework not in ('agf-direct', 'agf', 'laf'):
            raise ValueError('framework must be agf-direct or laf')
        if self.decode_mode not in ('audio', 'mimic'):
            raise ValueError('decode_mode must be audio or mimic')
        if self.activity_pattern not in ('bursty', 'random', 'cycling'):
            raise ValueError('unknown activity_pattern %r' % self.activity_pattern)
        if self.utterances <= 0 or self.num_grammars <= 0 or self.rules_per_grammar <= 0:
            raise ValueError('utterances, num_grammars, and rules_per_grammar must be positive')
        if not (0 <= self.dictation_rules_per_grammar <= self.rules_per_grammar):
            raise ValueError('dictation_rules_per_grammar out of range')
        if self.decode_mode == 'mimic' and self.dictation_rules_per_grammar == self.rules_per_grammar:
            raise ValueError('mimic mode requires at least one non-dictation rule per grammar')
        for name in ('active_grammar_fraction', 'context_switch_prob', 'context_drift_prob',
                     'empty_activity_fraction', 'garbage_audio_fraction', 'churn_fraction',
                     'novel_fraction', 'lazy_fraction', 'warmup_fraction',
                     'max_misrecognition_rate'):
            if not 0.0 <= getattr(self, name) <= 1.0:
                raise ValueError('%s must be between 0 and 1' % name)
        if self.empty_activity_fraction + self.garbage_audio_fraction > 1.0:
            raise ValueError('empty and garbage utterance fractions must sum to at most 1')
        if self.checkpoint_every <= 0 or self.report_every <= 0:
            raise ValueError('checkpoint_every and report_every must be positive')
        if self.churn_every < 0 or self.reload_every < 0 or self.max_minutes < 0:
            raise ValueError('cadences and max_minutes cannot be negative')
        if self.max_screen_rounds < 1:
            raise ValueError('max_screen_rounds must be at least 1')
        if self.max_baseline_regression_pct < 0:
            raise ValueError('max_baseline_regression_pct cannot be negative')
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


def read_process_metrics(process):
    """Return cross-platform RSS and descriptor/handle counts via psutil."""
    if process is None:
        return dict(available=False, error='psutil is not installed')
    try:
        rss_kib = process.memory_info().rss // 1024
        if hasattr(process, 'num_fds'):
            resource_count = process.num_fds()
            resource_kind = 'file descriptors'
        elif hasattr(process, 'num_handles'):
            resource_count = process.num_handles()
            resource_kind = 'process handles'
        else:
            resource_count = None
            resource_kind = None
        return dict(available=True, rss_kib=rss_kib,
                    process_resources=resource_count, process_resource_kind=resource_kind)
    except PROCESS_METRIC_ERRORS as error:
        return dict(available=False, error='%s: %s' % (type(error).__name__, error))


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


def piper_voice_path():
    return TESTS_DIR / os.environ.get('PIPER_MODEL', 'en_US-ryan-low.onnx')


def load_piper_voice():
    import piper
    model_path = piper_voice_path()
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

    def __init__(self, config, piper_voice=None, log=None, api=None):
        config.validate()
        self.config = config
        # Every call into kaldi_active_grammar whose shape differs between the
        # current API and released wheels goes through this adapter; see
        # tests/stress/compat.py.
        self.api = api if api is not None else build_adapter()
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
        # Both lists are rewritten in place by the phrase screen, which swaps
        # out any phrase the recognizer cannot separate from the rest.
        self.command_phrase_indices = list(range(config.command_pool_size))
        self.dictation_phrase_indices = list(
            range(len(self.universe) - config.reserved_dictation_phrases, len(self.universe)))
        self.free_phrase_indices = list(self.command_phrase_indices)
        self.phrase_screen = None
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
            prepare_calls=0, invariant_failures=0, misrecognitions=0,
        )
        self.prepare_seconds = 0.0
        self.truncated = False
        self.started_at = None
        self._rss_high_water_kib = None
        try:
            self.process = psutil.Process() if psutil is not None else None
        except PROCESS_METRIC_ERRORS:
            self.process = None

    @property
    def misrecognition_budget(self):
        """Wrong-rule allowance for the whole planned run.

        A rate rather than a count, so the same knob means the same thing to a
        200-utterance smoke run and a 200,000-utterance soak.  Exceeding it at
        any point means the gate has already failed, which is what makes it
        safe to use as the abort threshold too.
        """
        return int(self.config.max_misrecognition_rate * self.config.utterances)

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
        return self.dictation_phrase_indices[slot], DICTATION_PAYLOADS[slot % len(DICTATION_PAYLOADS)]

    def _build_rule(self, name, phrase_index, is_dictation, payload, lazy=False):
        """Create, populate, compile, and load one rule.

        Returns the rule, the text to speak for it, and the parse the harness
        must get back.  Shared by the measured population and the phrase
        screen, so both put identical graphs in front of the decoder.
        """
        from kaldi_active_grammar import KaldiRule
        lead_words = self.universe[phrase_index].split()
        rule = KaldiRule(self.compiler, name, has_dictation=is_dictation or None)
        if is_dictation:
            self._build_dictation_fst(rule.fst, lead_words)
            payload_words = payload.split()
            words = lead_words + ['dictate'] + payload_words
            mask = [False] * (len(lead_words) + 1) + [True] * len(payload_words)
        else:
            self._build_command_fst(rule.fst, lead_words)
            words = list(lead_words)
            mask = [False] * len(lead_words)
        rule.compile(lazy=lazy)
        rule.load(lazy=lazy)
        return rule, ' '.join(words), words, mask

    def _create_rule(self, grammar_index, rule_index, generation, phrase_index,
                     is_dictation, payload, lazy):
        name = f'Stress_g{grammar_index}_r{rule_index}_gen{generation}'
        rule, text, expected_words, expected_mask = self._build_rule(
            name, phrase_index, is_dictation, payload, lazy)
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
        for phrase_index in self.command_phrase_indices:
            self.audio_pool.get(self.universe[phrase_index])
        for grammar_index in range(self.config.num_grammars):
            for rule_index in range(self.config.dictation_rules_per_grammar):
                phrase_index, payload = self._dictation_slot(grammar_index, rule_index)
                lead_words = self.universe[phrase_index].split()
                self.audio_pool.get(' '.join(lead_words + ['dictate'] + payload.split()))

    # ----- phrase screening ------------------------------------------------------

    def _spare_phrase_indices(self):
        """Universe phrases held by neither the command pool nor a dictation slot."""
        used = set(self.command_phrase_indices) | set(self.dictation_phrase_indices)
        return [index for index in range(len(self.universe)) if index not in used]

    def _screen_round(self, round_index):
        """Decode every candidate phrase with all of them active at once.

        Returns the candidates not won by their own rule.  Screening with the
        whole pool live is strictly harder than anything the run presents:
        extra competitors can only take probability away from the right
        answer, so a phrase that survives here survives any active subset.
        """
        candidates = [(index, False, None) for index in self.command_phrase_indices]
        candidates += [(self.dictation_phrase_indices[slot], True,
                        DICTATION_PAYLOADS[slot % len(DICTATION_PAYLOADS)])
                       for slot in range(self.config.reserved_dictation_phrases)]

        entries = []
        for position, (phrase_index, is_dictation, payload) in enumerate(candidates):
            rule, text, words, mask = self._build_rule(
                'Screen_r%d_p%d' % (round_index, position), phrase_index, is_dictation, payload)
            entries.append((phrase_index, is_dictation, rule, text, words, mask))
        self.compiler.prepare_for_recognition()

        activity = self.api.activity(self.compiler, [entry[2].id for entry in entries])
        losers = []
        try:
            for phrase_index, is_dictation, rule, text, words, mask in entries:
                self.decoder.decode(self.audio_pool.get(text), True, activity)
                output, _ = self.decoder.get_output()
                recognized, got_words, got_mask = self.compiler.parse_output(output)
                if recognized is not rule or got_words != words or got_mask != mask:
                    losers.append(dict(phrase_index=phrase_index, text=text,
                                       is_dictation=is_dictation,
                                       got=' '.join(got_words) if got_words else '(nothing)'))
        finally:
            for entry in entries:
                self.api.close_rule(entry[2])
        return losers

    def _replace_screen_losers(self, losers, spares):
        """Swap each losing phrase for an unused one; False if the universe runs dry."""
        for loser in losers:
            if not spares:
                return False
            replacement = spares.pop(0)
            if loser['is_dictation']:
                slot = self.dictation_phrase_indices.index(loser['phrase_index'])
                self.dictation_phrase_indices[slot] = replacement
            else:
                position = self.command_phrase_indices.index(loser['phrase_index'])
                self.command_phrase_indices[position] = replacement
        return True

    def _screen_phrase_pool(self):
        """Replace phrases the recognizer cannot tell apart, before measuring.

        The workload asserts that every utterance is won by its own rule, which
        only holds if the phrases in play are acoustically separable under this
        model and voice.  Losers are swapped for unused phrases from the
        universe and the round is repeated until one comes back clean; what
        survives is cached next to the model, since the outcome depends on the
        model, the voice, and the phrase universe rather than on the run.
        """
        config = self.config
        cache_path = Path(self.compiler.model_dir) / PHRASE_SCREEN_FILENAME
        signature = phrase_screen_signature(config, self.universe,
                                            self.compiler.model_dir, piper_voice_path())
        cached = None if config.rescreen_phrases else load_phrase_screen(cache_path, signature)
        if cached is not None:
            self.command_phrase_indices = list(cached['command_phrase_indices'])
            self.dictation_phrase_indices = list(cached['dictation_phrase_indices'])
            self.phrase_screen = dict(cached, source='cache', seconds=0.0)
            self.phrase_screen.pop('signature', None)
            self.free_phrase_indices = list(self.command_phrase_indices)
            self.log('[%s] phrase screen: %d replaced, from %s'
                     % (config.framework, len(cached['replaced']), cache_path))
            return

        started = time.monotonic()
        spares = self._spare_phrase_indices()
        replaced, unresolved, rounds, losers = [], 0, 0, []
        for round_index in range(config.max_screen_rounds):
            rounds = round_index + 1
            losers = self._screen_round(round_index)
            if not losers:
                break
            replaced.extend(losers)
            if not self._replace_screen_losers(losers, spares):
                unresolved = len(losers)
                self.log('[%s] phrase screen: out of spare phrases, leaving %d confusable'
                         % (config.framework, unresolved))
                break
        else:
            # The last round's replacements went in unverified, so the pool is
            # not proven clean even though every known loser was swapped out.
            unresolved = len(losers)
            self.log('[%s] phrase screen: no clean round within %d; %d replacements unverified'
                     % (config.framework, config.max_screen_rounds, unresolved))

        self.phrase_screen = dict(
            source='computed', seconds=round(time.monotonic() - started, 1),
            rounds=rounds, unresolved=unresolved,
            replaced=[dict(text=loser['text'], got=loser['got']) for loser in replaced],
            command_phrase_indices=list(self.command_phrase_indices),
            dictation_phrase_indices=list(self.dictation_phrase_indices))
        self.free_phrase_indices = list(self.command_phrase_indices)
        save_phrase_screen(cache_path, signature, self.phrase_screen)
        self.log('[%s] phrase screen: %d replaced in %d rounds, %.1fs%s'
                 % (config.framework, len(replaced), rounds, self.phrase_screen['seconds'],
                    ''.join('\n    %r lost to %r' % (loser['text'], loser['got'])
                            for loser in replaced)))

    def _prepare_for_recognition(self):
        started = time.monotonic()
        self.compiler.prepare_for_recognition()
        self.prepare_seconds += time.monotonic() - started
        self.counters['prepare_calls'] += 1

    def _close_grammar(self, grammar):
        for stress_rule in grammar.rules:
            self.api.close_rule(stress_rule.rule)
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

    def _record_failure(self, utterance_index, kind, expected, got, category, log=True):
        """Record one failure, keeping the per-category counters current.

        ``log`` is off for callers that report the failure themselves.
        """
        self.failures.append(dict(utterance=utterance_index, kind=kind, category=category,
                                  expected=str(expected), got=str(got)))
        self.counters['misrecognitions' if category == MISRECOGNITION
                      else 'invariant_failures'] += 1
        if log:
            self.log('FAILURE at utterance %d (%s, %s): expected %s, got %s'
                     % (utterance_index, kind, category, expected, got))

    def _decode_and_validate(self, utterance_index, text_or_audio, active_rule_ids,
                             expected_rule, expected_words, expected_mask, kind):
        # Built before the timer: converting activity is shim work on released
        # wheels, and must not be charged to the package's decode latency.
        activity = self.api.activity(self.compiler, active_rule_ids)
        started = time.monotonic()
        if self.config.decode_mode == 'mimic':
            output = self.decoder.mimic(text_or_audio, activity)
            output = output if output is not False else ''
        else:
            self.decoder.decode(text_or_audio, True, activity)
            output, info = self.decoder.get_output()
            self.audio_seconds_decoded += len(text_or_audio) / (2.0 * 16000.0)
        recognized_rule, words, mask = self.compiler.parse_output(output)
        elapsed = time.monotonic() - started
        self.latencies.append((utterance_index, elapsed))

        if expected_rule is None:
            if recognized_rule is not None:
                self._record_failure(utterance_index, kind, 'no recognition',
                                     '%r -> %r' % (recognized_rule, words), INVARIANT)
        else:
            if recognized_rule is not expected_rule:
                self._record_failure(utterance_index, kind, expected_rule, recognized_rule,
                                     MISRECOGNITION)
            elif words != expected_words or mask != expected_mask:
                self._record_failure(utterance_index, kind,
                                     (expected_words, expected_mask), (words, mask), INVARIANT)

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
        process_metrics = read_process_metrics(self.process)
        rss_kib = process_metrics.get('rss_kib')
        if rss_kib is not None:
            self._rss_high_water_kib = max(self._rss_high_water_kib or rss_kib, rss_kib)
        checkpoint = dict(
            phase=phase,
            utterance=utterance_index,
            elapsed_s=round(time.monotonic() - self.started_at, 3),
            process_metrics_available=process_metrics['available'],
            process_metrics_error=process_metrics.get('error'),
            rss_kib=rss_kib,
            hwm_kib=self._rss_high_water_kib,
            process_resources=process_metrics.get('process_resources'),
            process_resource_kind=process_metrics.get('process_resource_kind'),
            # Retain the old key for schema-1 report consumers. On Windows its
            # value is a process-handle count rather than a POSIX fd count.
            fds=process_metrics.get('process_resources'),
            threads=threading.active_count(),
            gc_objects=len(gc.get_objects()),
            active_rules=getattr(self, '_last_active_count', 0),
        )
        if self.compiler is not None and self.api.compiler_is_open(self.compiler):
            checkpoint['live_rules'] = self.api.live_rule_count(self.compiler)
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

        invariant_failures = self.counters['invariant_failures']
        misrecognitions = self.counters['misrecognitions']
        verdict('harness-invariants', invariant_failures, 0, invariant_failures == 0,
                'rejection, alignment, harness, or teardown failures')
        budget = self.misrecognition_budget
        verdict('recognition-accuracy', misrecognitions, budget, misrecognitions <= budget,
                'utterances won by the wrong active rule (budget %g%% of %d planned)'
                % (config.max_misrecognition_rate * 100, config.utterances))

        if self.phrase_screen is not None:
            unresolved = self.phrase_screen['unresolved']
            verdict('phrase-screen', unresolved, 0, unresolved == 0,
                    'phrases left unseparated by screening (%d replaced, from %s)'
                    % (len(self.phrase_screen['replaced']), self.phrase_screen['source']))

        completed_target = completed == config.utterances
        verdict('completion', completed, config.utterances,
                completed_target or config.allow_truncated,
                'utterances completed%s' % (' (partial runs allowed)'
                                             if config.allow_truncated else ''))

        rss_metrics_available = any(checkpoint.get('rss_kib') is not None
                                    for checkpoint in self.checkpoints)
        resource_metrics_available = any(checkpoint.get('process_resources') is not None
                                         for checkpoint in self.checkpoints)
        metrics_required = not config.allow_missing_process_metrics
        verdict('rss-metrics-available', rss_metrics_available, True,
                rss_metrics_available or not metrics_required,
                'cross-platform process RSS sampling%s' %
                (' (missing metrics allowed)' if not metrics_required else ''))
        verdict('process-resource-metrics-available', resource_metrics_available, True,
                resource_metrics_available or not metrics_required,
                'file-descriptor or process-handle sampling%s' %
                (' (missing metrics allowed)' if not metrics_required else ''))

        xs, ys = series('rss_kib')
        slope = linear_slope(xs, ys)
        if slope is not None:
            slope_per_1k = slope * 1000.0
            net_growth = ys[-1] - ys[0]
            # A slope fitted through allocator jitter is meaningless when the
            # net movement is inside the noise floor (or negative: a run that
            # ends below where it started is not leaking); short runs cannot
            # resolve sub-noise leaks, long runs (overnight) can.
            within_noise = net_growth <= config.rss_noise_floor_kib
            verdict('rss-slope', round(slope_per_1k, 1), config.max_rss_slope_kib_per_1k,
                    within_noise or slope_per_1k <= config.max_rss_slope_kib_per_1k,
                    'KiB RSS growth per 1000 utterances, post-warmup (net %+d KiB, noise floor %d)'
                    % (net_growth, config.rss_noise_floor_kib))
        else:
            verdict('rss-slope', None, config.max_rss_slope_kib_per_1k, True,
                    'insufficient checkpoints or platform data')

        xs, ys = series('process_resources')
        if len(ys) >= 2:
            resource_growth = ys[-1] - ys[0]
            resource_kind = next((checkpoint.get('process_resource_kind')
                                  for checkpoint in run_points
                                  if checkpoint.get('process_resource_kind')), 'process resources')
            verdict('process-resource-growth', resource_growth, config.max_fd_growth,
                    resource_growth <= config.max_fd_growth,
                    '%s change post-warmup' % resource_kind)

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

        latency_summary = self._summarize_latency()
        if config.max_p95_ms > 0:
            p95_ms = latency_summary.get('p95_ms')
            verdict('p95-latency', p95_ms, config.max_p95_ms,
                    p95_ms is not None and p95_ms <= config.max_p95_ms,
                    'absolute p95 utterance latency (ms)')
        if config.max_real_time_factor > 0:
            real_time_factor = latency_summary.get('real_time_factor')
            verdict('real-time-factor', real_time_factor, config.max_real_time_factor,
                    real_time_factor is not None and
                    real_time_factor <= config.max_real_time_factor,
                    'total decode time divided by audio duration')
        if config.max_prepare_seconds > 0:
            verdict('prepare-seconds', round(self.prepare_seconds, 2),
                    config.max_prepare_seconds,
                    self.prepare_seconds <= config.max_prepare_seconds,
                    'total compile/load preparation time')

        if config.baseline_json:
            self._add_baseline_verdicts(verdict, latency_summary)

        # The strongest leak discriminator: after every rule is closed, RSS
        # must return to near the post-build baseline no matter how large the
        # decode-graph working set was in between.
        rss_by_phase = {checkpoint['phase']: checkpoint.get('rss_kib')
                        for checkpoint in self.checkpoints}
        if rss_by_phase.get('built') and rss_by_phase.get('drained'):
            drain_return = rss_by_phase['drained'] - rss_by_phase['built']
            verdict('rss-drain-return', drain_return, config.max_rss_drain_return_kib,
                    drain_return <= config.max_rss_drain_return_kib,
                    'KiB RSS retained after closing all rules, vs post-build baseline')

        verdict('rule-registry-empty', teardown_stats['allocator_rules'], 0,
                teardown_stats['allocator_rules'] == 0,
                'rule IDs still allocated after closing all rules')
        verdict('python-rules-collected', teardown_stats['alive_rule_objects'], 0,
                teardown_stats['alive_rule_objects'] == 0,
                'KaldiRule objects alive after compiler close + gc')

        return verdicts, latency_drift_pct

    def _add_baseline_verdicts(self, verdict, latency_summary):
        """Compare this run with a compatible prior JSON report."""
        config = self.config
        try:
            baseline = json.loads(Path(config.baseline_json).read_text())
        except (OSError, ValueError, TypeError) as error:
            verdict('baseline-load', None, config.baseline_json, False,
                    '%s: %s' % (type(error).__name__, error))
            return

        baseline_config = baseline.get('config') or {}
        current_config = dataclasses.asdict(config)
        mismatches = []
        for key in BASELINE_CONFIG_KEYS:
            current = current_config.get(key)
            previous = baseline_config.get(key)
            if key == 'framework':
                current = 'agf-direct' if current == 'agf' else current
                previous = 'agf-direct' if previous == 'agf' else previous
            if current != previous:
                mismatches.append('%s=%r (baseline %r)' % (key, current, previous))
        compatible = not mismatches
        detail = 'matching workload configuration' if compatible else '; '.join(mismatches[:5])
        # Reports written before the package identity was recorded simply skip
        # the note; there is nothing to compare against.
        baseline_environment = baseline.get('environment') or {}
        baseline_identity = ('%s [%s]' % (baseline_environment['package_version'],
                                          baseline_environment.get('package_api', 'unknown'))
                             if baseline_environment.get('package_version') else None)
        if compatible and baseline_identity and baseline_identity != self.api.identity:
            # Deliberate for release-vs-development comparisons, but the native
            # library differs too, so small deltas are build noise, not signal.
            detail += ' (cross-version: baseline %s, current %s)' % (baseline_identity,
                                                                     self.api.identity)
        verdict('baseline-compatible', compatible, True, compatible, detail)
        if not compatible:
            return

        current_metrics = {
            'p95-ms': latency_summary.get('p95_ms'),
            'prepare-seconds': round(self.prepare_seconds, 2),
        }
        baseline_latency = baseline.get('latency') or {}
        baseline_counters = baseline.get('counters') or {}
        baseline_metrics = {
            'p95-ms': baseline_latency.get('p95_ms'),
            'prepare-seconds': baseline_counters.get('prepare_seconds'),
        }
        if config.decode_mode == 'audio':
            current_metrics['real-time-factor'] = latency_summary.get('real_time_factor')
            baseline_metrics['real-time-factor'] = baseline_latency.get('real_time_factor')

        for name, current in current_metrics.items():
            previous = baseline_metrics.get(name)
            if current is None or previous is None:
                verdict('baseline-%s' % name, None,
                        config.max_baseline_regression_pct, False,
                        'metric missing from current or baseline report')
                continue
            if previous == 0:
                regression_pct = 0.0 if current == 0 else float('inf')
            else:
                regression_pct = (current / previous - 1.0) * 100.0
            rounded = round(regression_pct, 1) if math.isfinite(regression_pct) else 'infinity'
            verdict('baseline-%s' % name, rounded, config.max_baseline_regression_pct,
                    regression_pct <= config.max_baseline_regression_pct,
                    'percent change from baseline (%s -> %s)' % (previous, current))

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
        config = self.config
        self.started_at = time.monotonic()
        caught_error = None
        try:
            from kaldi_active_grammar import Compiler, disable_donation_message
            disable_donation_message()
            check_workload_supported(self.api, config.framework, config.decode_mode,
                                     config.lazy_fraction)
            self.log('[%s] using %s' % (config.framework, self.api.describe()))
            if config.decode_mode == 'audio':
                if self.piper_voice is None:
                    self.piper_voice = load_piper_voice()
                self.audio_pool = AudioPool(self.piper_voice)
                self._garbage_bytes = self._garbage_audio()

            self.compiler = Compiler(model_dir=config.model_dir or None,
                                     framework=config.framework)
            self.decoder = self.compiler.init_decoder()
            self._sample('startup', -1)

            # Before the population exists, so the screen's own rules are the
            # only ones in the graph, and before the 'built' baseline, so its
            # allocations cannot masquerade as workload growth.
            if self.audio_pool is not None and not config.skip_phrase_screen:
                self._screen_phrase_pool()

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

            # The cap applies to the measured workload, not model loading and
            # bounded audio pre-synthesis performed before the baseline.
            deadline = ((time.monotonic() + config.max_minutes * 60.0)
                        if config.max_minutes else None)
            # Never abort before max_failures examples have been logged, even
            # when the budget is smaller: one sample is a poor bug report.
            misrecognition_abort = max(config.max_failures, self.misrecognition_budget)
            for utterance_index in range(config.utterances):
                if deadline is not None and time.monotonic() > deadline:
                    self.truncated = True
                    self.log('[%s] wall-clock cap reached; stopping at utterance %d'
                             % (config.framework, utterance_index))
                    break
                if self.counters['invariant_failures'] > config.max_failures:
                    self.truncated = True
                    self.log('[%s] aborting: more than %d invariant failures'
                             % (config.framework, config.max_failures))
                    break
                if self.counters['misrecognitions'] > misrecognition_abort:
                    self.truncated = True
                    self.log('[%s] aborting: more than %d misrecognitions (budget %d)'
                             % (config.framework, misrecognition_abort,
                                self.misrecognition_budget))
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
        except BaseException as error:
            self.truncated = True
            caught_error = sys.exc_info()
            kind = 'interrupted' if isinstance(error, KeyboardInterrupt) else 'harness-error'
            self._record_failure(self.counters['utterances'], kind,
                                 'successful workload execution',
                                 '%s: %s' % (type(error).__name__, error),
                                 INVARIANT, log=False)
            self.log('[%s] %s; producing report after teardown: %s: %s'
                     % (config.framework, kind, type(error).__name__, error))

        teardown_stats, teardown_error = self._teardown()
        if caught_error is None and teardown_error is not None:
            caught_error = teardown_error
        verdicts, latency_drift_pct = self._analyze(teardown_stats)
        report = self._build_report(verdicts, teardown_stats)
        self._print_summary(report, latency_drift_pct)
        if config.json_out:
            Path(config.json_out).parent.mkdir(parents=True, exist_ok=True)
            Path(config.json_out).write_text(json.dumps(report, indent=2))
            self.log('[%s] JSON report written to %s' % (config.framework, config.json_out))
        if caught_error is not None:
            _, error, traceback = caught_error
            raise error.with_traceback(traceback)
        return report

    def _teardown(self):
        """Release every reachable native resource, continuing after failures."""
        first_error = None

        def note_error(kind, error):
            nonlocal first_error
            if first_error is None:
                first_error = (type(error), error, error.__traceback__)
            self._record_failure(self.counters['utterances'], kind,
                                 'successful teardown',
                                 '%s: %s' % (type(error).__name__, error),
                                 INVARIANT, log=False)
            self.log('[%s] %s: %s: %s'
                     % (self.config.framework, kind, type(error).__name__, error))

        # Pop all containers and close rules individually so one bad close
        # cannot prevent the remaining rules or compiler from being released.
        while self.grammars:
            grammar = self.grammars.pop()
            while grammar.rules:
                stress_rule = grammar.rules.pop()
                try:
                    self.api.close_rule(stress_rule.rule)
                    self.counters['rules_closed'] += 1
                except BaseException as error:
                    note_error('rule-teardown-error', error)
                del stress_rule
            del grammar

        allocator_rules = 0
        if self.compiler is not None:
            allocator_rules = self.api.allocated_rule_count(self.compiler)
            try:
                self._sample('drained', self.counters['utterances'])
            except BaseException as error:
                note_error('drained-sample-error', error)
            try:
                self.api.close_compiler(self.compiler)
            except BaseException as error:
                note_error('compiler-teardown-error', error)
        self.compiler = None
        self.decoder = None

        for _ in range(3):  # multiple passes: weakref/cffi finalizers can defer collection
            gc.collect()
        alive_rule_objects = sum(1 for reference in self.rule_refs if reference() is not None)
        if alive_rule_objects:
            try:
                self._log_alive_rule_referrers()
            except BaseException as error:
                note_error('teardown-diagnostic-error', error)
        try:
            self._sample('closed', self.counters['utterances'])
        except BaseException as error:
            note_error('closed-sample-error', error)

        return (dict(allocator_rules=allocator_rules,
                     alive_rule_objects=alive_rule_objects), first_error)

    def _build_report(self, verdicts, teardown_stats):
        config = self.config
        failed = [verdict for verdict in verdicts if not verdict['passed']]
        counters = dict(self.counters)
        if self.audio_pool is not None:
            counters['synth_calls'] = self.audio_pool.synth_calls
            counters['synth_seconds'] = round(self.audio_pool.synth_seconds, 1)
        counters['prepare_seconds'] = round(self.prepare_seconds, 2)
        return dict(
            # 3: failures carry a category, and the single correctness verdict
            # became the harness-invariants / recognition-accuracy pair.
            schema=3,
            label=config.label,
            timestamp=time.strftime('%Y-%m-%dT%H:%M:%S'),
            config=dataclasses.asdict(config),
            environment=dict(
                platform=platform.platform(),
                python=platform.python_version(),
                package_version=self.api.version,
                package_api=self.api.name,
                package_path=self.api.path,
            ),
            truncated=self.truncated,
            phrase_screen=self.phrase_screen,
            counters=counters,
            latency=self._summarize_latency(),
            latency_series_ms=[[index, round(seconds * 1000, 1)]
                               for index, seconds in self.latencies],
            teardown=teardown_stats,
            checkpoints=self.checkpoints,
            failures=self.failures,
            verdicts=verdicts,
            failed_verdicts=[verdict['name'] for verdict in failed],
            gated=not config.observe_only,
            passed=(not failed) or config.observe_only,
        )

    def _print_summary(self, report, latency_drift_pct):
        lines = ['', '=== long-term stress summary [%s, kaldi_active_grammar %s] ==='
                 % (self.config.framework, self.api.identity)]
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
        lines.append('failures: %d invariant, %d misrecognitions (budget %d)'
                     % (counters['invariant_failures'], counters['misrecognitions'],
                        self.misrecognition_budget))
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


def framework_report_path(path_value, framework):
    path = Path(path_value)
    return path.with_name('%s-%s%s' % (path.stem, framework, path.suffix or '.json'))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--profile', choices=sorted(PROFILES), default='standard')
    parser.add_argument('--framework', choices=['agf', 'agf-direct', 'laf', 'both'], default='agf-direct')
    parser.add_argument('--json-out', default=None, help='write JSON report(s); with --framework both, the framework name is appended')
    parser.add_argument('--observe', action='store_true', help='report drift but never fail on it')
    parser.add_argument('--label', default=None, help='free-form label recorded in the report')
    parser.add_argument('--allow-truncated', action='store_true', default=None,
                        help='allow a wall-clock-limited partial workload to pass completion')
    parser.add_argument('--allow-missing-process-metrics', action='store_true', default=None,
                        help='do not fail when RSS or descriptor/handle metrics are unavailable')
    parser.add_argument('--baseline-json', default=None,
                        help='compare performance with a compatible prior JSON report')

    knobs = parser.add_argument_group('workload knobs (override the profile)')
    for field in dataclasses.fields(StressConfig):
        if field.name in ('framework', 'observe_only', 'json_out', 'label',
                          'allow_truncated', 'allow_missing_process_metrics',
                          'baseline_json'):
            continue
        option = '--' + field.name.replace('_', '-')
        if field.type == 'bool':
            knobs.add_argument(option, action='store_true', default=None)
        else:
            knobs.add_argument(option, type=type(field.default), default=None)
    args = parser.parse_args(argv)

    # The worker changes into tests/ to locate its model. Keep paths relative
    # to the caller's directory, which is what CLI users expect.
    invocation_dir = Path.cwd()
    if args.json_out:
        args.json_out = str((invocation_dir / args.json_out).resolve())
    if args.baseline_json:
        args.baseline_json = str((invocation_dir / args.baseline_json).resolve())
    if args.model_dir:
        args.model_dir = str((invocation_dir / args.model_dir).resolve())

    if args.framework == 'both':
        # One process per framework: RSS and fd measurements are meaningless
        # when a second decoder session runs on top of the first one's freed
        # allocator arenas.
        import subprocess
        base_argv = []
        arguments = iter(list(argv) if argv is not None else sys.argv[1:])
        for argument in arguments:
            if argument in ('--framework', '--json-out', '--baseline-json'):
                next(arguments, None)
                continue
            if argument.startswith(('--framework=', '--json-out=', '--baseline-json=')):
                continue
            base_argv.append(argument)
        exit_code = 0
        for framework in ('agf-direct', 'laf'):
            child_argv = base_argv + ['--framework', framework]
            if args.json_out:
                child_argv += ['--json-out', str(framework_report_path(args.json_out, framework))]
            if args.baseline_json:
                child_argv += ['--baseline-json',
                               str(framework_report_path(args.baseline_json, framework))]
            result = subprocess.run([sys.executable, __file__] + child_argv)
            exit_code = exit_code or result.returncode
        return exit_code

    os.chdir(TESTS_DIR)
    frameworks = ['agf-direct' if args.framework == 'agf' else args.framework]

    overrides = {field.name: getattr(args, field.name)
                 for field in dataclasses.fields(StressConfig)
                 if hasattr(args, field.name) and field.name not in
                 ('framework', 'observe_only', 'json_out', 'label')}

    api = build_adapter()
    all_passed = True
    for framework in frameworks:
        if framework == 'laf':
            if not api.supports_framework('laf'):
                print('skipping laf: not supported by %s' % api.describe())
                continue
            missing = missing_laf_model_files(args.model_dir or None)
            if missing:
                print('skipping laf: missing model files: %s' % ', '.join(missing))
                continue
        config = build_config(profile=args.profile, framework=framework, **overrides)
        config.observe_only = args.observe
        if args.label:
            config.label = args.label
        if args.json_out:
            config.json_out = args.json_out
        try:
            check_workload_supported(api, framework, config.decode_mode, config.lazy_fraction)
        except UnsupportedByPackage as error:
            parser.error(str(error))
        session = LongTermStressSession(config, api=api)
        report = session.run()
        all_passed = all_passed and report['passed']
    return 0 if all_passed else 1


if __name__ == '__main__':
    sys.exit(main())
