# BeforeWipe v0.1.0-alpha.1

Experimental open-source Alpha, licensed under [MIT](../LICENSE). Source distribution only; no PyPI package, telemetry, hosted scanner or automatic updates. This release invites one supervised volunteer to start with [invented data](VOLUNTEER.md). Human usefulness remains unproven.

## What it does

- Assesses explicit local project/session roots using bounded metadata reads.
- Optionally compares staged index/HEAD IDs and modes using reviewed local loose commit/tree objects, with separate `--allow-git-object-read` authorization.
- Compares exact selected restored-file bytes after separate `--allow-content-read` authorization and review of both copies as non-sensitive.
- Emits scoped observations, uncertainty and selected-file matches. It never produces a machine-wide safety verdict.

Run from source using the instructions in [README](../README.md). The 109 existing tests use synthetic fixtures. See [publication checks](PUBLICATION_REVIEW.md) for local validation and the repository's Actions tab for actual remote CI results; configured jobs alone do not prove platform validation.

## Conditions and gaps

**Do not use this release as a wipe decision. It does not prove that wiping is safe. Keep originals intact.** It neither creates backups nor certifies recovery. A matching local file or exit 0 can coexist with losing staged-only work, stashes, history, important unselected files or both copies on the same disk.

Default assessment cannot diagnose staging. Optional object reading does not support required Git packfiles, external stores or many Git layouts, and can read arbitrary disguised bytes before validation. Do not enable it on unreviewed or secret-bearing objects. A complete supported staging comparison does not establish blob availability or restoration.

Unknown/unsupported results remain unresolved. Forgotten roots, reflog-only work, excluded sensitive files, session usability, full history integrity, LFS/submodules, backup provenance and independent-device survival remain unverified. Scope must be stable and trusted; this tool is not a sandbox against a hostile filesystem.

No real participant data, transcripts, private plans or credentials belong in the repository or its issues. Report only synthetic reproductions, following [SECURITY](../SECURITY.md). The reviewed assessment/runtime source is unchanged by this publication preparation; documentation, CI and public collaboration files were prepared for Alpha.
