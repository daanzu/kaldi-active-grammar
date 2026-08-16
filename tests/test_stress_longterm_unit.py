"""Fast control-plane tests for the long-term stress harness."""

import dataclasses
import json
from types import SimpleNamespace

import pytest

from tests.stress import compat, longterm
from tests import test_stress_longterm as pytest_wrapper


def verdict_by_name(verdicts):
    return {verdict['name']: verdict for verdict in verdicts}


def make_analyzable_session(config=None):
    config = config or longterm.StressConfig(
        utterances=100, decode_mode='mimic', allow_missing_process_metrics=True)
    session = longterm.LongTermStressSession(config, log=lambda message: None)
    session.started_at = 0.0
    session.counters['utterances'] = config.utterances
    session.checkpoints = [
        dict(phase='built', utterance=-1, rss_kib=100_000,
             process_resources=10, process_resource_kind='file descriptors'),
        dict(phase='run', utterance=29, rss_kib=100_000, gc_objects=1_000,
             process_resources=10, process_resource_kind='file descriptors'),
        dict(phase='run', utterance=49, rss_kib=100_100, gc_objects=1_010,
             process_resources=10, process_resource_kind='file descriptors'),
        dict(phase='run', utterance=69, rss_kib=100_200, gc_objects=1_020,
             process_resources=10, process_resource_kind='file descriptors'),
        dict(phase='run', utterance=99, rss_kib=100_300, gc_objects=1_030,
             process_resources=10, process_resource_kind='file descriptors'),
        dict(phase='drained', utterance=100, rss_kib=100_000,
             process_resources=10, process_resource_kind='file descriptors'),
    ]
    return session


def test_truncated_run_fails_completion_gate():
    config = longterm.StressConfig(
        utterances=100, decode_mode='mimic', allow_missing_process_metrics=True)
    session = make_analyzable_session(config)
    session.counters['utterances'] = 0
    session.truncated = True

    verdicts, _ = session._analyze({'allocator_rules': 0, 'alive_rule_objects': 0})

    completion = verdict_by_name(verdicts)['completion']
    assert completion['value'] == 0
    assert not completion['passed']


def test_explicit_allow_truncated_allows_partial_completion():
    config = longterm.StressConfig(
        utterances=100, decode_mode='mimic', allow_truncated=True,
        allow_missing_process_metrics=True)
    session = make_analyzable_session(config)
    session.counters['utterances'] = 10
    session.truncated = True

    verdicts, _ = session._analyze({'allocator_rules': 0, 'alive_rule_objects': 0})

    assert verdict_by_name(verdicts)['completion']['passed']


def test_failure_categories_are_gated_separately():
    config = longterm.StressConfig(
        utterances=10_000, decode_mode='mimic', allow_missing_process_metrics=True,
        max_misrecognition_rate=0.001)
    session = make_analyzable_session(config)
    assert session.misrecognition_budget == 10
    for index in range(9):
        session._record_failure(index, 'command', 'rule-a', 'rule-b',
                                longterm.MISRECOGNITION, log=False)

    by_name = verdict_by_name(session._analyze(
        {'allocator_rules': 0, 'alive_rule_objects': 0})[0])
    assert by_name['recognition-accuracy']['value'] == 9
    assert by_name['recognition-accuracy']['threshold'] == 10
    assert by_name['recognition-accuracy']['passed']
    assert by_name['harness-invariants']['passed']

    session._record_failure(9, 'garbage-audio', 'no recognition', 'rule-a',
                            longterm.INVARIANT, log=False)

    by_name = verdict_by_name(session._analyze(
        {'allocator_rules': 0, 'alive_rule_objects': 0})[0])
    assert not by_name['harness-invariants']['passed']
    assert by_name['recognition-accuracy']['passed']


def test_misrecognitions_beyond_the_budget_fail_the_run():
    config = longterm.StressConfig(
        utterances=1_000, decode_mode='mimic', allow_missing_process_metrics=True,
        max_misrecognition_rate=0.001)
    session = make_analyzable_session(config)
    assert session.misrecognition_budget == 1
    for index in range(2):
        session._record_failure(index, 'command', 'rule-a', 'rule-b',
                                longterm.MISRECOGNITION, log=False)

    by_name = verdict_by_name(session._analyze(
        {'allocator_rules': 0, 'alive_rule_objects': 0})[0])
    assert not by_name['recognition-accuracy']['passed']
    assert by_name['harness-invariants']['passed']


def test_only_a_losing_rule_counts_as_a_misrecognition():
    config = longterm.StressConfig(utterances=10, decode_mode='mimic',
                                   allow_missing_process_metrics=True)
    session = longterm.LongTermStressSession(config, log=lambda message: None)
    expected_rule, other_rule = object(), object()
    parsed = [other_rule, ['go', 'left'], [False, False]]
    session.decoder = SimpleNamespace(mimic=lambda text, activity: text)
    session.compiler = SimpleNamespace(parse_output=lambda output: tuple(parsed))

    # The wrong active rule won: recognition quality.
    session._decode_and_validate(0, 'go left', [], expected_rule,
                                 ['go', 'left'], [False, False], 'command')
    assert (session.counters['misrecognitions'], session.counters['invariant_failures']) == (1, 0)

    # The right rule won but its alignment disagrees: a package invariant.
    parsed[0], parsed[1] = expected_rule, ['go', 'right']
    session._decode_and_validate(1, 'go left', [], expected_rule,
                                 ['go', 'left'], [False, False], 'command')
    assert (session.counters['misrecognitions'], session.counters['invariant_failures']) == (1, 1)

    # Something matched when nothing should have: also an invariant.
    parsed[0] = other_rule
    session._decode_and_validate(2, 'garbage', [], None, None, None, 'garbage-audio')
    assert (session.counters['misrecognitions'], session.counters['invariant_failures']) == (1, 2)


def test_phrase_screen_signature_tracks_workload_and_assets(tmp_path):
    config = longterm.StressConfig(num_grammars=2, rules_per_grammar=2)
    universe = longterm.build_phrase_universe()
    voice = tmp_path / 'voice.onnx'
    voice.write_bytes(b'x' * 10)

    signature = longterm.phrase_screen_signature(config, universe, tmp_path, voice)
    assert signature['voice'] == ['voice.onnx', 10]
    assert signature['command_pool_size'] == config.command_pool_size
    assert signature['model'] == {name: None for name in longterm.PHRASE_SCREEN_MODEL_FILES}

    voice.write_bytes(b'x' * 11)
    assert longterm.phrase_screen_signature(config, universe, tmp_path, voice) != signature
    voice.write_bytes(b'x' * 10)

    wider = dataclasses.replace(config, num_grammars=3)
    assert longterm.phrase_screen_signature(wider, universe, tmp_path, voice) != signature
    assert longterm.phrase_screen_signature(config, universe[:-1], tmp_path, voice) != signature


def test_phrase_screen_cache_keeps_one_entry_per_workload(tmp_path):
    path = tmp_path / 'phrase_screen.json'
    longterm.save_phrase_screen(path, {'a': 1}, dict(replaced=['first']))
    longterm.save_phrase_screen(path, {'a': 2}, dict(replaced=['second']))

    # A second profile or framework must not evict the first one's result.
    assert longterm.load_phrase_screen(path, {'a': 1})['replaced'] == ['first']
    assert longterm.load_phrase_screen(path, {'a': 2})['replaced'] == ['second']
    assert longterm.load_phrase_screen(path, {'a': 3}) is None
    assert longterm.load_phrase_screen(tmp_path / 'missing.json', {'a': 1}) is None


def test_phrase_screen_cache_survives_a_corrupt_file(tmp_path):
    path = tmp_path / 'phrase_screen.json'
    path.write_text('{not json')

    assert longterm.load_phrase_screen(path, {'a': 1}) is None
    longterm.save_phrase_screen(path, {'a': 1}, dict(replaced=[]))
    assert longterm.load_phrase_screen(path, {'a': 1})['replaced'] == []


def make_screenable_session():
    config = longterm.StressConfig(
        utterances=10, num_grammars=2, rules_per_grammar=2,
        dictation_rules_per_grammar=1, decode_mode='mimic')
    return longterm.LongTermStressSession(config, log=lambda message: None)


def test_screen_losers_are_swapped_for_unused_phrases():
    session = make_screenable_session()
    command_before = list(session.command_phrase_indices)
    dictation_before = list(session.dictation_phrase_indices)
    spares = session._spare_phrase_indices()
    assert not set(spares) & set(command_before + dictation_before)

    swapped = session._replace_screen_losers([
        dict(phrase_index=command_before[1], is_dictation=False, text='', got=''),
        dict(phrase_index=dictation_before[0], is_dictation=True, text='', got=''),
    ], spares)

    assert swapped
    assert session.command_phrase_indices[0] == command_before[0]
    assert session.command_phrase_indices[1] not in command_before
    assert session.dictation_phrase_indices[0] not in dictation_before
    # The dictation slot lookup follows the rewritten list.
    assert session._dictation_slot(0, 0)[0] == session.dictation_phrase_indices[0]


def test_replacement_reports_an_exhausted_universe():
    session = make_screenable_session()
    loser = dict(phrase_index=session.command_phrase_indices[0], is_dictation=False,
                 text='', got='')

    assert not session._replace_screen_losers([loser], [])


def test_unseparated_phrases_fail_their_verdict():
    session = make_analyzable_session()
    session.phrase_screen = dict(source='computed', unresolved=2, replaced=[{}])

    by_name = verdict_by_name(session._analyze(
        {'allocator_rules': 0, 'alive_rule_objects': 0})[0])

    assert by_name['phrase-screen']['value'] == 2
    assert not by_name['phrase-screen']['passed']


def test_missing_process_metrics_are_an_explicit_failure():
    config = longterm.StressConfig(utterances=1, decode_mode='mimic')
    session = longterm.LongTermStressSession(config, log=lambda message: None)
    session.started_at = 0.0
    session.counters['utterances'] = 1
    session.checkpoints = [dict(phase='built', utterance=-1, rss_kib=None,
                                process_resources=None)]

    verdicts, _ = session._analyze({'allocator_rules': 0, 'alive_rule_objects': 0})
    by_name = verdict_by_name(verdicts)

    assert not by_name['rss-metrics-available']['passed']
    assert not by_name['process-resource-metrics-available']['passed']


def test_process_metrics_support_windows_handle_counts():
    class WindowsProcess:
        def memory_info(self):
            return SimpleNamespace(rss=12 * 1024)

        def num_handles(self):
            return 7

    metrics = longterm.read_process_metrics(WindowsProcess())

    assert metrics == dict(
        available=True,
        rss_kib=12,
        process_resources=7,
        process_resource_kind='process handles',
    )


def test_absolute_and_baseline_performance_gates_detect_uniform_slowdown(tmp_path):
    config = longterm.StressConfig(
        utterances=100, decode_mode='mimic', allow_missing_process_metrics=True,
        max_p95_ms=150.0, max_prepare_seconds=15.0,
        max_baseline_regression_pct=25.0)
    baseline_config = dataclasses.asdict(config)
    baseline_config.update(max_p95_ms=0.0, max_prepare_seconds=0.0,
                           baseline_json='')
    baseline_path = tmp_path / 'baseline.json'
    baseline_path.write_text(json.dumps(dict(
        schema=2,
        config=baseline_config,
        latency={'p95_ms': 100.0},
        counters={'prepare_seconds': 10.0},
    )))
    config.baseline_json = str(baseline_path)
    session = make_analyzable_session(config)
    session.latencies = [(index, 0.2) for index in range(100)]
    session.prepare_seconds = 20.0

    verdicts, _ = session._analyze({'allocator_rules': 0, 'alive_rule_objects': 0})
    by_name = verdict_by_name(verdicts)

    assert not by_name['p95-latency']['passed']
    assert not by_name['prepare-seconds']['passed']
    assert by_name['baseline-compatible']['passed']
    assert not by_name['baseline-p95-ms']['passed']
    assert not by_name['baseline-prepare-seconds']['passed']


def test_framework_both_spawns_isolated_workers_and_pairs_baselines(monkeypatch, tmp_path):
    calls = []

    def fake_run(command):
        calls.append(command)
        return SimpleNamespace(returncode=0)

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr('subprocess.run', fake_run)

    exit_code = longterm.main([
        '--profile', 'smoke', '--framework', 'both',
        '--json-out', 'report.json', '--baseline-json', 'baseline.json',
    ])

    assert exit_code == 0
    assert len(calls) == 2
    assert [call[call.index('--framework') + 1] for call in calls] == ['agf-direct', 'laf']
    assert calls[0][calls[0].index('--json-out') + 1].endswith('report-agf-direct.json')
    assert calls[1][calls[1].index('--json-out') + 1].endswith('report-laf.json')
    assert calls[0][calls[0].index('--baseline-json') + 1].endswith(
        'baseline-agf-direct.json')
    assert calls[1][calls[1].index('--baseline-json') + 1].endswith('baseline-laf.json')


def test_pytest_wrapper_runs_profile_in_a_worker_process(monkeypatch, tmp_path):
    calls = []

    def fake_run(command):
        calls.append(command)
        report_path = command[command.index('--json-out') + 1]
        longterm.Path(report_path).write_text(json.dumps(dict(
            truncated=False, failures=[], failed_verdicts=[])))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(pytest_wrapper, 'REPORTS_DIR', tmp_path)
    monkeypatch.setattr(pytest_wrapper.subprocess, 'run', fake_run)
    wrapper = pytest_wrapper.TestLongTermStress()
    wrapper.framework = 'agf-direct'

    wrapper.run_profile('smoke')

    assert len(calls) == 1
    assert calls[0][0] == pytest_wrapper.sys.executable
    assert calls[0][calls[0].index('--framework') + 1] == 'agf-direct'


def test_setup_error_still_writes_report_and_reraises(monkeypatch, tmp_path):
    report_path = tmp_path / 'setup-failure.json'
    config = longterm.StressConfig(
        utterances=1, num_grammars=1, rules_per_grammar=1,
        dictation_rules_per_grammar=0, json_out=str(report_path),
        allow_missing_process_metrics=True)
    session = longterm.LongTermStressSession(config, log=lambda message: None)
    monkeypatch.setattr('kaldi_active_grammar.disable_donation_message', lambda: None)
    monkeypatch.setattr(longterm, 'load_piper_voice',
                        lambda: (_ for _ in ()).throw(FileNotFoundError('voice missing')))

    with pytest.raises(FileNotFoundError, match='voice missing'):
        session.run()

    report = json.loads(report_path.read_text())
    assert not report['passed']
    assert report['truncated']
    assert any(failure['kind'] == 'harness-error' for failure in report['failures'])


def test_unexpected_workload_error_tears_down_writes_report_and_reraises(
        monkeypatch, tmp_path):
    class FakeProcess:
        def memory_info(self):
            return SimpleNamespace(rss=100_000 * 1024)

        def num_fds(self):
            return 5

    class FakeDecoder:
        num_grammars = 0

    class FakeCompiler:
        instance = None

        def __init__(self, framework, model_dir=None):
            self.framework = framework
            self.model_dir_arg = model_dir
            self._closed = False
            self.closed = False
            self.decoder = None
            self.kaldi_rule_by_id_dict = {}
            self._kaldi_rule_id_allocator = SimpleNamespace(num_rules=0)
            self.tmp_dir = None
            self.model_dir = str(tmp_path)
            FakeCompiler.instance = self

        def init_decoder(self):
            self.decoder = FakeDecoder()
            return self.decoder

        def prepare_for_recognition(self):
            pass

        def close(self):
            self.closed = True
            self._closed = True

    monkeypatch.setattr('kaldi_active_grammar.Compiler', FakeCompiler)
    monkeypatch.setattr('kaldi_active_grammar.disable_donation_message', lambda: None)

    report_path = tmp_path / 'failure.json'
    config = longterm.StressConfig(
        utterances=1, num_grammars=1, rules_per_grammar=1,
        dictation_rules_per_grammar=0, decode_mode='mimic',
        json_out=str(report_path))
    session = longterm.LongTermStressSession(config, log=lambda message: None)
    session.process = FakeProcess()
    monkeypatch.setattr(session, '_create_grammar',
                        lambda *args, **kwargs: longterm.StressGrammar(0, 0, []))
    monkeypatch.setattr(session, '_run_one_utterance',
                        lambda utterance_index: (_ for _ in ()).throw(RuntimeError('boom')))

    with pytest.raises(RuntimeError, match='boom'):
        session.run()

    assert FakeCompiler.instance.closed
    assert report_path.is_file()
    report = json.loads(report_path.read_text())
    assert not report['passed']
    assert 'harness-invariants' in report['failed_verdicts']
    assert any(failure['kind'] == 'harness-error' for failure in report['failures'])
    assert all(failure['category'] == longterm.INVARIANT for failure in report['failures'])


########################################################################################################################
# Released-wheel compatibility shim (tests/stress/compat.py)

def released_api():
    return compat.ReleasedApi('3.2.0', '/wheel/kaldi_active_grammar/__init__.py')


def test_build_adapter_probes_the_installed_package():
    api = compat.build_adapter()

    assert isinstance(api, compat.CurrentApi) and not isinstance(api, compat.ReleasedApi)
    assert 'kaldi_active_grammar' in api.path


def test_build_adapter_falls_back_to_the_released_family_without_rule_close(monkeypatch):
    import kaldi_active_grammar

    monkeypatch.delattr(kaldi_active_grammar.KaldiRule, 'close')

    assert isinstance(compat.build_adapter(), compat.ReleasedApi)


def test_released_adapter_converts_rule_ids_to_a_positional_mask():
    api = released_api()
    compiler = SimpleNamespace(num_kaldi_rules=4)

    assert api.activity(compiler, [0, 3]) == [True, False, False, True]
    # An empty activity must still cover every rule, not send a zero-length array.
    assert api.activity(compiler, []) == [False] * 4
    assert api.activity(compiler, None) is None


def test_released_adapter_rejects_rule_ids_the_mask_cannot_represent():
    api = released_api()

    with pytest.raises(compat.UnsupportedByPackage, match='outside the 2 allocated rules'):
        api.activity(SimpleNamespace(num_kaldi_rules=2), [5])


def test_current_adapter_passes_rule_ids_through_untouched():
    api = compat.CurrentApi('dev', '/tree/kaldi_active_grammar/__init__.py')
    active_rule_ids = [1, 4]

    assert api.activity(SimpleNamespace(), active_rule_ids) is active_rule_ids


def test_released_adapter_closes_rules_and_native_objects_by_hand():
    api = released_api()
    rule = SimpleNamespace(destroyed=False)
    rule.destroy = lambda: setattr(rule, 'destroyed', True)
    decoder = SimpleNamespace(destroyed=False)
    decoder.destroy = lambda: setattr(decoder, 'destroyed', True)
    agf_compiler = SimpleNamespace(destroyed=False)
    agf_compiler.destroy = lambda: setattr(agf_compiler, 'destroyed', True)
    compiler = SimpleNamespace(decoder=decoder, _agf_compiler=agf_compiler,
                               num_kaldi_rules=0, kaldi_rule_by_id_dict={})

    api.close_rule(rule)
    assert api.compiler_is_open(compiler)
    api.close_compiler(compiler)
    api.close_compiler(compiler)  # idempotent, like Compiler.close()

    assert rule.destroyed and decoder.destroyed and agf_compiler.destroyed
    assert compiler.decoder is None and compiler._agf_compiler is None
    assert not api.compiler_is_open(compiler)
    assert api.allocated_rule_count(compiler) == 0


def test_released_wheels_reject_laf_and_mimic_but_accept_agf_audio():
    api = released_api()

    compat.check_workload_supported(api, 'agf-direct', 'audio', 1.0)
    with pytest.raises(compat.UnsupportedByPackage, match='ActiveReplaceFst'):
        compat.check_workload_supported(api, 'laf', 'audio', 1.0)
    with pytest.raises(compat.UnsupportedByPackage, match='mimic'):
        compat.check_workload_supported(api, 'agf-direct', 'mimic', 1.0)


def test_released_wheels_reject_mixed_lazy_loading_before_building_rules():
    api = released_api()

    # Uniform in either direction keeps rule ids and grammar-fst indexes aligned.
    compat.check_workload_supported(api, 'agf-direct', 'audio', 1.0)
    compat.check_workload_supported(api, 'agf-direct', 'audio', 0.0)
    with pytest.raises(compat.UnsupportedByPackage, match='--lazy-fraction 1 or 0'):
        compat.check_workload_supported(api, 'agf-direct', 'audio', 0.5)


def test_current_api_supports_every_framework_decode_mode_and_lazy_mix():
    api = compat.CurrentApi('dev', '/tree/kaldi_active_grammar/__init__.py')

    compat.check_workload_supported(api, 'laf', 'mimic', 0.5)


def test_session_decodes_through_the_adapter_and_records_the_package(monkeypatch):
    seen = []
    config = longterm.StressConfig(utterances=1, decode_mode='mimic',
                                   allow_missing_process_metrics=True)
    session = longterm.LongTermStressSession(config, log=lambda message: None,
                                             api=released_api())
    session.compiler = SimpleNamespace(num_kaldi_rules=3)
    session.decoder = SimpleNamespace(
        mimic=lambda text, activity: seen.append(activity) or '')
    session.compiler.parse_output = lambda output: (None, [], [])

    session._decode_and_validate(0, 'go left', [2], None, None, None, 'command')

    assert seen == [[False, False, True]]
    assert session._build_report([], {})['environment']['package_version'] == '3.2.0'


def test_cross_version_baseline_comparison_is_flagged_but_still_gated(tmp_path):
    config = longterm.StressConfig(
        utterances=100, decode_mode='audio', allow_missing_process_metrics=True)
    baseline_path = tmp_path / 'baseline.json'
    baseline_path.write_text(json.dumps(dict(
        schema=2,
        config=dataclasses.asdict(config),
        environment={'package_version': '3.2.0', 'package_api': 'released-3.0-3.2'},
        latency={'p95_ms': 100.0, 'real_time_factor': 0.1},
        counters={'prepare_seconds': 10.0},
    )))
    config.baseline_json = str(baseline_path)
    session = make_analyzable_session(config)
    session.latencies = [(index, 0.1) for index in range(100)]
    session.prepare_seconds = 10.0

    verdicts, _ = session._analyze({'allocator_rules': 0, 'alive_rule_objects': 0})
    by_name = verdict_by_name(verdicts)

    assert by_name['baseline-compatible']['passed']
    assert 'cross-version' in by_name['baseline-compatible']['detail']
    assert by_name['baseline-p95-ms']['passed']


def test_baseline_without_a_recorded_package_is_compared_without_a_note(tmp_path):
    config = longterm.StressConfig(
        utterances=100, decode_mode='mimic', allow_missing_process_metrics=True)
    baseline_path = tmp_path / 'baseline.json'
    baseline_path.write_text(json.dumps(dict(
        schema=2,
        config=dataclasses.asdict(config),
        environment={'platform': 'Linux', 'python': '3.13.5'},
        latency={'p95_ms': 100.0},
        counters={'prepare_seconds': 10.0},
    )))
    config.baseline_json = str(baseline_path)
    session = make_analyzable_session(config)
    session.latencies = [(index, 0.1) for index in range(100)]

    verdicts, _ = session._analyze({'allocator_rules': 0, 'alive_rule_objects': 0})
    compatible = verdict_by_name(verdicts)['baseline-compatible']

    assert compatible['passed']
    assert 'cross-version' not in compatible['detail']
