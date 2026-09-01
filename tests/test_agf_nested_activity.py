"""AGF activity/cache regressions for nested rule graphs.

These tests deliberately use real audio decoding rather than ``mimic()``.
``mimic()`` builds a fresh ``ActiveReplaceFst`` for each call and therefore
cannot exercise ``ActiveGrammarFst``'s persistent expanded-state cache.
"""

from contextlib import contextmanager

import pytest

from kaldi_active_grammar import Compiler, KaldiRule
from tests.helpers import make_rule


def build_sequence(*labels):
    """Build one path whose labels may be words or rule nonterminals."""
    def build(fst):
        states = [fst.add_state(initial=True)]
        states.extend(fst.add_state() for _ in labels[:-1])
        states.append(fst.add_state(final=True))
        for index, label in enumerate(labels):
            fst.add_arc(states[index], states[index + 1], label)
    return build


def rule_label(rule):
    return '#nonterm:rule%d' % rule.id


def make_sequence_rule(compiler, name, *labels, **kwargs):
    return make_rule(compiler, name, build_sequence(*labels), **kwargs)


@pytest.fixture
def agf_compiler(change_to_test_dir):
    compiler = Compiler(framework='agf-direct')
    compiler.init_decoder()
    yield compiler
    compiler.close()


def read_observation(compiler):
    output, _ = compiler.decoder.get_output()
    rule, words, dictation_mask = compiler.parse_output(output)
    return (
        None if rule is None else rule.id,
        tuple(words),
        tuple(dictation_mask),
    )


def decode_observation(compiler, audio, active_rule_ids):
    compiler.decoder.decode(audio, True, active_rule_ids)
    return read_observation(compiler)


def expected_match(rule, *words):
    return rule.id, tuple(words), (False,) * len(words)


NO_MATCH = (None, (), ())


def make_one_level_graph(compiler):
    child = make_sequence_rule(
        compiler, 'PrivateChild', 'hello', exported=False)
    parent = make_sequence_rule(
        compiler, 'ExportedParent', rule_label(child))
    return parent, child


@contextmanager
def one_level_session():
    compiler = Compiler(framework='agf-direct')
    compiler.init_decoder()
    try:
        parent, child = make_one_level_graph(compiler)
        yield compiler, parent, child
    finally:
        compiler.close()


def test_nested_call_updates_active_inactive_active(agf_compiler, audio_generator):
    """An already-hydrated nested call must stop and resume emitting arcs."""
    parent, child = make_one_level_graph(agf_compiler)
    audio = audio_generator('hello')

    # These IDs make this the focused reproducer: exported rule 0 invokes
    # private rule 1000, so the affected call is not cached in instance 0.
    assert parent.id == 0
    assert child.id == 1000

    assert decode_observation(
        agf_compiler, audio, [parent.id, child.id]
    ) == expected_match(parent, 'hello')
    assert decode_observation(
        agf_compiler, audio, [parent.id]
    ) == NO_MATCH
    assert decode_observation(
        agf_compiler, audio, [parent.id, child.id]
    ) == expected_match(parent, 'hello')


def test_nested_call_updates_inactive_active_inactive(agf_compiler, audio_generator):
    """A call first cached inactive must become usable without rebuilding AGF."""
    parent, child = make_one_level_graph(agf_compiler)
    audio = audio_generator('hello')

    assert decode_observation(
        agf_compiler, audio, [parent.id]
    ) == NO_MATCH
    assert decode_observation(
        agf_compiler, audio, [parent.id, child.id]
    ) == expected_match(parent, 'hello')
    assert decode_observation(
        agf_compiler, audio, [parent.id]
    ) == NO_MATCH


def test_activity_history_matches_cold_agf(change_to_test_dir, audio_generator):
    """Warm-cache semantics must equal an AGF constructed at final activity."""
    audio = audio_generator('hello')

    with one_level_session() as (warm, parent, child):
        assert decode_observation(
            warm, audio, [parent.id, child.id]
        ) == expected_match(parent, 'hello')
        assert decode_observation(warm, audio, [parent.id]) == NO_MATCH
        warm_active = decode_observation(warm, audio, [parent.id, child.id])
        warm_inactive = decode_observation(warm, audio, [parent.id])

    with one_level_session() as (cold_active, parent, child):
        direct_active = decode_observation(
            cold_active, audio, [parent.id, child.id])

    with one_level_session() as (cold_inactive, parent, child):
        direct_inactive = decode_observation(cold_inactive, audio, [parent.id])

    assert warm_active == direct_active == expected_match(parent, 'hello')
    assert warm_inactive == direct_inactive == NO_MATCH


def test_deeply_nested_call_updates_at_arbitrary_depth(agf_compiler, audio_generator):
    """Invalidation must reach call caches several instances below the top."""
    leaf = make_sequence_rule(
        agf_compiler, 'DeepLeaf', 'hello', exported=False)
    private_rules = [leaf]
    target = leaf
    for depth in range(3):
        target = make_sequence_rule(
            agf_compiler,
            'PrivateLevel%d' % depth,
            rule_label(target),
            exported=False,
        )
        private_rules.append(target)
    root = make_sequence_rule(
        agf_compiler, 'DeepRoot', rule_label(target))
    all_active = [root.id] + [rule.id for rule in private_rules]
    leaf_inactive = [rule_id for rule_id in all_active if rule_id != leaf.id]
    audio = audio_generator('hello')

    assert decode_observation(
        agf_compiler, audio, all_active
    ) == expected_match(root, 'hello')
    assert decode_observation(
        agf_compiler, audio, leaf_inactive
    ) == NO_MATCH
    assert decode_observation(
        agf_compiler, audio, all_active
    ) == expected_match(root, 'hello')


def test_cached_returns_survive_parent_and_child_toggles(agf_compiler, audio_generator):
    """A cached nested path must remain usable across activity toggles.

    This is end-to-end coverage only. Because a return is unreachable while
    its parent is inactive, the public Python API cannot prove that cached
    #nonterm_end boundaries were excluded from invalidation; that classification
    requires a lower-level native test which inspects expanded boundaries.
    """
    child = make_sequence_rule(
        agf_compiler, 'ReturningChild', 'hello', exported=False)
    parent = make_sequence_rule(
        agf_compiler,
        'ReturningParent',
        rule_label(child),
        'world',
    )
    audio = audio_generator('hello world')
    both = [parent.id, child.id]

    # The first decode expands both the nested call and the child's return.
    assert decode_observation(
        agf_compiler, audio, both
    ) == expected_match(parent, 'hello', 'world')

    # Toggling the parent must not turn its cached child return into an
    # activity-controlled call boundary.
    assert decode_observation(
        agf_compiler, audio, [child.id]
    ) == NO_MATCH
    assert decode_observation(
        agf_compiler, audio, both
    ) == expected_match(parent, 'hello', 'world')

    # Toggling the child exercises the real call boundary while retaining the
    # already-cached return boundary.
    assert decode_observation(
        agf_compiler, audio, [parent.id]
    ) == NO_MATCH
    assert decode_observation(
        agf_compiler, audio, both
    ) == expected_match(parent, 'hello', 'world')


def test_every_call_site_targeting_one_rule_updates(agf_compiler, audio_generator):
    """All cached boundaries for one target rule must be updated together."""
    child = make_sequence_rule(
        agf_compiler, 'SharedCallTarget', 'hello', exported=False)

    def build_parent(fst):
        initial = fst.add_state(initial=True)
        first_call = fst.add_state()
        first_return = fst.add_state()
        second_call = fst.add_state()
        second_return = fst.add_state()
        final = fst.add_state(final=True)
        fst.add_arc(initial, first_call, 'one')
        fst.add_arc(first_call, first_return, rule_label(child))
        fst.add_arc(first_return, final, 'world')
        fst.add_arc(initial, second_call, 'two')
        fst.add_arc(second_call, second_return, rule_label(child))
        fst.add_arc(second_return, final, 'test')

    parent = make_rule(agf_compiler, 'TwoCallSites', build_parent)
    first_audio = audio_generator('one hello world')
    second_audio = audio_generator('two hello test')
    both = [parent.id, child.id]

    # Populate two distinct base-state cache entries in the same parent
    # instance before changing activity.
    assert decode_observation(
        agf_compiler, first_audio, both
    ) == expected_match(parent, 'one', 'hello', 'world')
    assert decode_observation(
        agf_compiler, second_audio, both
    ) == expected_match(parent, 'two', 'hello', 'test')

    assert decode_observation(
        agf_compiler, first_audio, [parent.id]
    ) == NO_MATCH
    assert decode_observation(
        agf_compiler, second_audio, [parent.id]
    ) == NO_MATCH

    assert decode_observation(
        agf_compiler, first_audio, both
    ) == expected_match(parent, 'one', 'hello', 'world')
    assert decode_observation(
        agf_compiler, second_audio, both
    ) == expected_match(parent, 'two', 'hello', 'test')


def test_same_parent_ifst_in_multiple_instances_updates(agf_compiler, audio_generator):
    """Per-instance copies of one source boundary must not retain stale state."""
    leaf = make_sequence_rule(
        agf_compiler, 'InstanceLeaf', 'hello', exported=False)
    shared_parent = make_sequence_rule(
        agf_compiler,
        'SharedPrivateParent',
        rule_label(leaf),
        exported=False,
    )

    def build_root(fst):
        initial = fst.add_state(initial=True)
        first_call = fst.add_state()
        first_return = fst.add_state()
        second_call = fst.add_state()
        second_return = fst.add_state()
        final = fst.add_state(final=True)
        fst.add_arc(initial, first_call, 'one')
        fst.add_arc(first_call, first_return, rule_label(shared_parent))
        fst.add_arc(first_return, final, 'world')
        fst.add_arc(initial, second_call, 'two')
        fst.add_arc(second_call, second_return, rule_label(shared_parent))
        fst.add_arc(second_return, final, 'test')

    root = make_rule(agf_compiler, 'MultipleParentInstances', build_root)
    first_audio = audio_generator('one hello world')
    second_audio = audio_generator('two hello test')
    all_active = [root.id, shared_parent.id, leaf.id]
    leaf_inactive = [root.id, shared_parent.id]

    # Distinct return states create two FstInstances for shared_parent. Decode
    # both paths so each instance caches its own shared_parent -> leaf call.
    assert decode_observation(
        agf_compiler, first_audio, all_active
    ) == expected_match(root, 'one', 'hello', 'world')
    assert decode_observation(
        agf_compiler, second_audio, all_active
    ) == expected_match(root, 'two', 'hello', 'test')

    assert decode_observation(
        agf_compiler, first_audio, leaf_inactive
    ) == NO_MATCH
    assert decode_observation(
        agf_compiler, second_audio, leaf_inactive
    ) == NO_MATCH

    assert decode_observation(
        agf_compiler, first_audio, all_active
    ) == expected_match(root, 'one', 'hello', 'world')
    assert decode_observation(
        agf_compiler, second_audio, all_active
    ) == expected_match(root, 'two', 'hello', 'test')


def test_recursive_instance_activity_is_not_stale(agf_compiler, audio_generator):
    """A recursive call boundary must observe every later activity change."""
    recursive = KaldiRule(
        agf_compiler, 'RecursivePrivate', exported=False)
    initial = recursive.fst.add_state(initial=True)
    recurse = recursive.fst.add_state()
    final = recursive.fst.add_state(final=True)
    recursive.fst.add_arc(initial, final, 'hello')
    recursive.fst.add_arc(initial, recurse, 'again')
    recursive.fst.add_arc(recurse, final, rule_label(recursive))
    recursive.compile()
    recursive.load()

    root = make_sequence_rule(
        agf_compiler, 'RecursiveRoot', rule_label(recursive))
    audio = audio_generator('again hello')
    both = [root.id, recursive.id]

    # Start inactive so both the root call and the recursive call exercise the
    # inactive-to-active direction before the reverse direction is checked.
    assert decode_observation(agf_compiler, audio, [root.id]) == NO_MATCH
    assert decode_observation(
        agf_compiler, audio, both
    ) == expected_match(root, 'again', 'hello')
    assert decode_observation(agf_compiler, audio, [root.id]) == NO_MATCH
    assert decode_observation(
        agf_compiler, audio, both
    ) == expected_match(root, 'again', 'hello')


# Empty-ifst activity normalization cannot be covered through this package's
# public integration API. NativeWFST always starts with a state, and a graph
# with no successful path is rejected by AGF grammar compilation before an
# ActiveGrammarFst can receive it. That invariant needs a lower-level native
# test which constructs ActiveGrammarFst directly with a zero-state ConstFst.


def test_missing_call_target_is_unavailable_until_agf_rebuild(
        agf_compiler, audio_generator):
    """A missing target is a stable unavailable boundary, not inactive state."""
    missing_private_id = 1000
    root = make_sequence_rule(
        agf_compiler,
        'MissingTargetRoot',
        '#nonterm:rule%d' % missing_private_id,
    )
    audio = audio_generator('hello')

    # Do not activate a nonexistent ID: only the loaded root belongs in the
    # activity set. Repeated lookups must reject cleanly rather than trying to
    # create a child instance for the missing nonterminal.
    assert decode_observation(agf_compiler, audio, [root.id]) == NO_MATCH
    assert decode_observation(agf_compiler, audio, []) == NO_MATCH
    assert decode_observation(agf_compiler, audio, [root.id]) == NO_MATCH

    # Loading the referenced rule reconstructs the AGF, at which point the same
    # source call becomes available. Removing it reconstructs the AGF again and
    # restores unavailable semantics.
    child = make_sequence_rule(
        agf_compiler, 'PreviouslyMissingTarget', 'hello', exported=False)
    assert child.id == missing_private_id
    assert decode_observation(
        agf_compiler, audio, [root.id, child.id]
    ) == expected_match(root, 'hello')

    child.close()
    assert decode_observation(agf_compiler, audio, [root.id]) == NO_MATCH


def test_activity_changes_only_between_chunked_utterances(
        agf_compiler, audio_generator):
    """Exercise the documented no-update-while-iterators-are-live contract."""
    parent, child = make_one_level_graph(agf_compiler)
    audio = audio_generator('hello')
    split = (len(audio) // 4) * 2  # Keep the int16 byte boundary aligned.

    agf_compiler.decoder.decode(
        audio[:split], False, [parent.id, child.id])
    agf_compiler.decoder.decode(audio[split:], True, None)
    assert read_observation(agf_compiler) == expected_match(parent, 'hello')

    # Once the utterance has finalized, activity may change safely and must be
    # reflected by the next decoder construction.
    assert decode_observation(
        agf_compiler, audio, [parent.id]
    ) == NO_MATCH
    assert decode_observation(
        agf_compiler, audio, [parent.id, child.id]
    ) == expected_match(parent, 'hello')
