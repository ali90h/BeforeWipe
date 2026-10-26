# Independent engineering and security review

Historical review of the implementation before optional staged-work detection. See [the subsequent implementation and validation note](STAGED_WORK_DETECTION.md) for current behavior. That change has not been independently re-reviewed; the findings and results below are retained as originally recorded.

Reviewed 2026-10-25. Scope: foundational concept, every Python source module, original tests, README, security guidance, example plan, CI configuration, saved demo report, and supplied synthetic demo files. All executions used synthetic data: the supplied demo and newly created temporary trees. No personal directories were scanned, no real developer work was accessed, and no remote repository or service was contacted.

**Assessment:** the revised alpha is suitable for a small, supervised, consent-based learning pilot, provided participants independently review Git staging and retain their original work. It does not reliably identify all important local work. Staged-only work remains a significant known blind spot. It must not be used as a standalone readiness gate, and this review does not establish that any machine can be wiped.

## Confirmed findings, ranked by severity

Severity describes impact on this product's privacy and recovery claims, not a CVSS score. None of the findings demonstrates remote exploitation, data transmission, or actual loss of user work.

| Priority | Finding | Evidence before changes | Disposition |
| --- | --- | --- | --- |
| High | Default assessment could read sensitive work-file bytes through a hardlinked Git ref. | A synthetic `.git/refs/heads/main` hardlinked to a synthetic `.env` caused `os.read` to consume that inode. A filename exclusion and `O_NOFOLLOW` did not prevent this. | Fixed for detectable hardlink and substitution cases. |
| High | Content verification could claim a match after the copy became the source inode, or after the declared restore root was replaced. | Replacing the restored file with a hardlink after the initial identity checks returned `match / selected_bytes_equal`. Renaming the opened restore directory and creating an empty directory at its declared path also returned `match`. | Fixed for reproduced interleavings; still not an atomic snapshot. |
| High, known functional limitation | Staged-only work is not identified. | Git's staged diff reported a modified file while BeforeWipe reported three metadata matches, zero changes, and zero files outside the index. Staged additions and deletions also produced zero metadata differences in independent fixtures. | Detection remains unsupported. Warnings and regression evidence strengthened. |
| Medium | Scope guards relied on lexical path spelling. | POSIX `//` survives `abspath` and differs from `Path('/')`, but the descriptor walk starts at `/`. A `symlink/../...` spelling was collapsed and assessed as a different scope. A synthetic home with different casing was accepted by the constructor. | Fixed repeated-leading-slash, parent-component, and conservative case/Unicode comparison rules. |
| Medium | A failed ref read erased independent project findings. | Replacing one ref with invalid synthetic text changed the whole project to a generic unknown, suppressing a known modified tracked file and two files outside the index. | Fixed: retain working-tree observations; unavailable branch/stash counts are null, with an explicit error. |
| Medium | Nested Git metadata could disappear without a gap indicator. | A genuine empty nested repository produced zero inventory gap counters and no `coverage_gaps` finding. Its `.git` entry was skipped silently. | Fixed: skipped Git markers are counted. Nested repository recovery is still unverified. |
| Low | A small, deeply nested plan caused an uncaught parser exception. | A plan containing 1,100 nested arrays raised `RecursionError` instead of the documented invalid-input result. | Fixed: controlled content-free error, exit 2. |

### Hardlink reads and verification identity

The initial implementation validated file type and rejected symlinks, but it did not reject multiply linked Git structural files. That allowed an inode behind a name normally excluded from assessment to be read through a permitted ref name. The experiment used only synthetic sentinel data; nothing was transmitted or printed from the file.

`Root.open_file` now checks regular-file type and identity before and immediately after opening. Plan and Git metadata reads require a single link. Metadata reads also check for size, timestamp, identity, and path replacement changes before accepting the data. The test that substitutes a hardlink during `os.open` verifies rejection before the first byte read from the sentinel inode.

Verification now carries each selected file's initial fingerprint into the content reader, checks final inode independence, and checks that each declared root still identifies the opened directory. This also prevents a newly substituted, unreviewed file from being read in the reproduced pre-read replacement case. Filesystem access remains descriptor-relative and uses no-follow flags.

Relevant regressions in `tests/test_review.py`:

- `test_hardlinked_git_metadata_never_reads_work_file`
- `test_hardlink_substituted_during_metadata_open_is_not_read`
- `test_selected_replacement_is_rejected_before_content_read`
- `test_substitution_cannot_verify_same_inode`
- `test_root_replacement_cannot_verify_old_directory`
- `test_metadata_replacement_during_read_is_unknown`

These fixes do not establish protection against every concurrent write, hostile filesystems, or sensitive bytes deliberately copied into an otherwise ordinary Git metadata file. Identity and naming cannot establish content provenance. Stable, trusted scopes remain a pilot condition.

### Staged work and incomplete backups

The original suite had one staged-only test that explicitly expected no detection. It did not establish whether the product would find that risk. The revised suite uses real isolated Git repositories and `git diff --cached --name-status` as an independent oracle for staged modification, addition, deletion, rename, and an index-only version whose working file was restored to HEAD.

Staged modification/addition/deletion can leave the indexed metadata matching the working files. Renames and index-only versions may raise incidental metadata warnings, but are still not identified as staged work. A warning about changed file metadata is not a diagnosis of what exists only in the index's referenced objects.

`test_matching_work_files_do_not_preserve_index_only_work` demonstrates the consequential recovery gap: the source working file and restored file match, while Git reports a staged version that is absent from the restored tree. Copying only those working files loses the staged version. The restore contains no `.git` directory.

I did not add an implicit Git subprocess or object-content reader. Determining general staging differences needs evidence about the committed tree that the current reader does not collect. Extending reads into repository objects would change the foundational privacy boundary and would require a separate design and review. In particular, arbitrary Git commands may consult configuration and external machinery, and object contents are not guaranteed to be non-sensitive.

The report now says that staging is not inspected, explicitly names the missed states, and instructs users to preserve the index and objects as well as important working files. `staging_status` remains `unknown`. This is a disclosed limitation, not a detection fix.

The original selected-content conclusion was already appropriately narrow: project recoverability stayed unknown, global readiness stayed `not_determined`, and the text explained the limitations. I found no promotion from a selected-file match to verified project recovery. The revised completed comparison result additionally carries `verification_scope: selected_file_bytes` and `recoverability: unknown` for machine consumers. Missing selections prevent an all-selected-files success. A recovery-only plan can still exit 0 for matching selections; that exit code is not a readiness verdict.

Relevant regressions:

- `test_staged_only_variants_against_git_oracle`
- `test_matching_work_files_do_not_preserve_index_only_work`
- `test_incomplete_backup_does_not_verify_project`
- `test_multiple_selections_cannot_hide_missing_file`

### Scope handling and partial evidence

Scope normalization now happens before root/home exclusions and overlap checks. A path containing `..` is refused instead of being silently reinterpreted. Case and Unicode normalization are used conservatively for home and overlapping-root comparisons. This can refuse genuinely distinct case-sensitive paths; that is an intentional false refusal. The broad-root tests intercept access before any open, and the home-case experiment substitutes a synthetic home path. No actual home or filesystem-root inventory was performed.

Reference failures are handled separately from valid index and working-tree checks. The resulting `coverage_errors` contain fixed reason codes, while branch/stash counts become null rather than zero. This does not reconstruct damaged refs. Invalid HEAD/index structures and unsupported layouts can still make the entire project unknown; that limitation is explicit and must be handled independently.

Inventory now counts skipped `.git` markers except the known top-level metadata directory already being assessed. This exposes nested repository gaps without entering their Git metadata. It does not claim to identify every possible repository layout.

## Validation results and quality of coverage

The original **39/39 tests passed** independently before any source changes. The final **66/66 tests passed**, with **zero failures and zero skips**, in 7.027 seconds. The 27 added tests are in `tests/test_review.py`; original tests were retained. One original limit assertion was updated because independent working-tree evidence now survives a ref-scan limit, and one mock accepts the new expected-fingerprint argument.

Local environment: macOS/Darwin 27.0.0 arm64, Python 3.9.6, Apple Git 2.50.1. Remote CI was not run. No Linux, Python 3.13, Windows, network filesystem, or real backup-system execution is claimed.

Commands exercised:

```sh
python3 -B -m unittest discover -s tests -v
python3 -B -m beforewipe demo --directory <new-isolated-directory>
python3 -B -m beforewipe assess --plan <synthetic-plan> --format json
python3 -B -m beforewipe verify --plan <synthetic-plan> --allow-content-read --format json
```

Both the supplied demo and a newly generated demo produced:

| Operation | Exit | Attention | Unknown | Selected content matches | Readiness |
| --- | --- | --- | --- | --- | --- |
| Create fresh demo | 0 | — | — | — | No assessment |
| Assess | 1 | 2 | 3 | 0 | `not_determined` |
| Verify | 1 | 3 | 1 | 1 | `not_determined` |

The original suite provides meaningful contract coverage for missing and changed data, consent, report privacy, checksums, unsupported index versions, conflicts, stashes, symlinks, hardlinks, size limits, and no assessed-data writes. The existing read audit forbids assessment subprocesses and socket creation and restricts byte reads to allowed metadata. Those tests continue to pass. The synthetic restored-program test proves only that that tiny example runs; it does not validate a general environment restore.

The added coverage uses independent oracles and negative cases rather than only implementation-shaped expectations:

- Git confirms actual staged changes and confirms that a cached-remote ancestor has no unpublished commits despite a differing tip.
- A timestamp-only change raises an inferred warning even though Git reports no content diff; this is an accepted false positive, correctly qualified in the report.
- Adversarial inode/root substitutions reproduce incorrect success and unauthorized-byte-read cases deterministically.
- A real permission-denied session subdirectory, special files, excluded files, nested Git markers, and depth limits produce visible gaps without transcript reads.
- Actual linked worktrees, SHA-256 repositories, and bare repositories fail conservatively; tracked symlinks and tracked sensitive files remain unchecked without content reads.
- A restore lacking history and important unselected work never becomes a verified project.

The tests do not measure recall across developers' real work, determine importance, prove backup survival, prove every syscall is read-only under every OS, or establish that users understand every warning. The original suite's all-pass result coexisted with the confirmed defects above. Passing the revised suite is evidence for these specific contracts and reproductions only.

Audit artifacts:

- `review/baseline.json`: original source hashes, original test count, and early reproductions.
- `review/test-results.txt`: full final unittest output.
- `review/demo-results.json`: compact independently executed CLI results.
- `review/existing-assess.json`, `review/existing-verify.json`, `review/fresh-assess.json`, `review/fresh-verify.json`: actual synthetic outputs.
- `review/original-demo-report.json`: original saved report retained for comparison.
- `demo-report.json`: regenerated example using the revised implementation.

## Remaining risks and unsupported scenarios

1. **Detection is incomplete:** staged-only and reflog-only work, object integrity, history completeness, LFS payloads, full submodule/nested-repository recovery, and exact file content changes are not established. No numerical recall claim is justified.
2. **Metadata produces false alarms:** touched/restored metadata, ignored build output, and older branches whose commits are already on the remote can trigger attention. Name exclusions can hide useful work, but gaps remain visible. Symbolic refs and unusual ref layouts are not a complete branch model.
3. **Unsupported Git layouts:** linked worktrees/gitfiles, bare repositories, SHA-256, index v4, split/sparse indexes, and reftable are unsupported or unknown. The review directly exercised only the named formats covered by the suite; it did not test every reftable or sparse-index variant.
4. **Sessions are inventory only:** file count and size do not establish conversation count, freshness, completeness, parseability, or usability. Transcripts, authentication, and session databases are not recovery-tested.
5. **File equality is limited:** no backup provenance, off-device durability, permissions/ACLs/xattrs, symlink restoration, dependencies, application behavior, history, or complete-project restoration is established. A same-disk copy can pass and be lost with the source.
6. **Filesystem scope is not a sandbox:** scans are bounded and non-atomic. Mount/bind-mount aliases, device survival, privileged mutation, and malicious filesystems are not verified. Changes after the final checks remain possible. OS reads may update access times. Demo creation intentionally writes a new synthetic tree and is not hardened against an adversary replacing its destination ancestors concurrently.
7. **Privacy depends on reviewed inputs:** ordinary selected code can contain embedded secrets, and a hostile repository can disguise arbitrary bytes as Git metadata. Filters are guardrails, not a general secret detector. Reports omit paths/content but retain user-supplied IDs and aggregate work metadata.
8. **Validation remains local and synthetic:** no real developer study, actual machine wipe, disaster recovery, remote CI, or cross-platform conformance has been completed. Unsupported or inaccessible items require a separate trusted review.

## Controlled-pilot decision

**Yes, for a narrowly controlled learning pilot using the revised code; no, for an unsupervised or comprehensive readiness assessment.** The original implementation should not be piloted without the reproduced privacy and verification fixes.

The pilot should use a few explicitly selected, stable, trusted project/session directories, with participants reviewing the plan and separately consenting to each non-sensitive content-selection set. Run the suite on the pilot environment first. Keep original data intact throughout the pilot; no wipe or destructive cleanup should be part of it.

Every participant needs an independent Git review, particularly staging, and an independently performed restore check that covers the work they consider important. Collect overlooked risks, missed risks, false alarms, and whether participants correctly distinguish a file match from project recoverability. Record unknowns as unresolved. A participant who interprets `verified_content_match` or exit 0 as full recovery has identified a product problem even if the underlying comparison is correct.

The pilot can test usefulness and comprehension under those conditions. It cannot establish machine-wipe safety.
