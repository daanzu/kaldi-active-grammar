"""Match text against a loaded grammar without decoding audio."""

import kaldi_active_grammar


def make_rule(compiler, name, phrase):
    rule = kaldi_active_grammar.KaldiRule(compiler, name)
    fst = rule.fst

    words = phrase.split()
    if not words:
        raise ValueError("phrase must contain at least one word")

    initial_state = fst.add_state(initial=True)
    previous_state = initial_state
    for index, word in enumerate(words):
        next_state = fst.add_state(final=index == len(words) - 1)
        fst.add_arc(previous_state, next_state, word)
        previous_state = next_state

    rule.compile()
    rule.load()
    return rule


def main():
    # Supply model_dir and tmp_dir here when they are not in their default locations.
    with kaldi_active_grammar.Compiler() as compiler:
        compiler.init_decoder()
        rule = make_rule(compiler, 'Greeting', 'hello world')

        for text in ('hello world', 'goodbye'):
            output = compiler.mimic(text, [rule.id])
            if output is None:
                print('%r: no match' % text)
                continue

            matched_rule, words, words_are_dictation_mask = compiler.parse_output(output)
            print('%r: rule=%r words=%r dictation=%r' % (
                text, matched_rule.name, words, words_are_dictation_mask))


if __name__ == '__main__':
    main()
