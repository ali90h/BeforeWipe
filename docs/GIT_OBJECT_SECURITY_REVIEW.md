# Independent Git object-reader security and correctness review

Reviewed 2026-10-26. **Decision: CONDITIONAL GO for a small supervised pilot using the revised code.** The pre-audit object reader should not be piloted unchanged. No machine-wipe safety conclusion is established.

Read the foundational concept, both earlier review/implementation reports, README/security guidance, all seven runtime modules, all 99 existing tests, and CI configuration. Assessment executions used newly created synthetic repositories and isolated Git homes/configuration. Git was used only for fixture construction and independent oracles; no runtime Git execution, network feature, permission expansion, or packfile support was added.

## Confirmed defects, ranked

Severity reflects impact on evidence reliability and local resource use, not remote exploitability.

| Severity | Defect and reproduction | Before | After |
| --- | --- | --- | --- |
| **High — correctness** | A symbolic loose branch ref shadows a stale packed ref. Pack `main`, create another committed version on `other`, then point `main` symbolically at `other` and HEAD at `main`. | The reader skipped the symbolic ref and reused the old packed ID. With the actual HEAD tree in the index, Git reported **zero changes**, but BeforeWipe reported `confirmed_risk`. With the old tree in the index, Git reported **one modification**, but BeforeWipe reported `no_difference_observed / complete`. | Non-remote symbolic refs make reference/staging evidence unknown. Remote aliases remain ignored, with shadowed packed values removed. Ordinary remote symbolic HEAD does not block comparison. |
| **Medium — resource exhaustion** | Failed reads/inflation were not charged to aggregate budgets. A zlib stream with a corrupted Adler checksum performs decompression before raising. Real timestamp mutation or file relocation during `os.read` causes validation to fail after bytes are consumed. | Three 900-byte inflation attempts left the expanded counter **0**. Five actual 900-byte reads consumed **4,500 bytes** despite a scaled **2,048-byte** aggregate limit. Existing tests exercised limits only on successful accounting paths. | Failed inflation/read attempts conservatively consume their maximum possible budget; exhausted expansion budgets are checked before further object access. Per-operation limit probing can consume one extra byte. |
| **Medium — malformed baseline acceptance** | Write a correctly hashed commit with `committer` before `author`, pointing at a valid tree. | `git fsck --strict --no-reflogs` rejected it with `missingAuthor`; BeforeWipe accepted it as `no_difference_observed / complete`. Mandatory fields were counted without validating their ordering. | Mandatory tree/parent/author/committer ordering and identity syntax are checked; malformed commits return unknown. Header parsing is additionally capped at 64 KiB. Valid extension/continuation headers remain supported. |

The resource reproductions deliberately reduce the constants to test accounting without stressing the machine. At production limits, repeated failures could multiply work far beyond the advertised 32 MiB aggregate budget, though object-attempt limits still bounded it. No unbounded memory exhaustion or machine crash was attempted or claimed.

## Evidence and changes

- [Saved original modules](object-review/before/) preserve all changed runtime code before fixes.
- [Before regression output](object-review/before-tests.txt) records six failing assertions across five tests reproducing the three defects; [after output](object-review/after-tests.txt) records their resolution.
- [Regression source](../tests/test_object_review.py) contains the synthetic construction, independent Git checks, actual inode-read instrumentation, and assertions.
- [Reproduction runner](object-review/reproduce.py) runs the same regressions against saved original modules or current code in a temporary package. Run `python3 -B docs/object-review/reproduce.py --before` to reproduce failures; omit `--before` for fixed behavior. Neither mode changes the working implementation.
- [Full suite output](object-review/full-test-results.txt) and [source/environment manifest](object-review/manifest.json) identify the tested revision.

The initial **99/99 tests passed** before fixes. The final **109/109 passed**, zero failures or skips. Ten independent audit tests were added. Existing tests were retained unchanged. New differential coverage includes eight deterministic rounds of twelve mixed edits, deletions, renames, and executable-bit changes across thirty synthetic files; counts agree with `git diff --cached --no-renames --name-status -z`. Tests also cover a loose HEAD whose required trees are packed, plan-based consent injection, and valid extended commit headers.

Changes are confined to `gitmeta.py`, `staging.py`, regression/evidence files, and documentation. There is no new runtime dependency. Conservative error accounting can end comparison early after inaccessible objects; conservative commit parsing can refuse unusual valid histories. Both produce explicit unknowns rather than inferred completeness.

## Privacy, authorization, and surviving guarantees

No new unauthorized-object-read bypass was reproduced through the CLI or normal assessment entry point. A plan cannot enable object reads, default/content-only assessment does not open objects, and object consent does not authorize selected-file contents. The flag explicitly covers **every declared project for that invocation**, including commit messages, tree names, and arbitrary disguised bytes. Python callers remain responsible for obtaining consent before setting the authorization argument; this is not an OS-enforced capability boundary.

Existing inode read audits and regression attacks still pass: no work-file/blob/config/alternate-store reads on valid object fixtures, no assessment subprocesses, sockets, or write-mode opens; hardlinks, symlinks, symlinked ancestors, FIFOs, and tested substitutions are rejected. Index/ref/root changes invalidate the staging comparison. The new timestamp/relocation races verify budget behavior on real failed reads, not only a mocked exception.

Reports remain aggregate and content-free in tested text/JSON cases, including malformed objects and control-character names. User-supplied IDs and aggregate counts still disclose metadata. Selected-file matches never promote repository recoverability or overall readiness.

**The foundational “never access secrets” principle is not an unconditional guarantee of this implementation.** Ordinary single-link objects or structural metadata can contain copied secret bytes; validation occurs after reading. Consent wording acknowledges this, but cannot establish provenance. The pilot must use repositories whose contents participants can actually review as non-sensitive; otherwise leave object reads disabled. No secret-scanning claim is justified.

## Practical usefulness and remaining risks

1. **Packed objects remain a major coverage gap.** Both wholly packed repositories and loose HEAD commits with packed trees remain unknown despite Git detecting staged work. Common cloned/garbage-collected layouts can therefore receive little benefit from the new option. No population-level coverage estimate is available. Do not unpack or modify real repositories merely to obtain a result.
2. Linked worktrees/gitfiles, bare repositories, SHA-256, index v4, split/sparse indexes, replacement refs, unborn HEAD, missing objects, and now non-remote symbolic refs remain unsupported/incomplete. Default staging remains uninspected. Unknown is not absence.
3. Comparison establishes only index/physical-HEAD path, ID, and mode differences. Blob availability/integrity, index-only recovery, full history, reflog-only work, LFS, submodules, sessions, backup durability, and runnable restores remain unverified. A hash is consistency evidence, not authentication.
4. Filesystem checks are non-atomic. Concurrent in-place writes, ABA replacements, mutations after final checks, mount aliases, and hostile/privileged filesystems remain unresolved. Rejection after a read cannot undo exposure of bytes already consumed. Keep roots stable and trusted.
5. Limits are per project, not a wall-clock deadline or process-wide memory cap. Many declared roots can accumulate substantial work. Slow filesystem calls are not timed out. Strict parsing is not full `git fsck`; no exhaustive parser fuzzing or adversarial filesystem proof is claimed.
6. Validation is local, synthetic, and platform-specific. No Linux/other-Python execution, remote CI run, real developer recall study, or participant comprehension study was performed. Passing tests support these specific scenarios only.

## Supervised-pilot conditions

Use the fixed version; run its suite on the pilot platform; select a few stable, trusted, reviewed non-sensitive roots and obtain separate informed consent for object and selected-file reads. Keep original data intact and exclude wiping or destructive cleanup from the pilot. Require an independent trusted Git review for staging, especially packed/unsupported layouts, and an independently tested repository/context restore. Verify that participants understand `complete` describes only the bounded comparison and that matching selected bytes does not preserve staged-only versions.

Under those conditions, the pilot can investigate usefulness, missed work, false alarms, and understanding of unknowns. This review does not establish that BeforeWipe is safe for wiping a machine.
