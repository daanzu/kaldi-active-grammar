"""Pytest entry points for the long-term stress harness.

These wrap ``tests/stress/longterm.py`` with fixed profiles so the harness can
run as a scripted regression gate.  They are excluded from default runs by the
``stress`` marker; enable with::

    just test -m stress                          # all stress tests
    just test -m stress -k 'smoke'               # quick validation only

Each run writes a JSON metrics report under ``tests/.stress_reports/`` for
trend tracking across commits.  For interactive or overnight runs with custom
knobs, invoke the harness CLI directly (see its module docstring).
"""

import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

from tests.helpers import missing_laf_model_files

REPORTS_DIR = Path(__file__).parent / '.stress_reports'
RUNNER = Path(__file__).parent / 'stress' / 'longterm.py'

pytestmark = pytest.mark.stress


@pytest.mark.parametrize('framework', ['agf-direct', 'laf'], ids=['agf', 'laf'])
class TestLongTermStress:

    @pytest.fixture(autouse=True)
    def setup(self, framework):
        if framework == 'laf':
            missing = missing_laf_model_files()
            if missing:
                pytest.skip('lookahead test model is missing: %s' % ', '.join(missing))
        self.framework = framework

    def run_profile(self, profile):
        framework_id = 'agf' if self.framework == 'agf-direct' else self.framework
        report_path = (REPORTS_DIR / ('%s-%s-%s-%d.json'
                       % (profile, framework_id, time.strftime('%Y%m%d-%H%M%S'),
                          time.time_ns()))).resolve()
        command = [
            sys.executable, str(RUNNER.resolve()),
            '--profile', profile,
            '--framework', self.framework,
            '--label', 'pytest-%s' % profile,
            '--json-out', str(report_path),
        ]
        result = subprocess.run(command)
        assert report_path.is_file(), \
            'stress worker exited %d without writing %s' % (result.returncode, report_path)
        report = json.loads(report_path.read_text())
        assert result.returncode == 0, \
            'stress worker exited %d (see %s)' % (result.returncode, report_path)
        assert not report['truncated'], 'stress workload was truncated (see %s)' % report_path
        # Misrecognitions are gated by the recognition-accuracy verdict against
        # its budget; anything else must not happen at all.
        invariant_failures = [failure for failure in report['failures']
                              if failure.get('category') != 'misrecognition']
        assert not invariant_failures, invariant_failures[:5]
        assert not report['failed_verdicts'], \
            'failed verdicts: %s (see %s)' % (report['failed_verdicts'], report_path)

    def test_longterm_smoke(self):
        """Fast, small-population run validating the harness end to end."""
        self.run_profile('smoke')

    def test_longterm_standard(self):
        """The scripted regression gate: ~100 rules with churn over thousands of utterances."""
        self.run_profile('standard')
