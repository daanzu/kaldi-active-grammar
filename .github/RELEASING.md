# Release Process

## Quick Summary

1. **Prepare**: Update version in `__init__.py`, update `CHANGELOG.md`, run tests
2. **Tag Fork First**: Push all changes and tag `kag-vX.Y.Z` in kaldi-fork repo (MUST be done first!)
3. **Tag Main**: Create and push git tag `vX.Y.Z` in this repo to trigger builds
4. **Build**: Automated GitHub Actions builds wheels for all platforms
5. **Release**: Create GitHub release with changelog, upload wheel artifacts and models
6. **Publish**: Download wheels from artifacts, upload to PyPI with twine
7. **Finalize**: Bump to next dev version, announce release

---

## Detailed Release Process

### Overview

This is a **duorepo** (2 separate repos used together):
- Main repo: `daanzu/kaldi-active-grammar` (Python package)
- Native binaries repo: `daanzu/kaldi-fork-active-grammar` (Kaldi C++ fork)

**⚠️ IMPORTANT: The fork repo MUST always be pushed first before this repo for any changes!** The build process in this repo checks out code from the fork repo, so the fork must contain all necessary changes before triggering builds here.

### 1. Pre-Release Preparation

#### Update Version Number

Edit `kaldi_active_grammar/__init__.py`:
```python
__version__ = 'X.Y.Z'  # Change from previous version
```

Optionally update `REQUIRED_MODEL_VERSION` if model changes.

#### Update CHANGELOG.md

Add new version section following Keep a Changelog format:
```markdown
## [X.Y.Z](release-url) - YYYY-MM-DD - Changes: [KaldiAG](compare-url) [KaldiFork](compare-url)

### Added
- New features

### Changed
- Changes to existing functionality

### Fixed
- Bug fixes

### Removed
- Removed features
```

Include comparison links for both repos (KaldiAG and KaldiFork).

#### Run Tests

```bash
just test
```

#### Commit Changes

```bash
git add kaldi_active_grammar/__init__.py CHANGELOG.md
git commit -m "Release vX.Y.Z"
```

### 2. Create Git Tags

**⚠️ CRITICAL ORDER: Tag and push the fork repo FIRST, then this repo!**

#### Tag the Kaldi Fork Repo (DO THIS FIRST!)

In the `daanzu/kaldi-fork-active-grammar` repo:

1. Ensure all native code changes are committed and pushed
2. Create and push the tag:
   ```bash
   git tag kag-vX.Y.Z  # Note the 'kag-' prefix matching the version
   git push origin kag-vX.Y.Z
   ```

This is crucial because the build process in this repo will check out code from the fork using this tag.

#### Tag This Repo (DO THIS SECOND!)

Only after the fork repo tag is pushed:

```bash
git tag vX.Y.Z
git push origin vX.Y.Z
```

Pushing this tag will trigger the GitHub Actions build workflow, which will pull the native code from the fork repo using the `kag-vX.Y.Z` tag.

### 3. Automated Build Process (GitHub Actions)

When you push a tag, the CI automatically:

#### Detects the Tag

Sets `KALDI_BRANCH=kag-vX.Y.Z` for tagged commits, or uses current branch name for non-tagged commits.

#### Builds Native Binaries

**Linux** (`build-linux` job):
- Uses dockcross/manylinux2010 for compatibility
- Compiles Kaldi C++ code with CMake
- Runs auditwheel for wheel repair

**Windows** (`build-windows` job):
- Uses Visual Studio 2022/2025
- Installs Intel MKL
- Compiles OpenFST and Kaldi with MSBuild

**macOS ARM** (`build-macos-arm` job):
- For Apple Silicon (M1/M2/etc)
- Uses delocate for wheel repair

**macOS Intel** (`build-macos-intel` job):
- For x86_64 Macs
- Uses delocate for wheel repair

#### Caches Native Binaries

Caches compiled Kaldi binaries by commit hash to speed up rebuilds.

#### Creates Python Wheels

- Packages include all native binaries
- Platform-specific wheels: `py3-none-{platform}`
- Uses `setup.py` with scikit-build (or `KALDIAG_BUILD_SKIP_NATIVE=1` for packaging only)

#### Tests All Wheels

`test-wheels` job runs on multiple OS/Python version combinations.

#### Merges Wheel Artifacts

`merge-wheels` job combines all platform wheels into single artifact named `wheels`.

### 4. Manual Workflow Trigger (Optional)

You can also trigger builds manually:

```bash
# Using GitHub CLI
gh workflow run build.yml --ref master
# Or specific ref:
gh workflow run build.yml --ref vX.Y.Z

# Or via Justfile:
just trigger-build master
```

### 5. Create GitHub Release

1. **Navigate to GitHub Releases page**
   - https://github.com/daanzu/kaldi-active-grammar/releases

2. **Create new release**:
   - Tag: `vX.Y.Z` (select existing tag)
   - Title: `vX.Y.Z` or descriptive name
   - Description: Copy relevant section from `CHANGELOG.md` or use template from `.github/release_notes.md`

3. **Download wheel artifacts** from successful build workflow:
   - Go to Actions → Build workflow → successful run
   - Download artifact named `wheels` (merged) or individual `wheels-{platform}`

4. **Upload wheels to release**:
   - Upload all `.whl` files from the artifacts

5. **Upload additional assets** (if applicable):
   - Pre-trained Kaldi models (if updated)
   - WinPython distributions (if prepared):
     - `kaldi-dragonfly-winpython` (stable)
     - `kaldi-dragonfly-winpython-dev` (development)
     - `kaldi-caster-winpython-dev` (with Caster)

6. **Publish the release**

### 6. Publish to PyPI

The process is currently **manual** (not automated in workflow).

#### Download Wheel Artifacts

Download the `wheels` artifact from the successful GitHub Actions build.

#### Upload to PyPI

You'll need PyPI credentials (entered interactively or configured in `~/.pypirc` or via environment variables).

```bash
# Test PyPI first (recommended):
uvx twine upload --repository testpypi wheels/*
# Production PyPI:
uvx twine upload wheels/*
```

Or:

```bash
pip install twine
# Test PyPI first (recommended):
twine upload --repository testpypi wheels/*
# Production PyPI:
twine upload wheels/*
```

#### Verify on PyPI

- Check https://pypi.org/project/kaldi-active-grammar/
- Verify all platforms are present
- Test installation:
  ```bash
  pip install kaldi-active-grammar==X.Y.Z
  ```

### 7. Post-Release Tasks

#### Bump Version for Development

Update `__version__` in `kaldi_active_grammar/__init__.py` to next dev version:
```python
__version__ = 'X.Y.Z.dev0'  # or 'X.Y+1.0.dev0'
```

Commit the change:
```bash
git add kaldi_active_grammar/__init__.py
git commit -m "Bump version to X.Y.Z.dev0"
git push
```

#### Announce Release

- Update documentation/README if needed
- Update Dragonfly documentation if relevant
- Post on relevant forums/communities
    - Notify on Gitter:
        - https://app.gitter.im/#/room/#dragonfly2:matrix.org
        - https://gitter.im/kaldi-active-grammar/community

---

## Key Files in Release Process

| File | Purpose |
|------|---------|
| `kaldi_active_grammar/__init__.py:8` | Version source |
| `kaldi_active_grammar/__init__.py:10` | Required model version |
| `CHANGELOG.md` | Release notes and history |
| `.github/workflows/build.yml` | CI build configuration |
| `.github/workflows/tests.yml` | CI test configuration |
| `setup.py` | Package build configuration |
| `pyproject.toml` | Build system requirements |
| `Justfile` | Build and test tasks |
| `.github/release_notes.md` | Release notes template |

---

## Environment Variables

| Variable | Purpose |
|----------|---------|
| `KALDIAG_BUILD_SKIP_NATIVE=1` | Skip native compilation, just package |
| `KALDI_BRANCH` | Which Kaldi fork branch/tag to build from (auto-detected from git tag) |
| `MKL_URL` | Optional Intel MKL download URL (mostly disabled now) |

---

## Development vs Release Versions

- **Dev versions**: `setup.py` auto-appends timestamp to `X.Y.Z.dev0` versions
  - Example: `3.1.0.dev20251031123456`
- **Release versions**: Clean `X.Y.Z` semantic version
  - Example: `3.1.0`
- Build process differentiates based on git tags

---

## Troubleshooting

### Build fails on one platform

- Check the GitHub Actions logs for that specific job
- Native binaries are cached, so may need to invalidate cache if Kaldi fork changed
- Ensure the `kag-vX.Y.Z` tag exists in kaldi-fork-active-grammar repo

### Tests fail

- Run tests locally: `just test`
- Check if model needs to be updated
- Verify test data is downloaded: `just setup-tests`

### PyPI upload fails

- Verify credentials in `~/.pypirc`
- Check wheel filenames are correct
- Ensure version doesn't already exist on PyPI
- Try test PyPI first

### Wheels missing for a platform

- Check if that build job completed successfully
- Look for cache issues
- Verify platform is included in build matrix

### Version mismatch

- Ensure git tag matches `__version__` in `__init__.py`
- Check that both repos are tagged (main repo: `vX.Y.Z`, fork: `kag-vX.Y.Z`)
- Verify `CHANGELOG.md` has correct version
