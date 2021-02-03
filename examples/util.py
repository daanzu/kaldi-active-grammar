import time
import kaldi_active_grammar
from audio import VADAudio

def initialize(model_dir=None, tmp_dir=None, config={}):
    compiler = kaldi_active_grammar.Compiler(model_dir=model_dir, tmp_dir=tmp_dir)
    decoder = compiler.init_decoder(config=config)
    return (compiler, decoder)

def do_recognition(compiler, decoder, print_partial=True, cap_dictation=True):
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
            if print_partial:
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
            if cap_dictation:
                words = [(word.upper() if word_in_dictation else word) for (word, word_in_dictation) in zip(words, words_are_dictation_mask)]
            parsed_output = ' '.join(words)
            print("End of phrase: eer=%.2f conf=%.2f%s, rule %s, %r" %
                (expected_error_rate, confidence, (" [BAD]" if not is_acceptable_recognition else ""), recognized_rule, parsed_output))

            in_phrase = False
