# Staged-work detection: implementation and validation

Historical implementation note. The [independent object-reader audit](GIT_OBJECT_SECURITY_REVIEW.md) subsequently reproduced and fixed reference-resolution, malformed-commit, and failure-budget defects; its evidence supersedes the claims below where applicable.

Implemented and validated on 2026-10-25. This is an implementation note, not a second independent security review. All development assessments and Git executions used newly created isolated synthetic fixtures. No personal directories or real developer repositories were assessed, no network requests were made, and no existing user work was changed.

## Approach and necessary evidence

The existing SHA-1 v2/v3 index parser already read each entry's object ID, but discarded it. The reader now retains that ID internally, together with path, mode, merge stage, and intent-to-add state. None of those private values is emitted in a report.

A working file's size/timestamps describe its relationship to the index's cached stat fields, not the index's relationship to HEAD. Staging an edit can update those fields to match the working file. Staging a deletion removes the entry entirely; staging an addition adds a matching entry. An index-only version can differ from both HEAD and a matching working-file restore. Ref IDs alone identify commits, not their path-to-version mappings. Index cache-tree extensions describe cached index trees and do not supply a trustworthy committed-tree baseline.

General comparison therefore cannot be established from the currently permitted structural metadata. Default mode keeps `staging_status: unknown` and `coverage: not_inspected`, with an explicit warning and no additional object access. Existing conflict-stage detection remains available in default mode.

The optional `--allow-git-object-read` grants a separate, invocation-only authorization for all explicitly declared project roots. Its help and documentation state that the repositories must be reviewed as non-sensitive and that reads include commit messages, tree names, and potentially arbitrary bytes in disguised objects. The Python entry points also default `allow_git_object_read=False`; `verify=True` alone never grants this access. A plan cannot silently enable object reads.

With authorization, the reader resolves a supported physical HEAD from existing refs, opens only its local loose object, obtains its root-tree ID, and walks local loose tree references. It compares `(mode, object ID)` at each path with index stage-zero entries. It does not follow parents or blob entries. Renames require no heuristic for risk detection: they appear as deletion plus addition. No content similarity or rename identity is claimed.

Object reads use the existing descriptor-relative, no-follow, single-link, regular-file reader. Objects must have bounded zlib framing without trailing data, the expected type and declared length, and the SHA-1 identity of their object path. Tree syntax, path components, ordering, modes, duplicate names, and zero IDs are checked. Index ordering, duplicate stages, path collisions, supported modes/flags, and zero IDs are also checked before comparison. Duplicate packed refs and malformed peeled IDs are refused as ambiguous committed-state evidence. Checksums establish consistency with the referenced bytes, not provenance, authenticity, or security against a hostile repository.

Compressed and expanded object bytes each have an 8 MiB per-object and 32 MiB per-project budget. There are at most 4,096 object attempts, 100,000 tree entries, and 32 subtree levels. The existing index and filesystem limits still apply. Failure in a subtree makes that subtree unknown; independent differences elsewhere survive as confirmed lower bounds. Re-reading index, HEAD, and refs and checking the declared root detects the tested concurrent substitutions; changed state invalidates staging counts. This is not an atomic filesystem snapshot.

## What is detected

Real Git constructs each scenario; `git diff --cached --no-renames --name-status -z` supplies the independent expected added/modified/deleted counts.

| Scenario | Actual result with authorized, available loose commit/tree objects |
| --- | --- |
| Staged addition | Confirmed added path |
| Staged modification | Confirmed modified ID |
| Staged deletion, including an empty index | Confirmed deleted path |
| Rename | Confirmed deletion plus addition, without pairing |
| Index-only version after restoring the working file to HEAD | Confirmed modified ID, even when the working copy matches the restored copy |
| Executable-bit change | Confirmed modified mode |
| Regular-file to symlink change | Confirmed type/mode change; no symlink target opened |
| Gitlink addition/change | ID/mode comparison only; no submodule repository access or recovery claim |
| Assume-unchanged / skip-worktree flags in a complete index | Stored IDs still compared; working-file coverage remains separately qualified |
| Detached HEAD; packed refs with loose objects | Supported comparison |
| One missing committed subtree and a known difference elsewhere | `confirmed_risk`, `coverage: incomplete`, lower-bound counts |
| No index/HEAD difference | `no_difference_observed`, never verified repository recovery |

For staged addition/modification/deletion, regression assertions also verify zero working-tree metadata changes and zero tracked missing paths. Detection is independent of those metadata warnings.

## Reproduction of the original loss

`test_original_loss_reproduction_with_matching_working_copy` stages a new synthetic version and restores the working file from HEAD. The source and restored working files are byte-equal; the staged blob differs from the restored file, and the restore has no `.git` directory.

An additional executed CLI reproduction (`verify` with both separately authorized read flags, exit 1) is saved in [index-only-evidence.json](staging/index-only-evidence.json), with [the rendered report](staging/index-only-report.txt). Its independent oracle reports exactly one staged modification. BeforeWipe reports:

- Project staging: `confirmed_risk`, complete supported ID/mode comparison, one modified path.
- Project status: `attention`; recoverability: `unknown`.
- Selected working-file comparison: `verified_content_match`, limited to `selected_file_bytes`, recoverability: `unknown`.
- Overall readiness: `not_determined`.

The report explicitly says selected-file matches do not preserve staged-only work. That warning is also present for recovery-only plans. File verification cannot change a project's staging finding or promote project recoverability.

The original failure is detected within this authorized loose-object scope. In default metadata-only mode, or when necessary committed objects are unavailable loose, it remains an explicit unknown rather than a detection claim.

## Unknowns and unsupported cases

Every project result, including failed items, carries `observations.staging` and a mirrored `staging_status`. Status distinguishes `confirmed_risk`, `no_difference_observed`, `unknown`, and `unsupported`; coverage separately distinguishes `complete`, `incomplete`, `not_inspected`, and `unsupported`. Fixed `reason_codes`, lower-bound counts, and `paths_compared` let machine consumers distinguish evidence from gaps. Text includes the same coverage and warnings. A zero lower bound does not establish absence.

- **Packed, external, or missing objects:** absence of a required loose object is ambiguous. No packfile or alternates file is opened, and no store outside the root is followed. This is an important practical gap for cloned or garbage-collected repositories. A real `git gc` fixture demonstrates unknown staging despite Git resolving a staged difference. Do not unpack or change real repositories merely to obtain a BeforeWipe result.
- **Unborn or missing HEAD:** absence of a branch tip is not assumed to prove a trustworthy empty baseline. The result is explicitly unsupported. A missing index is incomplete, not an empty staged tree.
- **Merge stages and intent-to-add:** these entries leave coverage incomplete and are not miscounted as ordinary deletions/additions. Independently comparable paths can still supply confirmed differences. Unusual file/directory conflict layouts can fail index validation conservatively.
- **Linked worktrees/gitfiles, bare repositories, SHA-256, index v4, split/sparse indexes, reftable, and replacement refs:** unsupported or unknown, with no automatic traversal, conversion, or subprocess fallback. Sparse directory entries now get a specific unsupported reason. Existing SHA-256/bare tests remain conservative unknowns; no config read was added to identify formats.
- **Blob availability, integrity, staging restore, history, reflog-only work, LFS payloads, other branches/stashes, nested repositories, and submodule contents:** unverified. Comparing IDs does not require, and does not establish, availability of the versions they name. A missing-blob regression deliberately preserves detection while keeping recoverability unknown.
- **Working-file identity with staging:** the comparison proves index/HEAD differences, not whether those staged versions are also represented in working files. It does not label every difference as content that exists exclusively in the index.
- **Concurrent or hostile filesystem mutation:** detected replacements become unknown, but changes after checks, ABA changes, mount aliases, privileged mutation, and malicious filesystems remain outside the guarantee.

## Security and privacy assessment

An implicit Git subprocess was rejected because Git can consult configuration, helpers, hooks, filters, alternate stores, and external paths. Adding pack parsing or executing a supposedly constrained Git command would materially expand the attack surface and review scope. Loose-object comparison supplies useful evidence with a smaller explicit boundary.

The new boundary still matters. Compressed commit objects contain messages; trees contain filenames; a supposedly structural object can actually be a blob or arbitrary sensitive data. Type checking happens after reading. No parser or filename filter can establish that repository contents are non-sensitive. Only reviewed non-sensitive repositories may be authorized. If that review is not possible, retain default mode and use a separate trusted Git review. The option must not be interpreted as permission to collect secrets.

For valid fixtures, read audits establish that only expected commit/tree object inodes and existing structural metadata are read. They reject work-file/blob/config/external-store reads, subprocesses, network sockets, and write-mode opens. A filesystem snapshot comparison finds no assessed-data changes. Synthetic hardlinks, substituted hardlinks, symlinks, symlinked object directories, and FIFOs are refused before sentinel reads. All reports omit object IDs, filenames, messages, content, and paths, including control-character filenames. Name/identity checks cannot prevent sensitive bytes deliberately copied into an ordinary single-link object; explicit scope and informed review remain necessary. OS reads may update access times.

No new runtime dependency, network feature, discovery scan, or modification/backup operation was introduced.

## Executed validation

Environment: macOS/Darwin 27.0.0 arm64, Python 3.9.6, Apple Git 2.50.1. All fixture Git invocations use isolated HOME/config with hooks and fsmonitor disabled. They only operate inside new temporary synthetic trees.

- Before edits: **66/66 passed**, zero failures/skips, 6.945 seconds.
- New staging regressions: **33/33 passed** as part of the final full run, zero failures/skips.
- Final full suite: **99/99 passed**, zero failures/skips, 11.071 seconds. Full output: [full-test-results.txt](staging/full-test-results.txt).
- CLI help and synthetic CLI assessments verify explicit object-read consent and that it does not authorize selected-file reads.
- Saved index-only reproduction independently confirms the oracle, byte match, absent Git restore, and attention finding.

The new tests cover actual Git additions/modifications/deletions/renames, index-only versions, modes/types, empty index, detached/packed refs, intent-to-add, merge stages, partial subtrees, real packed/split/sparse indexes and linked worktrees, valid-checksum malformed indexes, malformed/truncated/type-confused/hash-mismatched/compression-bomb/trailing-data objects, tree paths/order/duplicates/modes, object/entry/depth budgets, raw Git filename bytes and control characters, consent separation, report redaction, unchanged default access, scoped no-write reads, alternates/config refusal, hardlink/symlink/FIFO attacks, and index/ref/root substitutions.

No remote CI, Linux/Python 3.13 run, real developer assessment, backup-system test, recall measurement, or wipe was performed. Passing synthetic regressions demonstrates these cases, not complete risk detection or repository recoverability.

## Barriers to a supervised real-developer pilot

The original review's safeguards still apply: narrowly selected stable trusted roots, independent local Git review, originals retained, and independently tested restore of important work. No destructive cleanup belongs in a pilot.

Before a pilot exercises expanded object reads, obtain an independent security review of this new reader and its consent wording, confirm that participants can review the selected repositories as non-sensitive, and run the suite on the actual pilot platform. Unsupported or packed repositories need an independent staging review; their unknowns must remain unresolved in the report. Test that participants understand `complete` means only a bounded ID/mode comparison and that a file match is not repository recovery. Actual restoration must cover the index and its required objects, relevant refs/history, and usable working context; BeforeWipe does not provide that proof. A pilot limited to default metadata mode retains the independently reviewed boundary and its explicitly disclosed staging blind spot.
