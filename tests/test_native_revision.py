import subprocess

import pytest

from building.native_revision import (
    read_native_revision,
    resolve_native_revision,
    verify_checkout,
)


REVISION = "0123456789abcdef0123456789abcdef01234567"


def write_lock(root, value):
    (root / "kaldi-native-revision.txt").write_text(value)


def git(checkout, *args):
    subprocess.check_call(["git", "-C", str(checkout)] + list(args))


def test_read_native_revision_accepts_full_lowercase_hash(tmp_path):
    write_lock(tmp_path, REVISION + "\n")

    assert read_native_revision(str(tmp_path)) == REVISION


@pytest.mark.parametrize("value", [
    "",
    "01234567",
    "0123456789ABCDEF0123456789ABCDEF01234567",
    REVISION + "\nextra\n",
])
def test_read_native_revision_rejects_invalid_lock(tmp_path, value):
    write_lock(tmp_path, value)

    with pytest.raises(RuntimeError, match="full, lowercase 40-character"):
        read_native_revision(str(tmp_path))


def test_resolve_native_revision_validates_override(tmp_path):
    write_lock(tmp_path, REVISION + "\n")
    override = "89abcdef0123456789abcdef0123456789abcdef"

    assert resolve_native_revision(str(tmp_path), {"KALDI_REVISION": override}) == override
    with pytest.raises(RuntimeError, match="KALDI_REVISION"):
        resolve_native_revision(str(tmp_path), {"KALDI_REVISION": "develop"})


def test_verify_checkout_checks_revision_and_cleanliness(tmp_path):
    checkout = tmp_path / "native"
    checkout.mkdir()
    git(checkout, "init")
    git(checkout, "config", "user.name", "Test")
    git(checkout, "config", "user.email", "test@example.com")
    (checkout / "tracked").write_text("first\n")
    git(checkout, "add", "tracked")
    git(checkout, "commit", "-m", "Initial")
    revision = subprocess.check_output(
        ["git", "-C", str(checkout), "rev-parse", "HEAD"],
        universal_newlines=True,
    ).strip()
    write_lock(tmp_path, revision + "\n")

    assert verify_checkout(str(checkout), str(tmp_path), require_clean=True) == revision

    (checkout / "tracked").write_text("changed\n")
    with pytest.raises(RuntimeError, match="uncommitted changes"):
        verify_checkout(str(checkout), str(tmp_path), require_clean=True)

    write_lock(tmp_path, REVISION + "\n")
    with pytest.raises(RuntimeError, match="revision mismatch"):
        verify_checkout(str(checkout), str(tmp_path))
