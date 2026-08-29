# Historical Python/native revision pairings

`kaldi-active-grammar` and `kaldi-fork-active-grammar` were historically developed as a duorepo. Before `kaldi-native-revision.txt` was added, builds usually selected the native source through a matching tag or a moving branch. This record reconstructs a native pairing for every durable Python commit available locally, not only releases.

The current lock file remains authoritative for new builds. This history is primarily for archaeology, bisecting, and rebuilding old states. The release table below contains the strongest historical anchors; the [complete commit map](native-revision-commit-map.csv) contains every commit reachable from local branches, remote-tracking branches, and tags.

> **Point-in-time report:** This document records repository state when it was prepared and is not intended to be kept up to date as development continues or the native lock changes.

## Evidence levels

- **Lock**: the Python commit records a full native commit in `kaldi-native-revision.txt`.
- **Selector + tag**: the Python build selected `kag-v<version>` or an explicit SHA, and that native tag or SHA survives.
- **Artifact + tag**: a published manylinux wheel contains the same abbreviated Kaldi revision as a surviving native release tag.
- **Artifact**: a published manylinux wheel contains an abbreviated Kaldi revision, resolved to a full commit through the native repository and GitHub commit API.
- **Correlated**: non-release commits in both repositories implement the same interface or feature change, with matching subjects and nearby timestamps.
- **Inferred-compatible**: no exact checkout survives; the candidate is anchored to the nearest descendant release, nearest ancestor release, or current locked snapshot known to contain that Python history.
- **Inferred**: no usable embedded revision or surviving native tag was found; the candidate comes from synchronized commit timing and surrounding history.

The artifact value comes from the `KALDI_VERSION` string compiled into `libkaldi-base` in the published manylinux wheel. It is strong evidence, but older incremental builds could retain a base library built before the final native checkout. The clearest example is v1.5.0: its Python build explicitly selects `db0af4bd...`, while its bundled base library reports `9751e9cb...`. For that reason, an explicit selector or matching native tag takes precedence over the embedded marker.

## Complete commit map

[`native-revision-commit-map.csv`](native-revision-commit-map.csv) records all 478 commits reachable from `refs/heads`, `refs/remotes`, and `refs/tags` when this history was prepared. Every row has a full Python SHA and a full native candidate SHA:

- 60 rows have a lock, explicit selector, release tag, or release artifact as direct evidence.
- 35 non-release rows have correlated changes in both repositories.
- 383 rows use a clearly labeled compatibility inference from a release or locked snapshot.
- 57 distinct native revisions are represented, and no durable Python commit is omitted or left without a candidate.

The CSV columns are:

| Column | Meaning |
|---|---|
| `python_commit` | Full Python repository commit SHA. |
| `committer_date` | ISO 8601 committer timestamp. |
| `refs` | Branch, remote-tracking branch, or release tag pointing directly at the commit. |
| `package_version` | Version declared by that Python tree. |
| `python_subject` | Commit subject for scanning and correlation. |
| `native_commit` | Best recoverable full native commit SHA. |
| `confidence` | `exact`, `confirmed`, `artifact`, `artifact+tag`, `correlated`, `inferred-compatible`, or `inferred`. |
| `method` | How the candidate was selected. |
| `historical_selector` | Branch, tag, or SHA that the historical build configuration selected, when recoverable. |
| `anchor` | Release, lock, or correlation that supports `native_commit`. |

Rows are in Git topological order, so committer dates can move backward at branch boundaries. A historical selector is preserved even when it is not used as the candidate. In particular, untagged development commits sometimes still declared a released package version, causing local builds to default to an older `kag-v*` tag while CI selected a moving development branch. Treat `inferred-compatible` rows as useful bisect starting points, not proof that the exact pair was built together. Synthetic stash commits and reflog-only abandoned commits are intentionally excluded because they are not durable repository history.

### Correlated non-release transitions

These rows have matching changes in both repositories. Full SHAs and subjects are retained in the CSV.

| Python commit | Native commit | Correlated change |
|---|---|---|
| `cb059daf8272` | `ea731c2fbaa1` | fix linux support |
| `86a3c39ebc3e` | `bd0d49fd4dc8` | combine AGF graph compilation |
| `4153a87b846a` | `4a78d0668a36` | finish combining AGF graph compilation |
| `41f5c2ca2c8b` | `f7c29612e503` | make rule & dictation nonterm offset parameters |
| `c153ee42cc0f` | `767103b16f2c` | fix live adding to user_lexicon |
| `3c0fb8611517` | `857fd5f2fe2e` | add API to immediately save adaptation state |
| `33ba77f86ec5` | `3512aab579b1` | add support for rnnlm priming |
| `0f66d4f5b531` | `4ed70a4c19df` | pass ivector-extractor configuration directly as JSON |
| `8918f75c81ba` | `c36ca647768e` | add initial NativeWFST implementation |
| `649cee3b8022` | `d41735d7d308` | fix NativeWFST use |
| `ff158177db1b` | `eabbd2db0056` | refactor wrapper/interface function names |
| `30c1c884d8a7` | `09be14ebcb8c` | add wrapper/interface destructors |
| `516ca4e0faba` | `5525bd743c1e` | implement native-FST support for direct AGF |
| `01c984440f34` | `5525bd743c1e` | complete native-FST support for direct AGF |
| `7bc7420df1ba` | `11f6acb320a6` | add/fix `max_num_rules` decoder configuration |
| `dbf389a3e67e` | `54f43c847431` | add FST compilation from text |
| `7e5c53b121d0` | `318f302517ed` | relocate FST loading |
| `5f68c4f6133c` | `9406ee38c400` | internalize building `L_disambig.fst` |
| `a6a2147e6f49` | `134351e97c8d` | implement separate exported/non-exported rule compilation |
| `d7d225487063` | `bbd101216faa` | add NativeWFST writing to disk |
| `da807e6bd942` | `3a4d84cf0f4e` | fix decoding with no active grammars |
| `5ede5f2431ca` | `6bfd3cbd5cf0` | implement all-grammars-at-once direct mimic |
| `6e3c24fa728f` | `13852d464171` | refactor mimicking interface |
| `d2326d4d661f` | `f735ef55c849` | move mimicking from AGF to ActiveBase |
| `ef2109c4cc93` | `a195749e4ec6` | add dictation grammar to mimicking |
| `41d0a0791f65` | `5dc623d681b6` | fix mimicking of non-exported rules |
| `68345ded8dc8` | `46c7a6082435` | fix mimicking with `eps_disambig` |
| `149d849877ec` | `33e38708a3e6` | add NativeWFST printing to stdout |
| `c3b775aef7a2` | `64e1289d227d` | add NativeWFST writing to disk |
| `287933f3e06f` | `d3027fcb1443` | fix AGF interface typo |
| `299270d4e117` | `e4b49b2cfdf1` | add `NativeWFST.has_path()` |
| `ea507ae1449b` | `3986a5a44331` | make `NativeWFST.has_path()` handle loops |
| `4414be402750` | `eaf3ee9e2d37` | remove legacy GMM decoder interface |
| `e9232f91f71c` | `3158291004ed` | fix native resource lifecycle and ownership |
| `b2d040c7a9db` | `b4ede2107a94` | add batched NativeWFST arc export |

## Current development pairing

Commit `0b3af6d28c09256baba8e83982761db8ad41c16c` introduced the lock file. It selects native commit:

```text
b4ede2107a94700d1e657afc0a9f763b4b12fb0d
```

Every descendant continues to use that native commit until the lock file changes.

## Release pairings

| Python release | Python commit | Matching native commit | Evidence | Embedded manylinux marker |
|---|---|---|---|---|
| v0.1.0-dev3 | `27b74ce2399ffabd8de03bfa1fba37570f80e745` | `7c1ccf5135d25f4c4e60f10111aa089b53267065` | Inferred | Unavailable; release was Windows-only |
| v0.2.2 | `e809c3ea2e2d75a6752153e025e88754fe75171c` | `ead17f68075bf2174d5840b1dc83019a49d51685` | Artifact | `5.5.288~2-ead17` |
| v0.3.0 | `2c67e46e663e92b1d8aee1a6ed2f34a1eec67cc8` | `0ae220a521f25adcdbaeb02f9a2b8b6b1aff3288` | Artifact | `5.5.290-0ae2` |
| v0.4.0 | `b2dadeab3816b1420df0ae40e7b7153c727a011c` | `b5fb735127846ba0457cd167c7709c0e0a4fe260` | Artifact | `5.5.292-b5fb7` |
| v0.5.0 | `71a3838862c6b5a2ad68f3d16c81b9f0bccc27f8` | `b05aa9aeaa82a9451c05c3cca3d4831b40710e04` | Artifact | `5.5.300-b05aa` |
| v0.5.1 | `822f0aa9d3a6dba827fb8500e016672f84033c29` | `b05aa9aeaa82a9451c05c3cca3d4831b40710e04` | Artifact | `5.5.300-b05aa` |
| v0.5.2 | `32f4b827bd020b2c0e9899e7325eb238202bd10c` | `b05aa9aeaa82a9451c05c3cca3d4831b40710e04` | Artifact | `5.5.300-b05aa` |
| v0.5.3 | `8cf6081cb35f68430356a4bfa0f36e28ad275999` | `b05aa9aeaa82a9451c05c3cca3d4831b40710e04` | Artifact | `5.5.300-b05aa` |
| v0.6.0 | `c355de2ae277eaa65e0b52b1c78ccfe94f062a84` | `76c140c478b87b98592ad89481dbf48b2f9c6f55` | Artifact | `5.5.302-76c14` |
| v0.7.0 | `ce35a06771ebb655c6bbb2083e3581b8777d2ad2` | `f16c8529bfe0078f3022297959ab6bbcb14ce740` | Artifact | `5.5.304-f16c` |
| v0.7.1 | `5f3024b207a38a95bbdc53e818843ed0a0d5130e` | `f16c8529bfe0078f3022297959ab6bbcb14ce740` | Artifact | `5.5.304-f16c` |
| v0.7.2 | `4ebeb230c2e65bc88b9b25b4ced73e3fa3264e86` | `f16c8529bfe0078f3022297959ab6bbcb14ce740` | Artifact | `5.5.304-f16c` |
| v0.7.3 | `7dc217a1afa7b31b2f1ac2ae797a6eeba624de64` | `6025e5b9c62bc84b918c8533c6895f75dd62ab62` | Artifact + tag `kag-v0.7.3` | `5.5.305-6025` |
| v0.7.4 | `37bf527cb4ec73fad732f98908592f1c6c1aa5a4` | `6025e5b9c62bc84b918c8533c6895f75dd62ab62` | Artifact | `5.5.305-6025` |
| v1.0.0 | `aa44e475847de058babf937a857469ba4ca3d4e8` | `2892b0ebe851d12fd8db004b7a2947204d99a157` | Artifact | `5.5.531-2892b` |
| v1.0.1 | `5c09f4a251fe44768b521962869eb69bb3cb1aa1` | `857fd5f2fe2e2c0df6f134fb8b70427158729d68` | Artifact | `5.5.532-857fd` |
| v1.0.2 | `2d412d05731af259c0a02c3ec43580e61973effd` | `335e3b39a512878532396802cc750efe4fa98acf` | Artifact | `5.5.533-335e3` |
| v1.0.3 | `d09ab0e621254dde833b6dc857d5c81e8cfcdc0d` | `335e3b39a512878532396802cc750efe4fa98acf` | Artifact | `5.5.533-335e3` |
| v1.0.4 | `392b7e8c89ef36b12fa91b2d29d4eaa36710134c` | `1b694905e5c9d686cf8e3e1354ffb0e3d67378f6` | Artifact | `5.5.535-1b6949` |
| v1.1.0 | `a2dad2f6a021814bd55b2d62d40c2a19a7bee986` | `1b694905e5c9d686cf8e3e1354ffb0e3d67378f6` | Artifact | `5.5.535-1b6949` |
| v1.2.0 | `6c94b19d8cedb59fde6b58ba5baed5555557cb28` | `1b694905e5c9d686cf8e3e1354ffb0e3d67378f6` | Artifact | `5.5.535-1b6949` |
| v1.3.0 | `72e3fdbabf5ff8856d92b80611fdd48d178c138e` | `fa6c73cbd7409a1b9512c34f68eb6a7281797ed9` | Artifact | `5.5.536-fa6c7` |
| v1.4.0 | `0de3e3e7325adf4a5e46cfa25df3607b50af05ae` | `3802e4c43eddd74e75097b1f7f4dfd0a9e3fcde4` | Artifact; build source named moving `origin/dragonfly` | `5.5.540-3802e4` |
| v1.5.0 | `2538058fb58e53f9d57b873b12eb689ecdb2087e` | `db0af4bd240ca55a4563d4d37beb1a54bc6f6353` | Explicit SHA + tag `kag-v1.5.0` | `5.5.754-9751e9` from an older base-library build |
| v1.6.0 | `4d20fc53265cd2d879ecc4809a3978f2bce7fc71` | `be68bf233970a2a2664a3d5694438cfca534ff56` | Selector + tag `kag-v1.6.0` | `5.5.0~1-be68` |
| v1.6.1 | `5ee29d80ddd5aa9a211e433197600e4033bca18b` | `be68bf233970a2a2664a3d5694438cfca534ff56` | Selector + tag `kag-v1.6.1` | `5.5.0~1-be68` |
| v1.6.2 | `bdffa023996eceb1d196120a44ad7e23638ee17d` | `be68bf233970a2a2664a3d5694438cfca534ff56` | Selector + tag `kag-v1.6.2` | `5.5.0~1-be68` |
| v1.7.0 | `97b544156b260de8e19d817dab72975f9c239a86` | `f2a3ddc38b7bab4e3c77dcebd17eef2b9560bdc4` | Selector + tag `kag-v1.7.0` | `5.5.0~1-f2a3` |
| v1.8.0 | `a6a31590d50248f9bd515e7df63aba947d7001ca` | `f2a3ddc38b7bab4e3c77dcebd17eef2b9560bdc4` | Selector + tag `kag-v1.8.0` | `5.5.0~1-f2a3` |
| v1.8.1 | `8f21a2e5954a852a720ca4d14e0da1f4fe1cf467` | `f2a3ddc38b7bab4e3c77dcebd17eef2b9560bdc4` | Selector + tag `kag-v1.8.1` | `5.5.0~1-f2a3` |
| v1.8.3 | `b39d21035f3baff574ba36daf73e48e227cbaedc` | `3ebb48ee97fa8b6e4ec3f050106bee0f18b0b589` | Inferred probable target of missing `kag-v1.8.3` tag | Unavailable; release was Windows-only |
| v2.0.0 | `8cbebaf3d4b1315105612a2d8877c55983c11b49` | `e9c7d0ffca401cf312779d25f2c05a34b41ff696` | Selector + tag `kag-v2.0.0` | `5.5.0~1-e9c7` |
| v2.0.2 | `decb6f400b254c5cd35af3cc2d82d4098355f012` | `e9c7d0ffca401cf312779d25f2c05a34b41ff696` | Selector + tag `kag-v2.0.2` | `5.5.0~1-e9c7` |
| v2.1.0 | `ee3ff4128abcf5b02e665f21d1d2ef68df63f957` | `1f5a49865da999327fb772a890957b413119f011` | Selector + tag `kag-v2.1.0` | `5.5.0~1-1f5a4` |
| v3.0.0 | `99be2ae041294a551e36bee9c3b4aa2e1f3ed86e` | `ff55f1097b355989a7926100b99a18035c4a5e47` | Selector + tag `kag-v3.0.0` | `5.5.0~1-ff55` |
| v3.1.0 | `48360b9755198c1faebd42ea61e1536f56671c7f` | `ff55f1097b355989a7926100b99a18035c4a5e47` | Selector + tag `kag-v3.1.0` | `5.5.0~1-ff55` |
| v3.2.0 | `32407283939f5b7667e85369391b0f0230cd246a` | `e48aeed7c5f0df117a5d49f2ef00b19c135feccd` | Selector + tag `kag-v3.2.0` | `5.5.0~1-e48ae` |

## Uncertainties and historical anomalies

### v0.1.0-dev3

Only a Windows wheel was published, and its DLL does not carry a usable Kaldi Git revision. `7c1ccf5135d25f4c4e60f10111aa089b53267065` is the last surviving native feature commit before the Python release and is therefore the best candidate, not a confirmed pairing.

### Rewritten early native commits

The v0.2.2 and v0.5.x wheel markers resolve to commits that are no longer reachable from the native repository's current branches or tags:

```text
ead17f68075bf2174d5840b1dc83019a49d51685
b05aa9aeaa82a9451c05c3cca3d4831b40710e04
```

GitHub still resolves both objects, and a direct shallow fetch by full SHA was verified while preparing this record. They should not be replaced with later commits that merely have similar subjects or timestamps.

### v1.8.3

The Python release workflow would have selected `kag-v1.8.3`, but that native tag no longer exists. The Python release commit was created at 2021-01-02 03:28 -0500; native commit `3ebb48ee97fa8b6e4ec3f050106bee0f18b0b589` followed at 04:33 and is the most likely former tag target. The only published wheel is for Windows and does not expose a Kaldi revision, so this pairing remains inferred.

### Native tags without Python releases

`kag-v2.0.1` exists and points to the same native commit as v2.0.0 and v2.0.2, but there is no Python `v2.0.1` release tag. It is intentionally absent from the release table.

## How this record was reconstructed

1. Enumerate the 478 unique Python commits reachable from durable local branches, remote-tracking branches, and tags.
2. Inspect every Python tree's `setup.py`, `CMakeLists.txt`, CI configuration, package version, and lock file for the selector that tree would use.
3. Resolve release tags, explicit native SHAs, and every surviving `kag-v*` native tag to peeled commits.
4. Where available, inspect published manylinux wheels and extract `KALDI_VERSION` from the bundled `libkaldi-base` library.
5. Resolve abbreviated artifact hashes to full native commits using local Git history or the GitHub commit API.
6. Correlate non-release Python/native commits that describe the same API or feature transition at nearby times.
7. For remaining commits, use the nearest descendant release as a compatibility anchor. If no descendant release exists, use the nearest ancestor release or current locked snapshot as appropriate; these rows remain explicitly inferred.
8. Preserve the historical branch/tag selector separately so inferred compatibility is never presented as proof of the exact checkout used at commit time.

## Maintaining this file

For future releases:

1. Commit and push native changes first.
2. Update `kaldi-native-revision.txt` with `just native-lock`.
3. Verify the sibling checkout with `just native-verify`.
4. Commit the Python changes and lock update.
5. Add the release pair to this file when tagging the release.
6. Append new Python commits and their lock-selected native SHA to `native-revision-commit-map.csv`.

Never replace an exact historical SHA with a branch name. If later evidence corrects an inferred row, preserve the previous candidate in the commit history and explain the stronger evidence here.
