"""Plans, evidence, and deliberately narrow recovery checks."""

import json
import os
import re
import stat
import struct
from datetime import datetime, timezone

from . import __version__
from .fs import Root, ScopeError, absolute_scope_path, digest_file, fingerprint, relative_parts, scope_key, sensitive
from .gitmeta import assess_project
from .staging import staging_unknown

MAX_PLAN_BYTES = 128 * 1024
ID = re.compile(r"[a-z][a-z0-9_-]{0,39}\Z")


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ScopeError("duplicate_plan_key")
        result[key] = value
    return result


def load_plan(path):
    # The selected plan is user-authored configuration; it must contain no secrets.
    path = absolute_scope_path(path)
    if sensitive(path.name):
        raise ScopeError("sensitive_plan_refused")
    with Root(path.parent) as root:
        raw = root.metadata((path.name,), MAX_PLAN_BYTES)
    try:
        data = json.loads(raw, object_pairs_hook=unique_object)
    except (ValueError, UnicodeError, RecursionError):
        raise ScopeError("invalid_plan_json") from None
    if not isinstance(data, dict) or set(data) - {"version", "projects", "sessions", "recoveries"}:
        raise ScopeError("invalid_plan_structure")
    if type(data.get("version")) is not int or data["version"] != 1:
        raise ScopeError("unsupported_plan_version")
    seen, total = set(), 0
    for category in ("projects", "sessions", "recoveries"):
        items = data.setdefault(category, [])
        if not isinstance(items, list) or len(items) > 100:
            raise ScopeError("invalid_plan_items")
        for item in items:
            total += 1
            fields = {"id", "source", "restored", "files"} if category == "recoveries" else {"id", "path"}
            if category == "sessions":
                fields.add("tool")
            if not isinstance(item, dict) or set(item) != fields:
                raise ScopeError("invalid_plan_item_fields")
            label = item["id"]
            if not isinstance(label, str) or not ID.fullmatch(label) or label in seen:
                raise ScopeError("invalid_or_duplicate_item_id")
            seen.add(label)
            for field in (("source", "restored") if category == "recoveries" else ("path",)):
                value = item[field]
                if not isinstance(value, str) or not value or "\x00" in value or "~" == value[:1]:
                    raise ScopeError("invalid_scope_path")
                # Interpret relative paths against the plan, never the caller's cwd.
                item[field] = str(absolute_scope_path(path.parent / value))
            if category == "sessions" and item["tool"] not in ("codex", "claude", "other"):
                raise ScopeError("invalid_session_tool")
            if category == "recoveries":
                files = item["files"]
                if not isinstance(files, list) or not 1 <= len(files) <= 200:
                    raise ScopeError("invalid_recovery_selection")
                for value in files:
                    relative_parts(value)
                if len(set(files)) != len(files):
                    raise ScopeError("duplicate_recovery_selection")
    if not total:
        raise ScopeError("empty_plan")
    return data


def finding(code, evidence, detail, action):
    return {"code": code, "evidence": evidence, "detail": detail, "next_action": action}


def project_result(item, allow_git_object_read=False):
    result = {"id": item["id"], "kind": "project", "status": "unknown", "findings": []}
    meta = assess_project(item["path"], allow_git_object_read=allow_git_object_read)
    result["observations"] = meta
    counts, findings = meta["counts"], result["findings"]
    for error in meta["coverage_errors"]:
        findings.append(finding("git_metadata_incomplete", "unknown",
                                "Git reference inspection was incomplete: " + error["reason"] + ". "
                                "Branch and stash counts are unknown; independent working-tree observations are retained.",
                                "Review repository metadata and preserve all local branches and stashes independently."))
    if counts["metadata_changed"] or counts["tracked_missing"]:
        findings.append(finding("working_tree_metadata_differs", "inferred",
                                "Tracked file metadata differs from the Git index or a path is missing. "
                                "This is an inference about working files, independent of the staging comparison.",
                                "Review working and staged changes locally; preserve important work and test its recovery."))
    if counts["files_outside_index"]:
        findings.append(finding("files_outside_index", "observed",
                                "Files exist outside the index. This includes ignored files; importance is unknown.",
                                "Review untracked and ignored work locally and select important non-sensitive files for recovery checks."))
    if counts["unmerged_entries"]:
        findings.append(finding("unmerged_index", "observed", "The index contains unresolved merge stages.",
                                "Preserve the repository and working context before resolving conflicts."))
    if counts["stash_ref_present"]:
        findings.append(finding("stash_present", "observed", "A local stash reference exists; contents were not opened.",
                                "Review stashes locally and verify they survive your chosen backup and restore process."))
    if counts["branch_tips_absent_from_cached_remotes"]:
        findings.append(finding("branch_tip_not_in_cached_remotes", "inferred",
                                "Some local branch tips do not exactly match cached remote tips. "
                                "This does not prove commits are unpublished; ancestry and live remotes were not checked.",
                                "Review all local branches; verify recovery from a separately restored repository."))
    if meta["detached_head"]:
        findings.append(finding("detached_head", "observed", "HEAD is detached; its commit is not necessarily on a branch.",
                                "Review and preserve detached work and verify it is present after restoration."))
    if not meta["index_present"]:
        findings.append(finding("index_absent", "unknown", "No index was found; tracked coverage cannot be established.",
                                "Review whether this is a new, incomplete, or damaged repository."))
    if any(meta["inventory"].values()) or counts["unchecked_entries"] or counts["submodules"]:
        findings.append(finding("coverage_gaps", "unknown",
                                "Some entries were excluded, unsupported, inaccessible, or beyond scan limits.",
                                "Review excluded content, nested repositories, submodules, and sensitive material with appropriate tools."))
    staging = meta["staging"]
    if staging["status"] == "confirmed_risk":
        findings.append(finding("staged_changes_detected", "observed",
                                "The index differs from the physical HEAD tree in object IDs, paths, or modes. "
                                "Staged work is at risk if only working files are preserved. "
                                "Renames are counted as additions and deletions; blob availability was not checked.",
                                "Preserve the repository including its index and objects and independently test its restore. "
                                "A selected working-file match does not preserve staged-only work."))
    if staging["coverage"] == "not_inspected":
        findings.append(finding("staging_unchecked", "unknown",
                "Staging is NOT inspected. Staged additions, edits, deletions, and renames can be missed even when "
                "every tracked path has matching metadata. Work can exist only in the index's referenced objects.",
                "Review the staging area independently. Preserve the repository including its index and objects; "
                "matching selected working files does not preserve staged-only work. For optional loose-object comparison, "
                "review its privacy boundary and explicitly authorize --allow-git-object-read."))
    elif staging["coverage"] != "complete":
        findings.append(finding("staging_comparison_incomplete", "unknown",
                                "Staging comparison coverage is " + staging["coverage"] + ": " +
                                ", ".join(staging["reason_codes"]) + ". Change counts are lower bounds; other staged work remains unknown.",
                                "Independently review all staging and preserve index and objects; resolve every coverage gap."))
    else:
        findings.append(finding("staging_comparison_limits", "unknown",
                                "The supported index was compared with the physical HEAD tree by IDs and modes. "
                                "This does not establish blob integrity, backup inclusion, other refs, or repository recoverability.",
                                "Verify a separate repository restore including staging and the work you consider important."))
    findings.extend([
        finding("remote_state_unverified", "unknown",
                "No network access occurred. Cached refs may be stale or locally edited; remote availability and history were not checked.",
                "Independently verify access to and recovery from the intended remote or backup."),
        finding("project_recovery_unverified", "unknown",
                "This project has no verified repository restore or runnable-environment evidence. "
                "File checks, if present, cover only their explicit selections.",
                "Restore the repository separately and check history, branches, stashes, required files, and build/runtime behavior.")])
    if any(f["evidence"] in {"inferred", "observed"} for f in findings):
        result["status"] = "attention"
    return result


def session_result(item):
    with Root(item["path"]) as root:
        files, scan = root.inventory()
    return {"id": item["id"], "kind": "sessions", "status": "attention" if files else "unknown",
            "observations": {"tool": item["tool"], "regular_files": len(files),
                             "bytes_from_metadata": sum(i.st_size for i in files.values()),
                             "inventory": scan, "recoverability": "unknown"},
            "findings": [finding("sessions_not_recovery_tested", "unknown",
                                 "Only directory entries and file sizes were inspected. Transcripts, databases, "
                                 "credentials, and session contents were not opened; file counts do not establish session counts.",
                                 "Use a trusted local backup workflow, then test opening restored sessions in the relevant tool. "
                                 "Do not add transcripts or databases to content verification: they may contain secrets.")]}


def verify_selection(item):
    result = {"id": item["id"], "kind": "recovery", "status": "unknown",
              "evidence": "unknown", "selected_files": len(item["files"]), "checks": [],
              "verification_scope": "selected_file_bytes", "recoverability": "unknown",
              "limits": "Byte equality of selected files only, at check time. Does not prove off-device survival, "
                        "backup independence, permissions, history, staging, application usability, or complete recovery. "
                        "A selected-file match does not preserve staged-only work."}
    # Refuse overlapping trees even if selected files currently use different inodes.
    source_path, restored_path = absolute_scope_path(item["source"]), absolute_scope_path(item["restored"])
    if any(p.lower() in {".git", ".codex", ".claude"}
           for p in source_path.parts + restored_path.parts):
        raise ScopeError("agent_or_git_content_root_refused")
    source_key, restored_key = scope_key(source_path), scope_key(restored_path)
    if source_key == restored_key[:len(source_key)] or restored_key == source_key[:len(restored_key)]:
        raise ScopeError("overlapping_recovery_roots")
    with Root(source_path) as source, Root(restored_path) as restored:
        if fingerprint(os.fstat(source.fd))[:2] == fingerprint(os.fstat(restored.fd))[:2]:
            raise ScopeError("same_recovery_root")
        for number, value in enumerate(item["files"], 1):
            check = {"selection": number, "status": "unknown"}
            parts = relative_parts(value)
            if any(sensitive(p) or p.lower() in {".git", ".claude", ".codex"} for p in parts) or parts[-1].lower().endswith(
                    (".jsonl", ".json", ".db", ".sqlite", ".sqlite3", ".log")):
                check["reason"] = "sensitive_or_session_file_refused"
            else:
                try:
                    left_info, right_info = source.info(parts), restored.info(parts)
                    if not stat.S_ISREG(left_info.st_mode) or not stat.S_ISREG(right_info.st_mode):
                        raise ScopeError("not_regular_file")
                    if (left_info.st_dev, left_info.st_ino) == (right_info.st_dev, right_info.st_ino):
                        raise ScopeError("same_file_or_hardlink")
                    left_hash, left_after = digest_file(source, parts, expected=left_info)
                    right_hash, right_after = digest_file(restored, parts, expected=right_info)
                    if (left_after.st_dev, left_after.st_ino) == (right_after.st_dev, right_after.st_ino):
                        raise ScopeError("same_file_or_hardlink")
                    if fingerprint(source.info(parts)) != fingerprint(left_after) or fingerprint(restored.info(parts)) != fingerprint(right_after):
                        raise ScopeError("file_changed_during_check")
                    source.check_current()
                    restored.check_current()
                    check["status"] = "match" if left_hash == right_hash else "mismatch"
                    check["reason"] = "selected_bytes_equal" if left_hash == right_hash else "selected_bytes_differ"
                except FileNotFoundError:
                    check["reason"] = "selected_file_missing"
                except ScopeError as exc:
                    check["reason"] = str(exc)
                except OSError:
                    check["reason"] = "file_inaccessible_or_symlink"
            result["checks"].append(check)
    statuses = [check["status"] for check in result["checks"]]
    if "mismatch" in statuses:
        result.update(status="attention", evidence="observed")
    elif all(s == "match" for s in statuses):
        result.update(status="verified_content_match", evidence="verified")
    result["next_action"] = ("Repeat after any source or restored-copy change; independently confirm the backup survives the wipe."
                             if result["evidence"] == "verified" else
                             "Review each missing, refused, inaccessible, or differing selection and repeat the restore check.")
    return result


def assess(plan, verify=False, allow_git_object_read=False):
    results = []
    for kind, function in (("projects", project_result), ("sessions", session_result), ("recoveries", verify_selection)):
        kind_label = {"projects": "project", "sessions": "sessions", "recoveries": "recovery"}[kind]
        for item in plan[kind]:
            if kind == "recoveries" and not verify:
                results.append({"id": item["id"], "kind": "recovery", "status": "unknown", "evidence": "unknown",
                                "selected_files": len(item["files"]), "reason": "content_read_not_authorized",
                                "next_action": "Review selections for secrets, then run verify with --allow-content-read."})
                continue
            try:
                results.append(function(item, allow_git_object_read=allow_git_object_read)
                               if kind == "projects" else function(item))
            except ScopeError as exc:
                results.append({"id": item["id"], "kind": kind_label,
                                "status": "unknown", "evidence": "unknown", "reason": str(exc),
                                "next_action": "Check the explicit scope and supported formats; this item was not fully assessed."})
                if kind == "projects":
                    coverage = "unsupported" if "unsupported" in str(exc) else "incomplete"
                    staging = staging_unknown(str(exc), coverage)
                    results[-1]["observations"] = {"staging": staging, "staging_status": staging["status"],
                                                   "recoverability": "unknown"}
            except (OSError, ValueError, struct.error):
                results.append({"id": item["id"], "kind": kind_label,
                                "status": "unknown", "evidence": "unknown", "reason": "scope_inaccessible_or_invalid",
                                "next_action": "Check that the selected scope exists, is readable, and contains no symlink ancestors."})
                if kind == "projects":
                    staging = staging_unknown("scope_inaccessible_or_invalid")
                    results[-1]["observations"] = {"staging": staging, "staging_status": staging["status"],
                                                   "recoverability": "unknown"}
    summary = {"attention": 0, "unknown": 0, "verified_content_match": 0}
    for result in results:
        summary[result["status"]] += 1
    return {"schema_version": 1, "beforewipe_version": __version__,
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "readiness": "not_determined", "summary": summary, "items": results,
            "git_object_read_authorized": bool(allow_git_object_read),
            "scope": "Only explicitly declared roots and selections. No automatic discovery or network access.",
            "privacy": "Reports omit paths, filenames, branch names, remote URLs, hashes, and file contents. "
                       "Item IDs are user supplied. Treat aggregate work metadata as private.",
            "limits": ["This report is never permission to wipe a machine.",
                       "Default assessment reads Git structure and filesystem metadata, not work-file or session contents.",
                       ("Authorized Git reads follow only local loose HEAD commit/tree references, including messages and filenames. "
                        "Disguised objects may contain arbitrary bytes. Blob entries, packs, alternates, reflogs, config, and ignore rules are not followed."
                        if allow_git_object_read else
                        "Metadata cannot detect all working or staged changes. Git objects, reflogs, ignored-file rules, and config are not read."),
                       "Excluded and undeclared work remains unknown. A concurrent scan is not an atomic snapshot.",
                       "Content checks require explicit consent and non-sensitive selections; name exclusions cannot detect embedded secrets.",
                       "No backup is created, restored, uploaded, or destroyed. Off-device survival is not established."]}


def render_text(report):
    summary = report["summary"]
    lines = ["BeforeWipe — scoped evidence report", "Machine wipe readiness: NOT DETERMINED",
             "Checked: " + report["checked_at"],
             f"Attention: {summary['attention']} | Unknown: {summary['unknown']} | "
             f"Selected content matches verified: {summary['verified_content_match']}", ""]
    for item in report["items"]:
        lines.append(f"[{item['status'].upper()}] {item['id']} ({item['kind']})")
        if "reason" in item:
            lines.append("  " + item["reason"])
        observations = item.get("observations", {})
        staging = observations.get("staging")
        if staging:
            lines.append("  Staging: " + staging["status"] + " | Coverage: " + staging["coverage"])
            lines.append("  Staged change counts" + (" (lower bounds)" if staging["counts_are_lower_bounds"] else "") +
                         ": " + json.dumps(staging["changes"], sort_keys=True))
        for name, value in observations.get("counts", {}).items():
            lines.append(f"  {name}: {value if value is not None else 'unknown'}")
        if "regular_files" in observations:
            lines.append(f"  Files inventoried: {observations['regular_files']} (not a session count)")
            lines.append(f"  Bytes from metadata: {observations['bytes_from_metadata']}")
        if "inventory" in observations:
            lines.append("  Inventory gaps: " + json.dumps(observations["inventory"], sort_keys=True))
        for entry in item.get("findings", []):
            lines.extend([f"  {entry['evidence'].upper()}: {entry['detail']}", "  Next: " + entry["next_action"]])
        for check in item.get("checks", []):
            lines.append(f"  Selection {check['selection']}: {check['status']} ({check['reason']})")
        for key in ("limits", "next_action"):
            if key in item:
                lines.append("  " + item[key])
        lines.append("")
    lines.extend(["Scope: " + report["scope"], "Privacy: " + report["privacy"], "Limits:"])
    lines.extend("  - " + value for value in report["limits"])
    return "\n".join(lines)
