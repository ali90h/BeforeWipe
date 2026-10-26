# Alpha publication review — 2026-10-26

Target: `v0.1.0-alpha.1`, experimental source release under MIT. This reviews the proposed public distribution, not recovery safety or the security of arbitrary user repositories.

## Files, provenance and privacy

The supplied source directory had **no top-level `.git` directory and no inherited project history**. A new publication history is created from reviewed files. There was one nested Git repository in generated `demo-work/project`; it was authored by the synthetic demo, with one commit, six stored objects and only `example.invalid` author/committer email addresses. Its history, reflogs and all six stored objects were scanned locally. The whole generated `demo-work/` tree, including its Git database, simulated session and `.env` fixture, is excluded from publication.

Reviewed source, tests, examples, saved synthetic evidence, documentation and hidden collaboration/CI files. No symlinks were found. All publication candidates were UTF-8 text. A historical traceback contained six occurrences of a personal checkout prefix: these were replaced with `/workspace/BeforeWipe/`, retaining the failure evidence and assertions. No personal checkout paths or non-fixture email addresses remain in published file contents. Addresses ending in `example.invalid`, invented secret markers and the `PRIVATE_PASSWORD` URL are deliberate synthetic privacy-regression inputs, not working credentials. No actual developer plans, transcripts, reports, recovery copies or participant records are included. The new commit identity uses the owner's public GitHub alias and GitHub no-reply address, not a private email or full name.

Only explicit source/documentation/test/example/CI paths are staged. Ignore rules exclude generated demos, local audit output, private pilot records, private plans/reports, environment files and private-key file extensions. Ignore rules do not substitute for inspecting the actual Git index and release tree. No nested repositories or generated fixture data are part of the public tree.

## Checks performed before upload

- **109/109 tests passed**, no failures or skips, on macOS with Python 3.9.6 and Apple Git 2.50.1 (13.845 seconds).
- SHA-256 checks against `docs/object-review/manifest.json` confirm every recorded runtime module, test and preserved before-source file is unchanged. MIT license text remains intact. Publication changes concern documentation and collaboration/CI files.
- Gitleaks **8.30.1**, downloaded from its official release and checked against the release SHA-256 manifest: no detected secrets in the initial directory scan, nested synthetic Git history, or export of every stored nested object. The final staged snapshot and new publication history are scanned again before the first push, without custom exclusions or a finding baseline. Scanner output is redacted and retained locally outside the release.
- Additional inspection for personal home paths, non-fixture email addresses, credential-bearing URLs, private key material, hidden files and generated data. Only the synthetic `.invalid` credential URL is present in tests. No working credentials were detected. Automated matching cannot prove that every possible secret has been found.
- Fresh synthetic CLI exercise: demo exits 0, assessment and selected-file verification exit 1 with `readiness: not_determined`, and an existing demo destination is refused with exit 2. No real project was assessed.
- Actionlint **1.7.12** validates both workflows. Issue forms and Dependabot configuration parse as YAML. Local relative Markdown links are checked before publication.

CI is configured for Linux and Intel macOS with Python 3.9, 3.13 and 3.14. It uses read-only repository permissions, full commit SHA pins for checkout/setup, no persisted checkout credentials, bounded job timeouts and no secrets or uploaded test artifacts. A separate checksum-pinned Gitleaks job scans fetched history and current files with redacted output. Only `push`, ordinary `pull_request` and manual dispatch triggers are used. See [checkout releases](https://github.com/actions/checkout/releases), [setup-python releases](https://github.com/actions/setup-python/releases), and [Gitleaks](https://github.com/gitleaks/gitleaks) for upstream sources. Configuration validation alone does not establish remote success; inspect the repository's Actions runs for actual outcomes.

## Public guidance

README begins with an explicit prohibition on using BeforeWipe to decide whether to wipe a machine. It explains separate scope/object/content permissions, packed-object and other coverage gaps, selected-file-only verification, unknown recovery and retained originals. The [one-volunteer invitation](VOLUNTEER.md) begins with supervised invented data; the [pilot](PILOT.md) retains the separate consent and independent-review conditions for any later real-data session. Issue forms prohibit private data and raw real reports. [Security guidance](../SECURITY.md) describes private vulnerability reporting when available and a data-free fallback if unavailable.

No volunteers were contacted, enrolled or assessed. Publishing the invitation does not authorize access to anyone's data. BeforeWipe does not make wiping safe.
