"""Released-wheel compatibility shim for the long-term stress harness.

``longterm.py`` is written against the current (unreleased) kaldi-active-grammar
API.  To let the identical workload run against a released wheel -- so a run can
be compared with ``--baseline-json`` across versions -- every package call whose
shape changed goes through an adapter built by :func:`build_adapter`.  Nothing
else in the harness touches the changed API surface, so this file plus the
``self.api`` calls in ``longterm.py`` are the whole shim: when the oldest
supported release carries the current API, delete this module and inline
:class:`CurrentApi` back into direct package calls.

The released family (v3.0.0, v3.1.0, v3.2.0 -- all identical for our purposes)
differs from current as follows:

======================================  ========================================
current                                 released (v3.0.0 - v3.2.0)
======================================  ========================================
``KaldiRule.close()``                   ``KaldiRule.destroy()``, which also
                                        renumbers every higher rule id downwards
``Compiler.close()``, ``_closed``       absent; the decoder and the AGF compiler
                                        are destroyed individually
``Compiler._kaldi_rule_id_allocator``   ``Compiler.num_kaldi_rules``
activity = iterable of rule ids         activity = positional ``bool`` mask
                                        indexed by ``KaldiRule.id``
``decoder.mimic()``                     absent
``framework='laf'``                     predates the ActiveReplaceFst rework
rule ids stable for a rule's lifetime   ids are dense and double as the decoder's
                                        grammar-fst index, so rules must be
                                        loaded in id order: a mix of lazy and
                                        eager loading trips an assertion during
                                        population build
======================================  ========================================

Only AGF is supported on released wheels; LAF is reported as unsupported rather
than silently measured against a framework that has since been reworked.
"""

from __future__ import annotations

AGF_FRAMEWORKS = ('agf', 'agf-direct')


class UnsupportedByPackage(Exception):
    """The installed package cannot run the requested workload."""


class CurrentApi:
    """Adapter for the in-development API this harness is written against."""

    name = 'current'
    supports_mimic = True
    requires_uniform_lazy_loading = False

    def __init__(self, version, path):
        self.version = version
        self.path = path

    @property
    def identity(self):
        """Version plus API family.

        An unreleased build still carries the last release's ``__version__``, so
        the family is what separates it from the wheel of that same version.
        """
        return '%s [%s]' % (self.version, self.name)

    def describe(self):
        return 'kaldi_active_grammar %s from %s' % (self.identity, self.path)

    def supports_framework(self, framework):
        return framework in AGF_FRAMEWORKS + ('laf',)

    def activity(self, compiler, active_rule_ids):
        return active_rule_ids

    def close_rule(self, rule):
        rule.close()

    def close_compiler(self, compiler):
        compiler.close()

    def compiler_is_open(self, compiler):
        return not compiler._closed

    def allocated_rule_count(self, compiler):
        return compiler._kaldi_rule_id_allocator.num_rules

    def live_rule_count(self, compiler):
        return len(compiler.kaldi_rule_by_id_dict)


class ReleasedApi(CurrentApi):
    """Adapter for released wheels v3.0.0 - v3.2.0 (AGF only)."""

    name = 'released-3.0-3.2'
    supports_mimic = False
    # A rule's id must equal the grammar-fst index the decoder hands back when
    # it is loaded, so rules have to reach the decoder in creation order.  All
    # rules lazy (loaded from the queue in instantiation order) or none lazy
    # (loaded as created) both hold; interleaving the two does not.
    requires_uniform_lazy_loading = True

    def supports_framework(self, framework):
        return framework in AGF_FRAMEWORKS

    def activity(self, compiler, active_rule_ids):
        """Convert a set of rule ids into the positional Boolean mask.

        Rule ids are dense and 0-based in this family (``id`` doubles as the
        decoder's grammar-fst index), so the mask covers every allocated rule;
        an empty ``active_rule_ids`` yields an all-inactive mask rather than the
        zero-length array the native side would read past.
        """
        if active_rule_ids is None:
            return None
        mask = [False] * compiler.num_kaldi_rules
        for rule_id in active_rule_ids:
            if not 0 <= rule_id < len(mask):
                raise UnsupportedByPackage(
                    'rule id %d outside the %d allocated rules; the released positional '
                    'activity mask cannot represent it' % (rule_id, len(mask)))
            mask[rule_id] = True
        return mask

    def close_rule(self, rule):
        rule.destroy()

    def close_compiler(self, compiler):
        """Stand in for the absent ``Compiler.close()``.

        Releases the two native objects a Compiler owns, in the order the
        current implementation uses, and marks it closed for
        :meth:`compiler_is_open`.
        """
        if getattr(compiler, '_closed_by_shim', False):
            return
        compiler._closed_by_shim = True
        decoder = getattr(compiler, 'decoder', None)
        if decoder is not None:
            decoder.destroy()
            compiler.decoder = None
        agf_compiler = getattr(compiler, '_agf_compiler', None)
        if agf_compiler is not None:
            agf_compiler.destroy()
            compiler._agf_compiler = None

    def compiler_is_open(self, compiler):
        return not getattr(compiler, '_closed_by_shim', False)

    def allocated_rule_count(self, compiler):
        return compiler.num_kaldi_rules


def build_adapter():
    """Return the adapter matching the installed kaldi_active_grammar package.

    Detection is by feature probe rather than version parsing, so unreleased
    builds and local wheels are classified by what they actually expose.
    ``KaldiRule.close()`` and rule-id activity landed together, so one probe
    settles the whole family.
    """
    import kaldi_active_grammar
    from kaldi_active_grammar import KaldiRule

    version = getattr(kaldi_active_grammar, '__version__', 'unknown')
    path = getattr(kaldi_active_grammar, '__file__', 'unknown')
    api_class = CurrentApi if hasattr(KaldiRule, 'close') else ReleasedApi
    return api_class(version, path)


def check_workload_supported(api, framework, decode_mode, lazy_fraction):
    """Raise :class:`UnsupportedByPackage` if this package cannot run the workload.

    Checked before the population is built, so an unsupported knob combination
    reports what to change instead of failing deep inside the package.
    """
    if not api.supports_framework(framework):
        raise UnsupportedByPackage(
            "framework %r is not supported by %s (released wheels predate the "
            "LAF ActiveReplaceFst rework; use an AGF framework)" % (framework, api.describe()))
    if decode_mode == 'mimic' and not api.supports_mimic:
        raise UnsupportedByPackage(
            "decode_mode 'mimic' is not supported by %s (the decoder gained mimic() "
            "after v3.2.0); use --decode-mode audio" % api.describe())
    if api.requires_uniform_lazy_loading and 0.0 < lazy_fraction < 1.0:
        raise UnsupportedByPackage(
            "lazy_fraction %g mixes lazy and eager rule loading, which %s cannot do "
            "(its rule ids double as decoder grammar-fst indexes, so rules must load "
            "in creation order); use --lazy-fraction 1 or 0, and pass the same value "
            "to the run you are comparing against" % (lazy_fraction, api.describe()))
