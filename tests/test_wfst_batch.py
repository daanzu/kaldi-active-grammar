import math

import pytest

from kaldi_active_grammar import Compiler, KaldiError, NativeWFST
from kaldi_active_grammar.ffi import _ffi
from tests.helpers import missing_laf_model_files


@pytest.fixture(params=['agf-direct', 'laf'], ids=['agf', 'laf'])
def initialized_native_wfst(change_to_test_dir, request):
    if request.param == 'laf':
        missing = missing_laf_model_files()
        if missing:
            pytest.skip('lookahead test model is missing: %s' % ', '.join(missing))
    with Compiler(framework=request.param, cache_fsts=False) as compiler:
        yield compiler


def test_batched_arcs_match_scalar_hash(initialized_native_wfst):
    scalar = NativeWFST()
    batched = NativeWFST()
    try:
        scalar_initial = scalar.add_state(initial=True)
        scalar_middle = scalar.add_state()
        scalar_final = scalar.add_state(final=True)
        batched_initial = batched.add_state(initial=True)
        batched_middle = batched.add_state()
        batched_final = batched.add_state(final=True)

        def add_native_scalar(src_state, dst_state, label, olabel=None, weight=1):
            if label is None:
                label = scalar.eps
            if olabel is None:
                olabel = label
            native_weight = -math.log(weight) if weight != 0 else scalar.zero
            result = scalar._lib.fst__add_arc(
                scalar._get_raw_native_obj(), src_state, dst_state,
                scalar.word_to_ilabel_map[label], scalar.word_to_olabel_map[olabel],
                native_weight,
            )
            assert result
            scalar.num_arcs += 1

        add_native_scalar(scalar_initial, scalar_middle, None)
        add_native_scalar(scalar_middle, scalar_middle, 'hello', weight=0.25)
        add_native_scalar(scalar_middle, scalar_final, None, '#nonterm:end')
        batched.add_arcs([
            (batched_initial, batched_middle, None),
            (batched_middle, batched_middle, 'hello', None, 0.25),
            (batched_middle, batched_final, None, '#nonterm:end'),
        ])

        assert batched.num_arcs == scalar.num_arcs
        assert batched.compute_hash() == scalar.compute_hash()
    finally:
        scalar.close()
        batched.close()


def test_empty_batch_is_a_noop(initialized_native_wfst):
    fst = NativeWFST()
    try:
        original_num_arcs = fst.num_arcs
        fst.add_arcs([])
        assert fst.num_arcs == original_num_arcs
    finally:
        fst.close()


def test_invalid_state_rejects_entire_batch(initialized_native_wfst):
    fst = NativeWFST()
    try:
        final_state = fst.add_state(final=True)
        before_hash = fst.compute_hash()
        labels = [fst.word_to_ilabel_map['hello'], fst.word_to_ilabel_map['world']]
        result = fst._lib.fst__add_arcs(
            fst._get_raw_native_obj(), 2,
            _ffi.new('int32_t[]', [0, 9999]),
            _ffi.new('int32_t[]', [final_state, final_state]),
            _ffi.new('int32_t[]', labels),
            _ffi.new('int32_t[]', labels),
            _ffi.new('float[]', [0.0, 0.0]),
        )
        assert not result
        assert fst.num_arcs == 0
        assert fst.compute_hash() == before_hash
    finally:
        fst.close()


def test_universal_grammar_uses_batched_arcs(initialized_native_wfst):
    rule = initialized_native_wfst.compile_universal_grammar(['hello', 'world'])
    try:
        assert rule.compiled
        assert rule.fst.num_arcs == 3  # Two word loops and the implicit initial arc.
    finally:
        rule.close()


def test_scalar_arc_flushes_before_native_read(initialized_native_wfst):
    fst = NativeWFST()
    try:
        initial_state = fst.add_state(initial=True)
        final_state = fst.add_state(final=True)
        fst.add_arc(initial_state, final_state, 'hello')

        assert len(fst._pending_arc_src_state_ids) == 1
        assert fst.num_arcs == 2  # The pending word arc and implicit initial arc.
        assert fst.has_path()
        assert not fst._pending_arc_src_state_ids
    finally:
        fst.close()


def test_scalar_arcs_flush_at_batch_threshold(initialized_native_wfst):
    fst = NativeWFST()
    fst.arc_batch_size = 2
    try:
        initial_state = fst.add_state(initial=True)
        final_state = fst.add_state(final=True)
        fst.add_arc(initial_state, final_state, 'hello')
        assert len(fst._pending_arc_src_state_ids) == 1

        fst.add_arc(initial_state, final_state, 'world')
        assert not fst._pending_arc_src_state_ids
        assert fst.num_arcs == 3
        assert fst.has_path()
    finally:
        fst.close()


def test_adding_initial_state_flushes_pending_arcs(initialized_native_wfst):
    fst = NativeWFST()
    try:
        destination = fst.add_state()
        fst.add_arc(0, destination, 'hello')
        assert len(fst._pending_arc_src_state_ids) == 1

        fst.add_state(initial=True)
        assert not fst._pending_arc_src_state_ids
    finally:
        fst.close()


def test_clear_discards_pending_arcs(initialized_native_wfst):
    fst = NativeWFST()
    final_state = fst.add_state(final=True)
    fst.add_arc(0, final_state, 'hello')
    assert len(fst._pending_arc_src_state_ids) == 1

    fst.clear()
    try:
        assert not fst._pending_arc_src_state_ids
        assert fst.num_states == 1
        assert fst.num_arcs == 0
        assert fst.filename is None
    finally:
        fst.close()


def test_closed_fst_rejects_buffered_mutation(initialized_native_wfst):
    fst = NativeWFST()
    fst.close()

    with pytest.raises(KaldiError, match='closed native WFST'):
        fst.add_arc(0, 0, 'hello')
