# Supervised usefulness pilot — begin with one consenting developer

For the Alpha, recruit **one volunteer first** using [the public invitation](VOLUNTEER.md). Begin with its synthetic-only session. This is a feasibility and comprehension check, not a cohort result. Any subsequent real-data session follows every consent and review condition below. The original 3–5-person learning rule at the end applies only to a later, separately agreed cohort; one session cannot satisfy it.

Status: ready to use after explicit human authorization; **no participants have been recruited or assessed**. Aim: learn whether BeforeWipe reveals important overlooked work and improves a developer's next recovery decision. This is not wipe approval. Keep originals intact; no wipe, deletion, cleanup, repository conversion, unpacking, or push/fetch is part of the pilot.

Use one facilitator and an independent Git/recovery reviewer (a second person, or a reviewer who records findings before seeing the BeforeWipe report). Allow about 45 minutes of active participant effort plus independently needed backup/restore time. Do not rush an incomplete restore to finish the session. One to three trusted project roots and optionally one exact session directory per participant are sufficient. Run the existing suite on the actual pilot platform first:

```sh
python3 -B -m unittest discover -s tests -v
```

## 1. Explain limits and capture the baseline (5 minutes)

Read this aloud before showing findings:

> BeforeWipe examines only directories you name. It cannot find a forgotten project elsewhere, even through a symlink. Default mode does not inspect staging. Optional staging comparison cannot handle required packed objects or many other Git layouts. A file match means selected bytes match now; it does not verify repository recovery, independent backup survival, or that your machine can be wiped. Sessions are inventory only. Unknown means unresolved, including when another finding says attention or complete.

Participant records what they currently think needs preserving, what is already backed up, known concerns, and their intended next pre-wipe action. Use private item/risk aliases, not paths or contents in the shared worksheet. Define “important” as work/context the participant says would cause material rework or loss if unavailable. Record this criterion before showing the report; new risks can be rated important afterwards with a reason.

Participant privately considers forgotten checkouts/worktrees, side projects, Downloads/Desktop or other scratch locations, external volumes, other users, ignored work, sessions, local branches/stashes/reflogs, and excluded configuration. This is a recollection checklist, **not permission to scan those locations**. Record any roots remembered because of the checklist as facilitator-assisted scope discovery, separately from tool discovery. No machine-wide discovery claim is possible.

## 2. Approve the exact scope (5 minutes)

Participant creates a private plan using [examples/plan.json](../examples/plan.json), deleting unused sections. Select exact physical paths with no symlink ancestors; no home/root scopes. Review trusted Git structural metadata as non-sensitive as well: default metadata can also contain disguised bytes. Leave untrusted or sensitive roots out. Keep scopes stable during checks.

Review every project/session root and every recovery source, destination, and selected file. Record plan revision/hash, opaque item IDs, approval time, participant agreement, and approved operations in the private worksheet. Explain that every project entry is recursively inventoried within limits, while recovery selections are exact files. Any additional root or selection requires a new plan review and approval. Private plan paths stay with the participant. Do not send plans, reports, or repository data anywhere.

Approve default metadata assessment first. Separately ask for approval of local report storage if desired. Save results in a new private directory outside assessed roots; reports still disclose IDs/counts. The participant can instead view stdout without saving it.

```sh
# Substitute the exact reviewed plan path. Run from the BeforeWipe source directory.
PLAN=/absolute/private/pilot/plan.json
python3 -B -m beforewipe assess --plan "$PLAN"
# Optional machine-readable output, within the same approved scope:
python3 -B -m beforewipe assess --plan "$PLAN" --format json
```

Exit 1 is normal when attention/unknowns remain. Exit 2 is invalid input/setup failure, not an assessment. Exit 0 can mean selected files matched in a recovery-only plan; it is never wipe approval.

## 3. Interpret and optionally expand reads (10 minutes)

Participant explains each finding and chooses the next action before facilitator correction. Record confusing conclusions verbatim only if non-sensitive; otherwise use a short paraphrase.

| Result | Working interpretation |
| --- | --- |
| Observed / `confirmed_risk` | A stated fact was seen, not proof of importance or of backup loss. |
| Inferred | Investigate; metadata touches, generated files, or cached-tip differences can create noise. |
| Unknown / unsupported / incomplete / not inspected | A gap remains. Zero lower-bound changes do not mean zero risks. |
| `complete` staging | Only the supported index/HEAD ID/mode comparison completed. No blob/history/restore proof. |
| `verified_content_match` | Only explicitly selected bytes in distinct local file instances matched at check time. |

Keep expanded reads optional. Declining them is a valid pilot outcome; record the reason and unresolved coverage. Object consent covers **all project entries for that invocation**. If only some qualify, prepare and explicitly approve a smaller plan first. Do not quietly reuse a wider plan.

- **Object authorization:** participant can actually review every selected repository's objects as non-sensitive, including commit messages, tree names, and arbitrary disguised bytes. If not, keep this disabled and use a separately authorized trusted Git review. A filename filter or successful parser cannot provide that review.
- **Selected-file authorization:** after an independent restore to a separate destination, participant reviews **both copies of every selection** as non-sensitive. No transcripts, databases, secrets, or arbitrary config files. Separate local copies can still share the same disk and fail together.

Only after the respective approvals:

```sh
# Object consent alone never reads selected recovery-file contents.
python3 -B -m beforewipe assess --plan "$PLAN" --allow-git-object-read
# File consent alone never authorizes Git objects.
python3 -B -m beforewipe verify --plan "$PLAN" --allow-content-read
# Only if both were separately authorized for this exact plan:
python3 -B -m beforewipe verify --plan "$PLAN" --allow-content-read --allow-git-object-read
```

Do not change real repositories to improve tool coverage. Keep packed/unsupported results unresolved in the report, even if independent examination later explains them.

## 4. Independent truth and recovery check (15+ minutes)

Obtain separate participant authorization for this examination: trusted Git/backup tools can read contents, config, reflogs, packs, or external stores beyond BeforeWipe's boundary. Review any external stores or worktree locations and authorize their exact scope first. Do not run automated fallback Git inside BeforeWipe. Do not run build/test code without participant review and authorization. Participants retain control of all private output.

The reviewer initially works without seeing the BeforeWipe findings. For each approved repository, inspect working changes; staged paths, IDs and modes; untracked **and ignored** work; local branches relative to trusted cached history; stashes; detached/reflog-only work; nested repositories, submodules and LFS dependencies where applicable. Establish facts, not just alert counts. Do not contact remotes. Record unverifiable items as unresolved. The participant can privately examine additional remembered locations only under a fresh authorization; record those outside-scope risks separately.

Example local commands for a trusted approved repository, after the independent-read authorization (these do not cover everything above):

```sh
PROJECT=/absolute/reviewed/project
GIT_OPTIONAL_LOCKS=0 git --no-pager -c core.fsmonitor=false -C "$PROJECT" status --short --untracked-files=all --ignored=matching
GIT_OPTIONAL_LOCKS=0 git --no-pager -c core.fsmonitor=false -C "$PROJECT" diff --cached --no-ext-diff --no-textconv --no-renames --name-status
GIT_OPTIONAL_LOCKS=0 git --no-pager -C "$PROJECT" ls-files --stage
GIT_OPTIONAL_LOCKS=0 git --no-pager -C "$PROJECT" for-each-ref refs/heads refs/stash
GIT_OPTIONAL_LOCKS=0 git --no-pager -C "$PROJECT" reflog show --all --format='%h %gD'
GIT_OPTIONAL_LOCKS=0 git -C "$PROJECT" count-objects -v
```

These trusted Git commands are not a sandbox; Git may consult configuration/external storage. Review its configuration and dependencies before using them. Do not use reset, checkout, stash/pop, GC, or repair commands on originals during the pilot. Work through any restoration experiment in a separate destination, with the original stable and intact.

Using the participant's trusted backup workflow, demonstrate selected important work from a separately restored copy. Verify staging via the restored index **and the availability of its referenced versions**, relevant refs/history/stashes/reflogs, important ignored/untracked files, dependencies, and usable context. `git fsck --strict` alone cannot prove backup inclusion or completeness; a clean clone omits uncommitted/staged/stashed/reflog-only context. Test opening restored sessions through the appropriate trusted application only if separately authorized; inventory is not usability proof. Record omitted checks and off-device/backup-provenance uncertainty. BeforeWipe does not create or certify this restore.

Reconcile both evidence sets with the participant. A generic unknown, incidental metadata warning, or overall attention status does **not** count as detecting a specific staged/reflog/recovery-loss risk. A missing selection explicitly identified as missing remains recoverability-unknown but is a useful diagnosis of that gap.

## 5. Record outcomes and close (5 minutes)

Use one private sheet per participant; no new service or telemetry is needed. Copy this small record and add risk rows:

```text
Participant alias: ____  Platform/version: ____  Date: ____
Plan revision/hash: ____  Approved item IDs: ____
Default scope consent/time: ____  Local report storage consent: ____
Object consent/time/plan (or declined): ____
Selected-file consent/time/plan (or declined): ____
Independent Git/recovery consent/time/scope: ____
Known concerns before report: ____  Intended next action before report: ____
Active minutes: scope __ reading __ interpretation __ independent review __ restore __
Elapsed restore/transfer minutes: ____  Facilitator interventions: ____
Risk alias | important? why | known before? | inside approved scope? |
first prompt: default/object/file/checklist/independent/participant |
BeforeWipe diagnosis vs unknown/missed | independent evidence |
false alarm? | confusing conclusion | chosen next action
____
Unexamined/declined scope and unresolved recovery checks: ____
Next action after report; what changed and why: ____
Teach-back before correction (correct/incorrect for each): ____
Teach-back after explanation (correct/incorrect for each): ____
Continue/stop reason: ____
```

Ask four teach-back questions without coaching first: (1) Can work outside the plan be discovered? (2) Can packed staging with zero reported changes be treated as clean? (3) Does `complete` staging or a matching working file preserve an index-only version? (4) Does a file match/exit 0 prove repository recovery or survival of a wipe? Expected answer to all: **no**, with the participant explaining the unresolved evidence. Correct misunderstandings before continuing expanded reads or closing. Record initial and corrected comprehension separately.

Report descriptive counts per participant, not population estimates:

- **Overlooked important risks discovered:** participant did not know the risk before; specific finding led to independent confirmation and a stated recovery/review action. Attribute default, object and file findings separately; attribute checklist/facilitator-only discoveries separately.
- **Important risks missed:** independent examination confirms an important risk with no specific tool diagnosis. Report unknown-with-warning separately from silent absence and split inside/outside approved scope. The denominator is independently examined risks, not all machine work; unexamined areas remain unmeasured.
- **False alarms/noise:** participant and reviewer confirm no relevant loss risk behind a review prompt (e.g. timestamp-only change or disposable output). Count distinct prompts, not each file in an aggregate warning. Do not count unresolved unknowns as false alarms.
- **Effort:** active minutes by step, elapsed restore time, interventions, skipped optional reads and abandoned sessions. Machine runtime is not participant effort.
- **Understanding and decision change:** initial/corrected teach-back results, unsupported claims made by the participant, and concrete changes in intended next action. No hypothetical satisfaction score substitutes for a confirmed discovery.

Preregister a lightweight learning rule: continue improving toward another supervised cohort if at least two participants find an independently confirmed previously overlooked important risk prompted by BeforeWipe and choose a concrete additional action; target median active effort at or below 45 minutes (report review/restore effort separately). This is a proposed learning threshold, not validated evidence of product fit. Even if met, list every important miss. Any unauthorized access, changed original data, or uncorrected belief that a match makes wiping safe stops that session and pauses expansion pending review. If usefulness is low or packed/unsupported gaps dominate, prioritize scope guidance and clearer actionable handoff before adding a new parser. No enrollment, real assessment, upload, or participant messaging is authorized by this document itself.

Synthetic rehearsal: `python3 -B scripts/pilot_dry_run.py --directory /physical/path/to/NEW/tree`. It never accepts existing data, creates only synthetic fixtures, records simulated authorizations explicitly as non-human, and runs CLI plus instrumented CLI comparisons. See [the actual dry-run findings](PRODUCT_REALITY_CHECK.md).
