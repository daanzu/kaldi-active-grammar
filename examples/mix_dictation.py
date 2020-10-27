import kaldi_active_grammar

if __name__ == '__main__':
    import util
    compiler, decoder = util.initialize()

##### Set up a rule mixing strict commands with free dictation

rule = kaldi_active_grammar.KaldiRule(compiler, 'TestRule')
fst = rule.fst

dictation_nonterm = '#nonterm:dictation'
end_nonterm = '#nonterm:end'

# Optional preface
previous_state = fst.add_state(initial=True)
next_state = fst.add_state()
fst.add_arc(previous_state, next_state, 'cap')
fst.add_arc(previous_state, next_state, None)  # Optionally skip, with an epsilon (silent) arc

# Required free dictation
previous_state = next_state
extra_state = fst.add_state()
next_state = fst.add_state()
# These two arcs together (always use together) will recognize one or more words of free dictation (but not zero):
fst.add_arc(previous_state, extra_state, dictation_nonterm)
fst.add_arc(extra_state, next_state, None, end_nonterm)

# Loop repetition, alternating between a group of alternatives and more free dictation
previous_state = next_state
next_state = fst.add_state()
for word in ['period', 'comma', 'colon']:
    fst.add_arc(previous_state, next_state, word)
extra_state = fst.add_state()
next_state = fst.add_state()
fst.add_arc(next_state, extra_state, dictation_nonterm)
fst.add_arc(extra_state, next_state, None, end_nonterm)
fst.add_arc(next_state, previous_state, None)  # Loop back, with an epsilon (silent) arc
fst.add_arc(previous_state, next_state, None)  # Optionally skip, with an epsilon (silent) arc

# Finish up
final_state = fst.add_state(final=True)
fst.add_arc(next_state, final_state, None)

rule.compile()
rule.load()

# Decode
if __name__ == '__main__':
    util.do_recognition(compiler, decoder)
