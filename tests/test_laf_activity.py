"""LAF activity-set lifetime regressions."""

import pytest

from kaldi_active_grammar import Compiler, KaldiError
from tests.helpers import make_rule, missing_laf_model_files


@pytest.fixture
def laf_compiler(change_to_test_dir):
    missing_files = missing_laf_model_files()
    if missing_files:
        pytest.skip(
            'lookahead test model is missing: %s' % ', '.join(missing_files))

    compiler = Compiler(framework='laf')
    compiler.init_decoder()
    yield compiler
    compiler.close()


def test_laf_mid_utterance_activity_change_is_rejected(
        laf_compiler, audio_generator):
    """LAF activity stays fixed while decoding a chunked utterance."""
    def build_rule(fst):
        initial = fst.add_state(initial=True)
        final = fst.add_state(final=True)
        fst.add_arc(initial, final, 'hello')

    rule = make_rule(laf_compiler, 'LafUtteranceScope', build_rule)
    audio = audio_generator('hello')
    split = (len(audio) // 4) * 2  # Keep the int16 byte boundary aligned.

    laf_compiler.decoder.decode(audio[:split], False, [rule.id])

    # Repeating the current set is a no-op, while changing it is rejected.
    laf_compiler.decoder.decode(audio[:0], False, [rule.id])
    with pytest.raises(KaldiError):
        laf_compiler.decoder.decode(audio[:0], False, [])

    # Rejection must not poison the utterance already in progress.
    laf_compiler.decoder.decode(audio[split:], True, None)
    output, _ = laf_compiler.decoder.get_output()
    recognized_rule, words, dictation_mask = laf_compiler.parse_output(output)
    assert recognized_rule == rule
    assert words == ['hello']
    assert dictation_mask == [False]
