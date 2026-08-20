"""Resolve reproducible release versions and unique development build versions."""

from __future__ import print_function

import argparse
import datetime
import os
import re
import subprocess


_BASE_VERSION_RE = re.compile(r"^__version_base__ = ['\"]([^'\"]+)['\"]", re.M)
_VERSION_RE = re.compile(
    r"^\d+\.\d+\.\d+"
    r"(?:(?:a|b|rc)\d+|\.dev\d+)?"
    r"(?:\+[a-z0-9]+(?:\.[a-z0-9]+)*)?$"
)
_RELEASE_TAG_RE = re.compile(r"^v(\d+\.\d+\.\d+(?:(?:a|b|rc)\d+)?)$")


def read_base_version(root):
    version_path = os.path.join(root, 'kaldi_active_grammar', '_version.py')
    with open(version_path, 'r') as version_file:
        contents = version_file.read()
        match = _BASE_VERSION_RE.search(contents)
    if not match:
        raise RuntimeError("Unable to find __version_base__ in %s" % version_path)
    version = match.group(1)
    if not re.match(r"^\d+\.\d+\.\d+$", version):
        raise RuntimeError("Invalid base version %r in %s" % (version, version_path))
    return version


def validate_version(version, source='version'):
    if not _VERSION_RE.match(version):
        raise RuntimeError("Invalid PEP 440 %s: %r" % (source, version))
    return version


def _git_output(root, *arguments):
    try:
        return subprocess.check_output(
            ['git'] + list(arguments),
            cwd=root,
            stderr=subprocess.DEVNULL,
            universal_newlines=True,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return ''


def _is_git_checkout(root):
    top_level = _git_output(root, 'rev-parse', '--show-toplevel')
    return bool(top_level) and os.path.realpath(top_level) == os.path.realpath(root)


def _tagged_version(root, base_version):
    tags = _git_output(root, 'tag', '--points-at', 'HEAD').splitlines()
    versions = []
    for tag in tags:
        match = _RELEASE_TAG_RE.match(tag)
        if match:
            versions.append(match.group(1))
    if not versions:
        return None
    if len(versions) != 1:
        raise RuntimeError("Expected one release tag at HEAD, found %r" % versions)

    version = validate_version(versions[0], 'tag version')
    if version != base_version and not re.match(
            r"^%s(?:a|b|rc)\d+$" % re.escape(base_version), version):
        raise RuntimeError(
            "Tag version %r does not target base version %r" % (version, base_version))
    if _git_output(root, 'status', '--porcelain'):
        raise RuntimeError("Refusing to create release version %r from a dirty tree" % version)
    return version


def resolve_build_version(root, environ=None, timestamp=None):
    """Return the exact version to put in distribution metadata and package code."""
    environ = os.environ if environ is None else environ
    base_version = read_base_version(root)
    is_git_checkout = _is_git_checkout(root)
    tagged_version = _tagged_version(root, base_version) if is_git_checkout else None

    override = environ.get('KALDIAG_BUILD_VERSION')
    if override:
        override = validate_version(override, 'KALDIAG_BUILD_VERSION')
        if tagged_version is not None and override != tagged_version:
            raise RuntimeError(
                "KALDIAG_BUILD_VERSION %r does not match tag version %r" %
                (override, tagged_version))
        return override
    if tagged_version is not None:
        return tagged_version

    timestamp = timestamp or environ.get('KALDIAG_BUILD_TIMESTAMP')
    if timestamp is None:
        timestamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d%H%M%S')
    if not re.match(r"^\d{14}$", timestamp):
        raise RuntimeError(
            "KALDIAG_BUILD_TIMESTAMP must be a 14-digit UTC timestamp, got %r" % timestamp)

    version = '%s.dev%s' % (base_version, timestamp)
    revision = (_git_output(root, 'rev-parse', '--short=8', 'HEAD').lower()
                if is_git_checkout else '')
    if re.match(r"^[0-9a-f]+$", revision):
        version += '+g%s' % revision
        if _git_output(root, 'status', '--porcelain'):
            version += '.dirty'
    return validate_version(version, 'generated version')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--root', default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        help='repository root (defaults to the parent of this script directory)')
    args = parser.parse_args()
    print(resolve_build_version(args.root))


if __name__ == '__main__':
    main()
