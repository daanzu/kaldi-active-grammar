
setup-linux-develop kaldi_dir:
	ln -sr {{kaldi_dir}}/tools/openfst/bin/fstarcsort kaldi_active_grammar/exec/linux/
	ln -sr {{kaldi_dir}}/tools/openfst/bin/fstcompile kaldi_active_grammar/exec/linux/
	ln -sr {{kaldi_dir}}/tools/openfst/bin/fstinfo kaldi_active_grammar/exec/linux/
	ln -sr {{kaldi_dir}}/src/fstbin/fstaddselfloops kaldi_active_grammar/exec/linux/
	ln -sr {{kaldi_dir}}/src/dragonfly/libkaldi-dragonfly.so kaldi_active_grammar/exec/linux/
	ln -sr {{kaldi_dir}}/src/dragonflybin/compile-graph-agf kaldi_active_grammar/exec/linux/
