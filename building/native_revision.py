"""Read and validate the Kaldi fork revision locked by this repository."""

from __future__ import print_function

import argparse
import os
import re
import subprocess
import sys


LOCK_FILENAME = "kaldi-native-revision.txt"
_FULL_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")


def validate_native_revision(revision, source="native revision"):
    """Return revision if it is a full lowercase commit hash."""
    revision = revision.strip()
    if not _FULL_COMMIT_RE.match(revision):
        raise RuntimeError(
            "%s must contain exactly one full, lowercase 40-character Git commit hash"
            % source
        )
    return revision


def read_native_revision(repository_root=None):
    """Return the full native commit hash recorded in the lock file."""
    if repository_root is None:
        repository_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    lock_path = os.path.join(repository_root, LOCK_FILENAME)
    try:
        with open(lock_path, "r") as lock_file:
            revision = lock_file.read().strip()
    except OSError as error:
        raise RuntimeError("Unable to read native revision lock %s: %s" % (lock_path, error))

    return validate_native_revision(revision, lock_path)


def resolve_native_revision(repository_root=None, environ=None):
    """Return a validated explicit override or the repository lock."""
    if environ is None:
        environ = os.environ
    override = environ.get("KALDI_REVISION")
    if override:
        return validate_native_revision(override, "KALDI_REVISION")
    return read_native_revision(repository_root)


def checkout_revision(checkout_path):
    return subprocess.check_output(
        ["git", "-C", checkout_path, "rev-parse", "HEAD"],
        universal_newlines=True,
    ).strip()


def checkout_is_dirty(checkout_path):
    output = subprocess.check_output(
        ["git", "-C", checkout_path, "status", "--porcelain"],
        universal_newlines=True,
    )
    return bool(output.strip())


def verify_checkout(checkout_path, repository_root=None, require_clean=False):
    """Raise RuntimeError unless a checkout is at the locked native revision."""
    expected = read_native_revision(repository_root)
    try:
        actual = checkout_revision(checkout_path)
    except (OSError, subprocess.CalledProcessError) as error:
        raise RuntimeError("Unable to inspect native checkout %s: %s" % (checkout_path, error))
    if actual != expected:
        raise RuntimeError(
            "Native checkout revision mismatch: expected %s, found %s in %s"
            % (expected, actual, checkout_path)
        )
    if require_clean and checkout_is_dirty(checkout_path):
        raise RuntimeError("Native checkout has uncommitted changes: %s" % checkout_path)
    return actual


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--verify-checkout",
        metavar="PATH",
        help="verify that PATH is at the locked native commit",
    )
    parser.add_argument(
        "--require-clean",
        action="store_true",
        help="also reject an unclean checkout when verifying",
    )
    args = parser.parse_args(argv)

    try:
        if args.verify_checkout:
            revision = verify_checkout(
                args.verify_checkout, require_clean=args.require_clean)
        else:
            revision = read_native_revision()
    except (RuntimeError, OSError, subprocess.CalledProcessError) as error:
        print("error: %s" % error, file=sys.stderr)
        return 1

    print(revision)
    return 0


if __name__ == "__main__":
    sys.exit(main())
