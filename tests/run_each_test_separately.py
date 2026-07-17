"""
Run each test in a separate process.
This is the only reasonable cross-platform way to do this with pytest.
"""

from pathlib import Path
import subprocess
import sys


TESTS_DIR = Path(__file__).resolve().parent


OPTIONS_WITH_VALUE = {
    "-c", "-k", "-m", "-o", "-p", "--basetemp", "--confcutdir",
    "--cov", "--cov-config", "--cov-context", "--cov-fail-under",
    "--cov-report", "--deselect", "--durations", "--durations-min",
    "--ignore", "--ignore-glob", "--import-mode", "--junit-xml",
    "--last-failed-no-failures", "--log-cli-date-format", "--log-cli-format",
    "--log-cli-level", "--log-date-format", "--log-file",
    "--log-file-date-format", "--log-file-format", "--log-file-level",
    "--log-format", "--log-level", "--maxfail", "--override-ini",
    "--rootdir", "--show-capture", "--tb", "--timeout",
}


def options_only(args):
    """Remove positional test selectors after they have been used for collection."""
    options = []
    takes_value = False
    for arg in args:
        if takes_value:
            options.append(arg)
            takes_value = False
        elif arg.startswith("-"):
            options.append(arg)
            takes_value = arg in OPTIONS_WITH_VALUE
    return options


def collect_nodeids(extra):
    # -q with --collect-only prints one nodeid per line
    r = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "--collect-only", *extra],
        cwd=TESTS_DIR,
        capture_output=True, text=True, check=True,
    )
    return [
        ln.strip().split("/")[-1]  # Discard the "tests/" prefix
        for ln in r.stdout.splitlines()
        if ln.strip() and not ln.startswith(("=", "<", "[")) and not (ln.lstrip()[:1].isdigit() and " collected" in ln)
    ]

def main():
    extra = sys.argv[1:]   # e.g. ["tests", "-k", "not slow"]
    nodeids = collect_nodeids(extra)
    options = options_only(extra)
    print(f"Collected {len(nodeids)} nodeids: {nodeids}")
    failed = []
    for nid in nodeids:
        print(f"\n=== {nid} ===")
        rc = subprocess.call([sys.executable, "-m", "pytest", "-q", nid, *options], cwd=TESTS_DIR)
        if rc != 0:
            failed.append(nid)
    print("\n========= DONE =========")
    if failed:
        print(f"\nFailures in {len(failed)} tests:")
        for nid in failed: print(" -", nid)
        sys.exit(1)
    else:
        print("\nAll tests passed.")

if __name__ == "__main__":
    main()
