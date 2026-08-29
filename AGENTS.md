# Agent Notes

Keep this file limited to repository-specific instructions. See `README.md`, `BUILDING.md`, and `TESTING.md` for project documentation.

## Testing

- Use the existing project `.venv` for Python commands and tests when available.
- Run a focused test first: `just test <pytest-args>`.
- Run the full default suite with `just test`. It excludes `prolonged` and `stress` tests.
- If test assets or the environment are missing, run `just setup-tests` and `just setup-tests-venv`.
- Let long-running tests finish without frequent polling; report failures or the final summary rather than progress output.

## Native Kaldi dependency

Native sources are developed in the sibling `../kaldi-fork-active-grammar` checkout. `kaldi-native-revision.txt` records the exact compatible commit.

- Inspect or prepare the sibling checkout with `just native-status`, `just native-sync`, and `just native-verify`.
- After changing native code, rebuild it with `just build-linux-develop`.
- After committing a native change, update the lock with `just native-lock`.
- Use the relevant `just *-develop` recipes for native development; consult `BUILDING.md` for setup details.

## Packaging

The project is wheel-only because distributions must bundle native code; do not add or rely on source-distribution support.
