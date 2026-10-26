# Product reality check and pilot decision

2026-10-26 — **READY FOR SUPERVISED HUMAN PILOT**, under the existing security review's conditions and the [executable pilot procedure](PILOT.md). This is permission to learn from a small, separately authorized cohort, not evidence that the product is broadly useful or that a machine can be wiped. No real developer participation was available or initiated: **0 human participants, 0 real-data assessments, 0 transmissions, 0 wipes**.

Read the [foundational vision](../BEFOREWIPE_PROJECT_CONCEPT.md), README/security guidance, all seven runtime modules, all four test modules, CI, and the [engineering/security review](ENGINEERING_SECURITY_REVIEW.md), [staging implementation report](STAGED_WORK_DETECTION.md), and [object-reader review](GIT_OBJECT_SECURITY_REVIEW.md), and their saved manifests/results. The final conditional-go review governs this decision. Runtime source hashes still match its manifest; no assessment code or access boundary was changed.

## A. What the developer actually gets

BeforeWipe is currently a **review aid inside remembered, explicitly selected roots**. It can prompt examination of files outside an index (including ignored files), tracked metadata differences, stashes, detached HEAD and cached branch-tip differences. It inventories selected session directories and checks selected restored-file bytes after separate authorization. With reviewed non-sensitive loose commit/tree objects, it diagnoses index/HEAD differences that working-file equality cannot expose. This is useful evidence, but the human still identifies the important files behind aggregate/redacted counts and determines whether they were preserved.

It requires prior knowledge of project roots, exact session locations, restore destinations, important file selections, and which data can be reviewed as non-sensitive. It cannot search outside those roots, infer overlooked directories from a report, or follow a symlink to find forgotten work. A developer who forgets a project cannot rely on this tool to find it. A manual recollection checklist may help that developer, but its benefit must be attributed separately. Scope expansion requires a reviewed new plan. Giving a broad folder to the project reader also does not discover child repositories automatically: a project entry expects a Git root.

It cannot establish importance, complete worktree contents, reflog-only recovery, blob/history integrity, usable sessions, full repository/context restoration, backup provenance, off-device durability, or runtime dependencies. Packed/external/missing objects and unsupported layouts limit staging. Metadata-only assessment does not inspect staging in any supported project. A file match can coexist with losing the only staged version. Excluded configuration can still matter. The product offers no comprehensive-machine conclusion.

Redaction protects reports but makes triage less direct: an ID and count do not tell the developer which file needs preserving. The pilot measures manual lookup and facilitator effort rather than treating a technically correct aggregate warning as a successful discovery. Attention and unknown summary counts are item statuses, not counts of important risks. An attention item can also contain multiple unresolved unknowns.

## B. What was prepared

- [One practical protocol and private worksheet](PILOT.md): baseline before findings, limits/teach-back, exact plan approval, metadata first, separately approved optional reads, independent Git/recovery examination, risk reconciliation, effort and decision measures. Three to five volunteers; recruitment and real-data access still need explicit human authorization.
- [One synthetic-only rehearsal script](../scripts/pilot_dry_run.py): refuses an existing destination, authors new environments, records simulated authorizations, executes the existing CLI in text/JSON, and independently checks access and Git/recovery truth. It is a development harness, not a participant assessment launcher or consent system.
- [Saved execution evidence](pilot/results.json), [independent oracle](pilot/oracle.json), [synthetic approval records](pilot/approvals.json), actual text/JSON outputs, and [full suite output](pilot/full-test-results.txt).

No new CLI, parser, automatic discovery, pack support, fallback Git, service, or runtime dependency was necessary. README wording now makes the selected-directory boundary explicit and links the pilot. Existing flags and manual plan review suffice for this supervised cohort.

## C. Controlled dry run actually executed

The recorded run used macOS 27.0.1 arm64, Python 3.9.6, Apple Git 2.50.1. All **109 existing tests passed**, no failures/skips, in 14.340 seconds. These are regression checks, not population coverage evidence. No remote CI, Linux or other-Python execution was performed here.

The rehearsal created nine initial project roots plus a session directory and a recovery selection, a deliberately omitted tenth project, and a seed repository. The clone seed has seven commits, nested trees, and reused history. Git fixture setup and independent oracles used an isolated HOME/configuration, disabled hooks/fsmonitor/automatic maintenance, local-only file transport and no network. Assessment itself never invoked Git. The small fixtures exercise realistic state/layout mechanisms, not representative developer workload sizes or prevalence.

To reproduce from the source directory, choose a **new physical destination** (on macOS use `/private/tmp`, not symlinked `/tmp`):

```sh
python3 -B scripts/pilot_dry_run.py --directory /private/tmp/beforewipe-pilot-new-run
```

Existing destinations are refused before fixture creation. Evidence is written below the new tree, outside assessed machine/copy roots. Original project work is never supplied. Fixture construction intentionally makes synthetic commits, stages work and runs GC; assessments do not modify those fixtures. Do not apply the setup to real work.

Seven assessment invocations were executed in each of text and JSON form, then repeated through the same CLI entry point under instrumentation; evidence must agree except for timestamps:

| Step | Access authorized | CLI exit | Attention / unknown / matching items |
| --- | --- | --- | --- |
| 01 default | Structural/filesystem metadata only | 1 | 8 / 3 / 0 |
| 02 objects only | Also reviewed loose commit/tree objects | 1 | 8 / 3 / 0 |
| 03 content only | Selected bytes, no object consent | 1 | 8 / 2 / 1 |
| 04 both | Both separate permissions | 1 | 8 / 2 / 1 |
| 05 revised selections | File consent renewed for two added selections; objects disabled | 1 | 9 / 2 / 0 |
| 06 approved new root | Newly reviewed plan adds forgotten project; metadata only | 1 | 9 / 3 / 0 |
| 07 recovery only | Matching selected file, no projects/sessions | 0 | 0 / 0 / 1 |

All reports retained `readiness: not_determined`. Step 07 demonstrates why even exit 0 is not a recovery or wipe verdict. Simulated authorization records are generated for authored synthetic data; they are not human consents or comprehension measurements.

### Packed objects: observed practical effect

Each of the first seven rows below has exactly **one staged modification**, established by independent `git diff --cached --no-renames --name-status -z`. Its working `src/app.py` equals HEAD, while the index version differs. Default mode never diagnoses this staging state; incidental metadata attention is not a diagnosis.

| Fixture / ordinary construction | Required object layout | Authorized BeforeWipe staging result |
| --- | --- | --- |
| Newly initialized loose repository | Single-link loose commit/trees | `confirmed_risk`, complete; one modification |
| Local `git clone --no-hardlinks` control | Copied single-link loose objects | `confirmed_risk`, complete; one modification |
| Local transport `git clone --no-local` | Packed commit/trees | Unknown, incomplete; missing loose-object reason; zero lower-bound changes |
| Initialized repository after ordinary `git gc` | Packed commit/trees | Same unknown; zero paths compared |
| `git gc`, then an ordinary empty commit | Loose HEAD, packed root/subtree evidence | Same unknown; a new loose commit does not restore tree coverage |
| Default local-path `git clone` | Loose objects hardlinked by Git (HEAD link count 2) | Unknown, incomplete: `hardlinked_metadata_refused` |
| Supported SHA-1 repo with actual index v4 | Loose objects, unsupported index | Unsupported; entire project inventory unavailable |
| Reflog-only committed work | Loose objects; current index/HEAD equal | `no_difference_observed`, complete staging; abandoned commit not diagnosed |

Transport cloning was through a local path, not an internet clone. It exercises Git's transport packing without any real repository/network access. Local clone defaults depend on source layout/filesystem; here they hardlinked objects. The hardlink refusal is a deliberate security guard, not a recommendation to weaken it. Packed refs alone are supported and are different from packed objects.

The optional reader directly diagnosed two of these seven deliberately selected staged-risk fixtures. This is a case matrix, **not a coverage percentage, expected real-world recall, or prevalence estimate**. The clone/GC mechanisms show that the gap arises in ordinary workflows; their frequency among developers remains unmeasured. No objects were unpacked and no fallback or permission expansion occurred.

### Risks, misses and noise

| Independent fact | Tool outcome | Product interpretation |
| --- | --- | --- |
| Important untracked idea and ignored scratch file in loose project | Three files outside index reported, including disposable build cache | Useful aggregate prompt; human still has to locate and judge them. Generated cache adds noise to the same prompt. |
| Stash exists with an important version | `stash_present` in default mode | Specific presence detection; stash contents/recovery unknown. |
| Source notes changed; selected restored notes are stale | Metadata prompt initially; explicit mismatch only after revised file selection | Detection of wrong restored bytes depends on prior selection and file-read consent. |
| Initial selected app bytes match; restore has no `.git`, no important idea or scratch, no stash/index-only version | `verified_content_match` coexists with project recovery unknown and staging warnings | Narrow comparison correct; incomplete backup is not certified. Exact omitted repository state not established by that file match. |
| Revised selection includes missing idea | `selected_file_missing`, selection unknown; stale notes mismatch makes recovery item attention | Useful explicit missing-file gap; recovery remains unresolved. |
| `.env` represents needed synthetic configuration | Exclusion count/coverage warning; contents never inspected | Important excluded material is not identified or recovery-tested; independent workflow required. |
| Two synthetic session files; copy contains only one | Source file inventory and recovery unknown | Missing session copy is not diagnosed: copy is outside session assessment and transcript verification is refused. No real application/session usability test was performed. |
| Important reflog-only commit exists but no surviving branch contains it | Current staging complete/no difference, project recovery unknown; no reflog diagnosis | Specific important risk missed despite a correct narrow comparison. |
| Forgotten project's untracked work is outside the initial plan; symlink points there | No project finding; symlink counted as a gap, not followed | Outside-scope miss, revealed only by harness oracle. Found after an explicit new-root plan, not automatically. |
| Noise repository has a touched timestamp but HEAD-equal bytes | Inferred working-tree metadata warning | Deliberate false alarm as a content-loss prompt; no file-byte change. |
| Older local branch is an ancestor of cached remote tip | Inferred exact-tip warning | Deliberate false alarm as an unpublished-work prompt; no live-remote conclusion. |

The harness's independent recovery check confirms that a separately copied full synthetic repository retains identical index bytes, refs, staged bytes and stash content, and passes `git fsck --strict`. It extracts the staged version **from the copy into a new file** and executes that known synthetic program, producing `important version ONLY in index`. The working-only copy cannot supply that version. This demonstrates recovery of this fixture, not a general backup-system restore, device survival, session recovery or runnable development environment.

The [risk ledger](pilot/risk-ledger.json) preserves scenario-level classifications. A separate [Git inventory examination](pilot/independent-inventory.json) confirms the untracked/ignored paths; [delivery checks](pilot/delivery-checks.json) confirm existing-destination refusal and recorded source hashes. Fixture importance was assigned by construction; there were no humans who “previously overlooked” these risks. No human discovery count, recall, false-alarm rate, participant effort or comprehension score is claimed.

### Scope and authorization evidence

For every assessment, the instrumented CLI restricted root opens to the exact plan/approved roots; byte reads to plan/structural metadata, additionally known HEAD commit/tree inodes only with object consent, and selected files only with file consent. Directory enumeration was restricted to declared project/session inventories and their allowed refs. Work-file/blob/config/pack/reflog/alternate/session-content reads outside these allowances, write-mode opens, Python file opens, subprocesses and sockets would fail the run. These observations are harness-level checks, not an OS sandbox proof.

Object consent alone left recovery files unread. Content consent alone left staging `not_inspected`. An injected plan authorization and `verify` without file consent each exited 2. The omitted root was never enumerated by assessment until a separate expanded plan authorized it; its symlink was not followed. Machine/copy snapshots (mode, size, mtime, content hashes/symlink values) matched after every run. Access times are excluded, as reads may change them. The recorded runtime hashes match the audited version. No real-data tool or connector was used.

## D. What remains unproven and what comes next

Real usefulness, effort, comprehension, risk importance and distribution of layouts are entirely unproven. A supervised pilot can learn these without needing a new parser. The procedure requires independently examined Git state and selected repository/context restoration, original data retained, informed exact scope and optional-read consent, and the suite on the actual platform. Participants unable to review objects as non-sensitive stay in default mode; record that limitation instead of pressuring them to opt in.

Prioritize (1) human evidence that specific findings reveal overlooked important work and change a concrete next action, separating manual scope assistance; (2) whether people understand unknown/complete/match despite many aggregate warnings, and the effort required to locate the relevant files; (3) actual packed/unsupported encounter counts in this cohort and usefulness of the independent-review handoff. Consider broader Git support only after those observations justify its security/complexity cost. Do not add pack parsing or weaken hardlink checks merely to improve this synthetic matrix.

Proceed only after explicit human authorization for enrollment/access. Until then, stop at this completed synthetic rehearsal and the ready-to-use procedure. BeforeWipe does not make machine wiping safe.
