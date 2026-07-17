
import re

def test_import_and_version():
    import kaldi_active_grammar as kag
    assert isinstance(kag.__version__, str)
    assert kag.__version__.strip() != ""

    version_pattern = r'^\d+\.\d+\.\d+(?:[-+].+)?$'
    assert re.match(version_pattern, kag.__version__), f"Version '{kag.__version__}' does not match semantic versioning format"
