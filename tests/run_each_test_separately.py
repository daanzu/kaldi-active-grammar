"""
Run each test in a separate process.
This is the only reasonable cross-platform way to do this with pytest.
"""

import sys, subprocess

def collect_nodeids(extra):
    # -q with --collect-only prints one nodeid per line
    r = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "--collect-only", *extra],
        capture_output=True, text=True, check=True
    )
    return [
        ln.strip().split("/")[-1]  # Discard the "tests/" prefix
        for ln in r.stdout.splitlines()
        if ln.strip() and not ln.startswith(("=", "<", "[")) and not "collected in" in ln
    ]

def main():
    extra = sys.argv[1:]   # e.g. ["tests", "-k", "not slow"]
    nodeids = collect_nodeids(extra)
    print(f"Collected {len(nodeids)} nodeids: {nodeids}")
    failed = []
    for nid in nodeids:
        print(f"\n=== {nid} ===")
        rc = subprocess.call([sys.executable, "-m", "pytest", "-q", nid, *extra])
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
