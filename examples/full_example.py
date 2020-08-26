import logging, time
import kaldi_active_grammar

logging.basicConfig(level=20)
model_dir = None  # Default
tmp_dir = None  # Default

##### Set up grammar compiler & decoder

compiler = kaldi_active_grammar.Compiler(model_dir=model_dir, tmp_dir=tmp_dir)
# compiler.fst_cache.invalidate()

top_fst = compiler.compile_top_fst()
dictation_fst_file = compiler.dictation_fst_filepath
decoder = kaldi_active_grammar.KaldiAgfNNet3Decoder(model_dir=compiler.model_dir, tmp_dir=compiler.tmp_dir,
    top_fst_file=top_fst.filepath, dictation_fst_file=dictation_fst_file, save_adaptation_state=False,
    config={},)
compiler.decoder = decoder

##### Set up a rule

rule = kaldi_active_grammar.KaldiRule(compiler, 'TestRule')
fst = rule.fst

# Construct grammar in a FST
previous_state = fst.add_state(initial=True)
for word in "i will order the".split():
    state = fst.add_state()
    fst.add_arc(previous_state, state, word)
    if word == 'the':
        # 'the' is optional, so we also allow an epsilon (silent) arc
        fst.add_arc(previous_state, state, None)
    previous_state = state
final_state = fst.add_state(final=True)
for word in ['egg', 'bacon', 'sausage']: fst.add_arc(previous_state, final_state, word)
fst.add_arc(previous_state, final_state, 'spam', weight=8)  # 'spam' is much more likely
fst.add_arc(final_state, previous_state, None)  # Loop back, with an epsilon (silent) arc

rule.compile()
rule.load()

##### You could add many more rules...

##### Perform decoding on live, real-time audio from microphone

from audio import VADAudio
audio = VADAudio()
audio_iterator = audio.vad_collector(nowait=True)
print("Listening...")

in_phrase = False
for block in audio_iterator:

    if block is False:
        # No audio block available
        time.sleep(0.001)

    elif block is not None:
        if not in_phrase:
            # Start of phrase
            kaldi_rules_activity = [True]  # A bool for each rule
            in_phrase = True
        else:
            # Ongoing phrase
            kaldi_rules_activity = None  # Irrelevant

        decoder.decode(block, False, kaldi_rules_activity)
        output, info = decoder.get_output()
        print("Partial phrase: %r" % (output,))
        recognized_rule, words, words_are_dictation_mask, in_dictation = compiler.parse_partial_output(output)

    else:
        # End of phrase
        decoder.decode(b'', True)
        output, info = decoder.get_output()
        expected_error_rate = info.get('expected_error_rate', float('nan'))
        confidence = info.get('confidence', float('nan'))

        recognized_rule, words, words_are_dictation_mask = compiler.parse_output(output)
        is_acceptable_recognition = bool(recognized_rule)
        parsed_output = ' '.join(words)
        print("End of phrase: eer=%.2f conf=%.2f%s, rule %s, %r" %
            (expected_error_rate, confidence, (" [BAD]" if not is_acceptable_recognition else ""), recognized_rule, parsed_output))

        in_phrase = False
