"""Fast control-plane tests for the long-term stress harness."""

import dataclasses
import json
from types import SimpleNamespace

import pytest

from tests.stress import longterm
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

        def __init__(self, framework):
            self.framework = framework
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
    assert 'correctness' in report['failed_verdicts']
    assert any(failure['kind'] == 'harness-error' for failure in report['failures'])
