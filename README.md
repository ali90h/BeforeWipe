# BeforeWipe — experimental Alpha

**Do not use BeforeWipe to decide whether to wipe a machine. It does not establish that a wipe is safe. Keep all originals.**

We are looking for **one volunteer** for a supervised, non-destructive first trial. Start with synthetic data; real-data access requires separate, informed agreement. See [the invitation and safe first session](docs/VOLUNTEER.md), [pilot procedure](docs/PILOT.md), and [Alpha release notes](docs/RELEASE_ALPHA.md). No human usefulness results are available.

Review local work within directories you explicitly select, and test selected recovery evidence before replacing or wiping a development machine. Work outside those directories cannot be discovered.

**Working alpha, Python 3.9+, macOS/Linux, no runtime packages required.** BeforeWipe is an assessment tool, not a backup engine. It only examines directories you declare. It never produces a machine-wide “safe to wipe” verdict.

The [supervised pilot procedure](docs/PILOT.md) and [product reality check with executed synthetic evidence](docs/PRODUCT_REALITY_CHECK.md) are ready. No human pilot results are available.

## Try it safely

From this repository, with Python and Git installed:

```sh
python3 -B -m beforewipe demo --directory demo-work-new
python3 -B -m beforewipe assess --plan demo-work-new/plan.json
python3 -B -m beforewipe verify --plan demo-work-new/plan.json --allow-content-read
```

`demo` creates a **new**, isolated tree with a real synthetic Git repository, a synthetic session file, and simulated restored files. It refuses to overwrite an existing directory. It runs Git with an isolated home and disabled system/global config and hooks. Assessment and verification do not invoke Git or any subprocess.

The demonstration finds:

- A tracked file whose metadata changed and two files outside the index, including ignored work.
- Session files whose recoverability remains unknown; no transcripts are opened.
- A selected code file with identical bytes in a separate copy: `verified_content_match`.
- Stale restored notes: `mismatch`.
- A missing restored idea: `unknown` with `selected_file_missing`.

An actual synthetic CLI run is saved in [docs/demo-report.json](docs/demo-report.json): three items need attention, one remains unknown, and one selected-content comparison is verified.

Assessment and verification return **1 for attention or unknowns**. This is expected in the demo. Exit **0** means every declared item has a verified selected-content match, which is possible for a recovery-only plan; it is **never wipe approval**. Exit **2** means invalid input or command/setup failure. Per-item access/format failures are unknowns, so other items still get assessed. `demo` returns 0 on successful fixture creation.

## Assess your chosen scope

Make a private copy of [examples/plan.json](examples/plan.json), edit its paths, and remove sections you do not need. Supply exact project roots and exact session directories; there is no home-directory discovery. Relative paths are relative to the plan file. Use physical paths with no symlink components (`/private/tmp` rather than `/tmp` on macOS). Paths containing `..` are refused to avoid silently changing their meaning; use an explicit absolute path instead. The plan itself must be a regular file, have no symlink ancestors, and contain no secrets. Scope roots `/` and your home directory itself are refused, including spellings with repeated leading slashes. Home and overlapping recovery roots are compared conservatively without case distinctions, which can refuse distinct paths on case-sensitive filesystems. Hardlinked plans and Git structural files are refused before reading bytes.

```sh
python3 -B -m beforewipe assess --plan private-plan.json
python3 -B -m beforewipe assess --plan private-plan.json --format json
```

Each item needs a unique, non-sensitive `id` matching `[a-z][a-z0-9_-]{0,39}`. IDs identify findings without exposing file paths. Paths, filenames, branch names, remote URLs, object IDs, digests, and contents are omitted from text and JSON reports. Aggregate counts and user-supplied IDs can still be private. Reports go only to stdout; the tool does not save or upload them.

| Section | Required fields | What is accessed |
| --- | --- | --- |
| `projects` | `id`, `path` | Filesystem metadata; `.git/HEAD`, index, loose refs, packed refs |
| `sessions` | `id`, `path`, `tool` (`codex`, `claude`, `other`) | Recursive directory entries and regular-file sizes only |
| `recoveries` | `id`, `source`, `restored`, `files` | Nothing during default assessment; explicit selected bytes during `verify` |

The default Git reader checks index checksums, indexed-file metadata, files outside the index, merge stages, stash-ref presence, detached HEAD, and whether local branch tips exactly match any cached remote tip. It does not read Git object contents. Neither assessment mode reads Git config, hooks, ignore patterns, reflogs, or credentials, or contacts remotes. There is no clone, push, fetch, backup, restore, delete, or wipe command.

If reference inspection fails, independently detected working-file risks are retained. Unavailable branch/stash counts are JSON `null` (text: `unknown`), with reasons in `coverage_errors`; they are not zero. Skipped nested `.git` markers are counted in `git_entries_skipped` as coverage gaps, not inspected for repository recovery.

## Optional staged-work comparison

An index entry records the staged version's object ID and mode. Working-file metadata cannot establish whether that version differs from the committed tree: staged edits, additions, deletions, and renames may produce no metadata warning. General comparison needs the HEAD commit's tree and its subtrees, which are outside the default metadata boundary.

**Review all declared project repositories for non-sensitive object contents before authorizing this option.** It reads local loose HEAD commit/tree objects, including commit messages and filenames. An object presented as a commit or tree can contain arbitrary bytes, including secrets; object type and hash validation happen after reading. Name filters cannot establish provenance or detect embedded secrets. Do not authorize it for unreviewed or secret-bearing repositories. Keep the default assessment if that review is not possible.

After that review, this separate flag authorizes expanded reads for **all projects in the plan, for this invocation only**:

```sh
python3 -B -m beforewipe assess --plan private-plan.json --allow-git-object-read --format json
```

It does not execute Git, traverse blob entries, open work-file contents, read packfiles/config/alternates, or follow external stores. A missing loose object remains unknown even if Git can resolve it elsewhere. `--allow-content-read` does not authorize Git object reads, and `--allow-git-object-read` does not authorize selected-file reads. To use both independently reviewed checks, pass both flags to `verify`.

For supported ordinary SHA-1 repositories and v2/v3 indexes, it detects staged additions, ID or mode changes, deletions, and index-only versions. Renames are reported as a deletion and addition without rename pairing. Symlink and gitlink changes are compared by stored IDs/modes; their targets and repository contents are not opened. This confirms index/HEAD differences, not that those versions are absent from working files, important, intact, or backed up.

Every project result includes `observations.staging`, including access/format failures. The existing `staging_status` mirrors its `status`:

| Field/value | Meaning |
| --- | --- |
| `status: confirmed_risk` | At least one index/HEAD difference was observed; project needs attention even if selected files match |
| `status: no_difference_observed` | No difference within a complete supported ID/mode comparison; repository recovery remains unknown |
| `status: unknown` | No confirmed difference and insufficient evidence, or access was not authorized |
| `status: unsupported` | An explicitly recognized unsupported layout or state |
| `coverage: complete` | All paths in this supported index/HEAD comparison were compared; excludes blob integrity and recovery |
| `coverage: incomplete / unsupported / not_inspected` | Coverage gaps, unsupported state, or no expanded-read authorization |
| `changes`, `counts_are_lower_bounds` | Added/modified/deleted path counts; incomplete or uninspected counts are lower bounds, so zero is not absence |
| `reason_codes`, `paths_compared` | Content-free gap reasons and count of paths actually compared |

A readable subtree's confirmed differences survive another subtree's failure. Detected index/HEAD/ref or root replacement invalidates the comparison; this remains a bounded, non-atomic observation. The [implementation and validation note](docs/STAGED_WORK_DETECTION.md) explains the evidence and security tradeoffs.

## Check selected restored files

First restore important work using your trusted backup workflow into a separate directory. Review each file selection **in both copies** for secrets. Then explicitly authorize reading those selected bytes:

```sh
python3 -B -m beforewipe verify --plan private-plan.json --allow-content-read --format json
```

`--allow-content-read` confirms that **all selected files in both copies are non-sensitive**, and permits streaming their contents into SHA-256 comparisons. Do not use it on arbitrary files, secret-bearing source files, configuration, transcripts, or session databases. Name filters cannot determine whether an otherwise ordinary source file contains an embedded secret.

Verification refuses known sensitive names, `.git`/agent-state selections, JSON/JSONL/log/database selections, overlapping roots, symlinks, special files, same-inode/hardlinked copies, and files over 32 MiB. A selection is numbered in the report; its name and digest are not emitted. Files changed or replaced during the check become unknown when detected.

**`verified_content_match` means only that the selected files in two distinct local file instances had matching bytes at check time.** It does not prove the copy came from a backup, is on a different device, will survive the wipe, retains permissions, or is runnable. A copy on the same disk can match perfectly and still be lost in a wipe. The tool neither performs nor verifies a complete restore. Keep the original until you independently demonstrate the recovery you need.

Completed file-comparison results explicitly carry `verification_scope: selected_file_bytes` and `recoverability: unknown`, including when all selections match. A matching working file does not establish that staged-only versions of that file were preserved.

## Understand the evidence

| Evidence | Example | Meaning |
| --- | --- | --- |
| Observed | Staged ID/mode difference with consent, stash ref, file outside index, mismatching selected bytes | Directly checked fact within scope, not proof of importance or loss |
| Inferred | Tracked metadata changed; branch tip absent from cached remotes | A reason to review local work; false alarms are possible |
| Unknown | Uninspected/incomplete staging, session usability, live remote state, excluded file | No supporting verification; do not treat it as recovered |
| Verified | Matching selected bytes in separate file instances | Only the stated content comparison passed |

There is no numerical readiness score. Project and session recovery remain unknown even when individual file checks pass.

## Current limits

- Supports ordinary **SHA-1 Git repositories with complete v2/v3 indexes** and loose/packed refs. Linked worktrees, gitfiles, bare repositories, index v4, split/sparse indexes, SHA-256 repositories, and reftable are unsupported or unknown. No automatic config changes or conversion are attempted.
- **Default assessment does not detect staged-only changes.** The optional comparison detects index/HEAD differences only when authorized and supported commit/tree objects are available loose. Packed/external/missing objects, unborn or missing HEAD, replacement refs, non-remote symbolic refs, conflicts, intent-to-add entries, malformed data, and limits leave explicit gaps or unknowns. No automatic unpacking or layout conversion occurs. Exact working-file changes, reflog-only work, history integrity, LFS payloads, submodule recovery, and nested-repository completeness are unverified. Preserve index and objects as well as working files.
- Files outside the index include ignored build outputs as well as valuable work. Ignore rules are not read. Branch-tip comparisons are exact-tip comparisons, not ancestry or “unpushed commit” calculations; merged or stale branches can raise false alarms.
- Session inventory is generic, not tied to a versioned Codex/Claude format. A file count is not a conversation count. Transcripts may contain secrets and are never parsed or content-verified.
- Known sensitive names and directories are excluded before opening or descending. This intentionally over-excludes some harmless names. Excluded work may still be important and needs a separate trusted workflow. There is no secret detection promise for user-attested content selections.
- Inventories are bounded to 20,000 directory entries and 32 levels per root; Git structural files to 16 MiB; plans to 128 KiB and 100 items per section; content checks to 200 selected files per recovery item and 32 MiB per file. Optional Git object reads are limited to 8 MiB per compressed/expanded object, 32 MiB total in each representation, 4,096 object attempts, 100,000 tree entries, and 32 subtree levels per project; commit headers are capped at 64 KiB. Failed object reads/inflation conservatively consume their possible byte budget (with one-byte overflow probes). Gaps are visible, never counted as success.
- Assessments are not atomic snapshots. Avoid concurrent changes. Descriptor-relative access prevents symlink traversal, but this is not a sandbox against a hostile OS, privileged attacker, or malicious filesystem. OS-level reads may update access timestamps. Mount points and different-device survival are not verified.
- Windows is not supported. Initial validation used synthetic fixtures on macOS, Python 3.9.6, Git 2.50.1. CI tests Linux and Intel macOS on Python 3.9/3.13/3.14; Python 3.9 is a compatibility check, not a recommendation to use an unsupported interpreter. Remote results are available in the repository's Actions tab after publication. No real personal machine was scanned during development.

## Test and contribute

```sh
python3 -B -m unittest discover -s tests -v
```

All **109 tests passed locally**, including **10 independent object-reader audit tests**, **33 staging regressions**, and the **66 tests** from the earlier review. See the [object-reader security review](docs/GIT_OBJECT_SECURITY_REVIEW.md) for reproduced defects, before/after evidence, and pilot conditions. Tests require Git only for isolated synthetic fixture creation and independent Git-state comparisons. The added suite checks staged edits/additions/deletions/renames, index-only versions, mode/type changes, partial coverage, real packed/split/sparse/worktree layouts, malformed objects/indexes/refs, compression limits, consent isolation, and replacement attacks. For valid fixtures, read audits forbid network, subprocesses, writes, work-file reads, and blob/config/external-store reads during assessment. The original default metadata-only audit remains unchanged. One original test executes a known synthetic restored program; verification never executes user code. See the [staged-work validation results](docs/STAGED_WORK_DETECTION.md) for actual executed checks and their limits.

The [independent engineering and security review](docs/ENGINEERING_SECURITY_REVIEW.md) records confirmed defects, fixes, evidence, and remaining limits. The revised alpha is suitable only for a small, supervised, consent-based pilot with independent Git review and no destructive action; comprehensive risk detection has not been established.

Run directly from source; installation is optional. To install in an existing isolated Python environment: `python3 -m pip install --no-build-isolation --no-deps .` (requires setuptools 61+). No telemetry or service account is involved. See [SECURITY.md](SECURITY.md) before submitting sample data. Contributions should add synthetic regression fixtures for changed behavior and preserve explicit scope, uncertainty, and secret avoidance. License: [MIT](LICENSE).

## Why this scope

The [project concept](BEFOREWIPE_PROJECT_CONCEPT.md) is authoritative. Existing solutions already handle substantial parts of recovery: [restic](https://github.com/restic/restic/blob/master/doc/010_introduction.rst) creates and checks backups; [chezmoi](https://www.chezmoi.io/what-does-chezmoi-do/) manages dotfiles; [Git](https://git-scm.com/docs/git-status) exposes working state. [Git remote-tracking refs](https://git-scm.com/book/en/v2/Git-Branching-Remote-Branches) describe cached remote state rather than current remote availability. BeforeWipe adds a small local evidence-and-action report across developer work and agent-session inventory, plus narrowly scoped restored-file comparisons. It does not replace these tools or claim proven novelty.

This version demonstrates the mechanism on controlled fixtures. Whether it helps developers discover overlooked work with tolerable effort and false alarms still needs real developer evaluation with informed access authorization. A useful first evaluation is to declare a few projects and session directories, record overlooked risks, restore selected important work independently, then ask whether the report improved the readiness decision. No user study or actual wipe/recovery has been performed.
