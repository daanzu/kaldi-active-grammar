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

import time
from pathlib import Path

import pytest

from tests.stress.longterm import (
    LongTermStressSession,
    build_config,
    missing_laf_model_files,
)

REPORTS_DIR = Path(__file__).parent / '.stress_reports'

pytestmark = pytest.mark.stress


@pytest.mark.parametrize('framework', ['agf-direct', 'laf'], ids=['agf', 'laf'])
class TestLongTermStress:

    @pytest.fixture(autouse=True)
    def setup(self, change_to_test_dir, piper_voice, framework):
        if framework == 'laf':
            missing = missing_laf_model_files()
            if missing:
                pytest.skip('lookahead test model is missing: %s' % ', '.join(missing))
        self.framework = framework
        self.piper_voice = piper_voice

    def run_profile(self, profile):
        framework_id = 'agf' if self.framework == 'agf-direct' else self.framework
        config = build_config(profile=profile, framework=self.framework)
        config.label = f'pytest-{profile}'
        config.json_out = str(REPORTS_DIR / ('%s-%s-%s.json'
                              % (profile, framework_id, time.strftime('%Y%m%d-%H%M%S'))))
        session = LongTermStressSession(config, piper_voice=self.piper_voice)
        report = session.run()
        assert not report['failures'], report['failures'][:5]
        assert not report['failed_verdicts'], \
            'failed drift verdicts: %s (see %s)' % (report['failed_verdicts'], config.json_out)

    def test_longterm_smoke(self):
        """Fast, small-population run validating the harness end to end."""
        self.run_profile('smoke')

    def test_longterm_standard(self):
        """The scripted regression gate: ~100 rules with churn over thousands of utterances."""
        self.run_profile('standard')
