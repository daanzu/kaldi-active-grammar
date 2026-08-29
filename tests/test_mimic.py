import pytest

from kaldi_active_grammar import Compiler, KaldiError, NativeWFST
from tests.helpers import make_rule, missing_laf_model_files


@pytest.fixture
def mimic_compiler(request, change_to_test_dir):
    framework = getattr(request, 'param', 'agf-direct')
    if framework == 'laf':
        missing_files = missing_laf_model_files()
        if missing_files:
            pytest.skip('lookahead test model is missing: %s' % ', '.join(missing_files))

    compiler = Compiler(framework=framework)
    compiler.init_decoder()
    yield compiler
    compiler.close()


def build_phrase(*words):
    def build(fst):
        states = [fst.add_state(initial=True)]
        states.extend(fst.add_state() for _ in words[:-1])
        states.append(fst.add_state(final=True))
        for index, word in enumerate(words):
            fst.add_arc(states[index], states[index + 1], word)
    return build


def assert_all_rule_match(compiler, text, active_rule_ids, expected_rule,
                          expected_words, expected_mask=None):
    output = compiler.mimic(text, active_rule_ids)
    assert isinstance(output, str)
    assert output.startswith('#nonterm:rule%d ' % expected_rule.id)

    rule, words, dictation_mask = compiler.parse_output(output)
    assert rule is expected_rule
    assert words == expected_words
    if expected_mask is None:
        expected_mask = [False] * len(expected_words)
    assert dictation_mask == expected_mask
    return output


@pytest.mark.parametrize(
    'mimic_compiler',
    ['agf-direct', 'laf'],
    indirect=True,
    ids=['agf', 'laf'],
)
def test_backend_output_contracts(mimic_compiler):
    compiler = mimic_compiler
    rule = make_rule(compiler, 'Greeting', build_phrase('hello', 'world'))

    all_rule_output = compiler.mimic('hello world', [rule.id])
    selected_output = compiler.decoder.mimic(
        'hello world', [rule.id], grammar_fst_index=rule.id)

    if compiler.decoding_framework == 'laf':
        # LAF NativeWFST input labels use words.relabeled.txt, while the shared
        # native mimic path tokenizes text with the original words.txt IDs.
        # Until that mapping is implemented, this ordinary phrase cannot
        # match in either root mode.
        assert all_rule_output is None
        assert selected_output is False
        return

    assert_all_rule_match(compiler, 'hello world', [rule.id], rule, ['hello', 'world'])
    assert selected_output == 'hello world'
    assert not selected_output.startswith('#nonterm:rule')
    with pytest.raises(ValueError, match="expected a '#nonterm:rule' marker"):
        compiler.parse_output(selected_output)


def test_activity_state_sparse_ids_and_no_match(mimic_compiler):
    compiler = mimic_compiler
    inactive_rule = make_rule(compiler, 'Inactive', build_phrase('hello'))
    active_rule = make_rule(compiler, 'Active', build_phrase('world'))
    inactive_rule.close()

    active_ids = (rule_id for rule_id in [active_rule.id])
    assert_all_rule_match(compiler, 'world', active_ids, active_rule, ['world'])

    # None retains the activity installed by the previous mimic call.
    assert compiler.decoder.mimic('world', None) is not False
    assert compiler.mimic('world', []) is None
    assert compiler.decoder.mimic('world', None) is False
    assert compiler.mimic('hello', [active_rule.id]) is None
    assert compiler.decoder.mimic('world', None) is not False

    with pytest.raises(TypeError, match='integer rule IDs'):
        compiler.decoder.mimic('world', [True])
    with pytest.raises(ValueError, match='non-negative'):
        compiler.decoder.mimic('world', [-1])


@pytest.mark.parametrize('dictation_words', ['hello', 'hello world'])
def test_dictation_output_and_mask(mimic_compiler, dictation_words):
    compiler = mimic_compiler

    def build(fst):
        initial_state = fst.add_state(initial=True)
        command_state = fst.add_state()
        dictation_state = fst.add_state()
        end_state = fst.add_state()
        final_state = fst.add_state(final=True)
        fst.add_arc(initial_state, command_state, 'dictate')
        fst.add_arc(command_state, dictation_state, '#nonterm:dictation')
        fst.add_arc(dictation_state, end_state, None, '#nonterm:end')
        fst.add_arc(end_state, final_state, None)

    rule = make_rule(compiler, 'Dictation', build, has_dictation=True)
    words = ['dictate'] + dictation_words.split()
    assert_all_rule_match(
        compiler,
        'dictate ' + dictation_words,
        [rule.id],
        rule,
        words,
        [False] + [True] * len(dictation_words.split()),
    )


def test_epsilon_disambiguation_input_is_silent(mimic_compiler):
    compiler = mimic_compiler

    def build(fst):
        initial_state = fst.add_state(initial=True)
        disambiguated_state = fst.add_state()
        final_state = fst.add_state(final=True)
        fst.add_arc(
            initial_state,
            disambiguated_state,
            NativeWFST.eps_disambig,
            NativeWFST.eps,
        )
        fst.add_arc(disambiguated_state, final_state, 'hello')

    rule = make_rule(compiler, 'Disambiguated', build)
    assert_all_rule_match(compiler, 'hello', [rule.id], rule, ['hello'])
    assert compiler.decoder.mimic(
        'hello', [rule.id], grammar_fst_index=rule.id) == 'hello'


def test_nonexported_rule_is_only_a_root_when_selected(mimic_compiler):
    compiler = mimic_compiler
    child = make_rule(
        compiler,
        'PrivateChild',
        build_phrase('hello'),
        exported=False,
    )

    assert compiler.mimic('hello', [child.id]) is None
    assert compiler.decoder.mimic(
        'hello', [child.id], grammar_fst_index=child.id) == 'hello'

    def build_parent(fst):
        initial_state = fst.add_state(initial=True)
        final_state = fst.add_state(final=True)
        fst.add_arc(initial_state, final_state, '#nonterm:rule%d' % child.id)

    parent = make_rule(compiler, 'ExportedParent', build_parent)
    assert_all_rule_match(
        compiler, 'hello', [parent.id, child.id], parent, ['hello'])


def test_reload_removal_and_rule_id_recycling(mimic_compiler):
    compiler = mimic_compiler
    rule = make_rule(compiler, 'Reloaded', build_phrase('hello'))
    recycled_id = rule.id
    assert_all_rule_match(compiler, 'hello', [rule.id], rule, ['hello'])

    with rule.reload():
        build_phrase('world')(rule.fst)
        rule.compile()

    assert compiler.mimic('hello', [rule.id]) is None
    assert_all_rule_match(compiler, 'world', [rule.id], rule, ['world'])

    rule.close()
    assert compiler.decoder.mimic('world', [recycled_id]) is False

    replacement = make_rule(compiler, 'Replacement', build_phrase('test'))
    assert replacement.id == recycled_id
    assert compiler.mimic('world', [replacement.id]) is None
    assert_all_rule_match(
        compiler, 'test', [replacement.id], replacement, ['test'])


def test_output_overflow_and_zero_length_probe(mimic_compiler):
    compiler = mimic_compiler
    decoder = compiler.decoder
    rule = make_rule(
        compiler,
        'LongOutput',
        build_phrase('one', 'two', 'three', 'four', 'five'),
    )
    text = 'one two three four five'

    for grammar_fst_index in (None, rule.id):
        kwargs = ({'grammar_fst_index': grammar_fst_index}
                  if grammar_fst_index is not None else {})
        output = decoder.mimic(text, [rule.id], **kwargs)
        required_bytes = len(output.encode('utf-8')) + 1

        assert decoder.mimic(
            text, [rule.id], output_max_length=required_bytes, **kwargs) == output
        with pytest.raises(KaldiError, match='needed .* bytes of output'):
            decoder.mimic(
                text, [rule.id], output_max_length=required_bytes - 1, **kwargs)
        assert decoder.mimic(
            text, [rule.id], output_max_length=0, **kwargs) is True
        assert decoder.mimic(
            'hello', [rule.id], output_max_length=0, **kwargs) is False
