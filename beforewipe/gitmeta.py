"""Conservative Git metadata inspection without Git subprocesses.

Supports ordinary SHA-1 repositories with a complete v2/v3 index. Other layouts
are unknown rather than silently delegated to Git (which can read credentials,
work-file contents, include paths, helpers, and external object stores).
Optional commit/tree object comparison requires separate informed authorization.
"""

import hashlib
import re
import stat
import struct

from .fs import Root, ScopeError, relative_parts, sensitive
from .staging import compare_staging, staging_unknown

OID = re.compile(rb"[0-9a-f]{40}")
MAX_METADATA = 16 * 1024 * 1024


def parse_index(data):
    if len(data) < 32 or data[:4] != b"DIRC":
        raise ScopeError("invalid_git_index")
    version, count = struct.unpack_from(">II", data, 4)
    if version not in (2, 3):
        raise ScopeError("unsupported_git_index_version")
    if count > 100000:
        raise ScopeError("index_entry_limit_exceeded")
    if hashlib.sha1(data[:-20]).digest() != data[-20:]:
        raise ScopeError("invalid_git_index_checksum")
    entries, pos, end = [], 12, len(data) - 20
    previous = None
    path_stages = {}
    for _ in range(count):
        start = pos
        if pos + 62 > end:
            raise ScopeError("truncated_git_index")
        fields = struct.unpack_from(">10I20sH", data, pos)
        flags, extended = fields[-1], 0
        pos += 62
        if flags & 0x4000:
            if version != 3 or pos + 2 > end:
                raise ScopeError("invalid_git_index_flags")
            extended = struct.unpack_from(">H", data, pos)[0]
            pos += 2
        stop = data.find(b"\0", pos, end)
        if stop < 0:
            raise ScopeError("truncated_git_index")
        raw = data[pos:stop]
        if not raw:
            raise ScopeError("unsupported_split_index")
        if fields[6] == 0o40000:
            raise ScopeError("unsupported_sparse_index")
        if len(raw) > 65536 or raw.count(b"/") > 256:
            raise ScopeError("git_index_path_limit")
        try:
            parts = relative_parts(raw.decode("utf-8", "surrogateescape"))
        except ScopeError:
            raise ScopeError("invalid_git_index_path") from None
        if any(p.lower() == ".git" for p in parts):
            raise ScopeError("invalid_git_index_path")
        stage = (flags >> 12) & 3
        if previous is not None and (raw, stage) <= previous:
            raise ScopeError("invalid_git_index_order")
        previous = (raw, stage)
        stages = path_stages.setdefault(parts, set())
        if (stage == 0 and stages) or (stage and 0 in stages):
            raise ScopeError("invalid_git_index_stages")
        stages.add(stage)
        if fields[6] not in (0o100644, 0o100755, 0o120000, 0o160000):
            raise ScopeError("unsupported_git_index_mode")
        if not any(fields[10]):
            raise ScopeError("invalid_git_index_object_id")
        if extended & ~0x6000:
            raise ScopeError("unsupported_git_index_flags")
        if flags & 0xfff != min(len(raw), 0xfff):
            raise ScopeError("invalid_git_index_path_length")
        pos = start + ((stop + 1 - start + 7) // 8) * 8
        if pos > end or any(data[stop:pos]):
            raise ScopeError("invalid_git_index_padding")
        entries.append({"parts": parts, "ctime_ns": fields[0] * 10**9 + fields[1],
                        "mtime_ns": fields[2] * 10**9 + fields[3], "mode": fields[6],
                        "size": fields[9], "stage": stage, "oid": fields[10],
                        "intent_to_add": bool(extended & 0x2000),
                        "special_flags": bool(flags & 0x8000 or extended)})
    for parts in path_stages:
        if any(parts[:i] in path_stages for i in range(1, len(parts))):
            raise ScopeError("invalid_git_index_path_collision")
    while pos < end:
        if pos + 8 > end:
            raise ScopeError("invalid_git_index_extension")
        signature, length = struct.unpack_from(">4sI", data, pos)
        pos += 8
        if not 65 <= signature[0] <= 90:
            raise ScopeError("unsupported_git_index_extension")
        pos += length
        if pos > end:
            raise ScopeError("truncated_git_index_extension")
    return entries


def refs(root):
    values = {}
    try:
        data = root.metadata((".git", "packed-refs"), MAX_METADATA)
    except FileNotFoundError:
        data = b""
    for line in data.splitlines():
        if line.startswith(b"#") or not line:
            continue
        if line.startswith(b"^"):
            if not values or not OID.fullmatch(line[1:]):
                raise ScopeError("unsupported_or_invalid_git_refs")
            continue
        parts = line.split(b" ", 1)
        if len(parts) != 2 or not OID.fullmatch(parts[0]):
            raise ScopeError("unsupported_or_invalid_git_refs")
        name = parts[1].decode("utf-8", "surrogateescape")
        relative_parts(name)
        if name in values:
            raise ScopeError("unsupported_or_invalid_git_refs")
        values[name] = parts[0]
    try:
        files, scan = root.inventory((".git", "refs"), skip_git=False)
    except FileNotFoundError:
        files, scan = {}, {}
    if scan.get("limited") or any(scan.get(k) for k in ("errors", "symlinks", "excluded", "special")):
        raise ScopeError("incomplete_git_refs")
    for parts in files:
        value = root.metadata(parts, 256).strip()
        name = "/".join(parts[1:])
        if value.startswith(b"ref: "):
            # Loose refs override packed refs even when symbolic. Skipping one
            # can silently resurrect a stale packed tip as the HEAD baseline.
            if name.startswith("refs/remotes/"):
                # Remote aliases never supply our physical HEAD baseline and
                # are not independent cached tips. Remove a shadowed tip too.
                values.pop(name, None)
                continue
            raise ScopeError("symbolic_git_refs_unsupported")
        if not OID.fullmatch(value):
            raise ScopeError("unsupported_or_invalid_git_refs")
        values[name] = value
    return values


def assess_project(path, allow_git_object_read=False):
    with Root(path) as root:
        try:
            info = root.info((".git",))
        except FileNotFoundError:
            raise ScopeError("not_a_git_root") from None
        if not stat.S_ISDIR(info.st_mode):
            raise ScopeError("linked_worktree_or_gitfile_unsupported")
        head = root.metadata((".git", "HEAD"), 4096).strip()
        if not (OID.fullmatch(head) or head.startswith(b"ref: refs/heads/")):
            raise ScopeError("unsupported_or_invalid_git_head")
        if head.startswith(b"ref: "):
            relative_parts(head[5:].decode("utf-8", "surrogateescape"))
        try:
            index_data = root.metadata((".git", "index"), MAX_METADATA)
            entries = parse_index(index_data)
            index_present = True
        except FileNotFoundError:
            entries, index_present = [], False
        coverage_errors = []
        try:
            values = refs(root)
        except ScopeError as exc:
            values = None
            coverage_errors.append({"component": "refs", "reason": str(exc)})
        except (OSError, ValueError):
            values = None
            coverage_errors.append({"component": "refs", "reason": "git_refs_inaccessible"})
        files, scan = root.inventory(known_git_root=True)
        tracked = {entry["parts"] for entry in entries}
        counts = {"tracked_paths": len(tracked), "metadata_changed": 0,
                  "tracked_missing": 0, "metadata_matches": 0,
                  "unmerged_entries": 0, "submodules": 0, "unchecked_entries": 0,
                  "files_outside_index": sum(p not in tracked for p in files),
                  "local_branches": None,
                  "branch_tips_absent_from_cached_remotes": None,
                  "stash_ref_present": None}
        if values is not None:
            counts["local_branches"] = sum(n.startswith("refs/heads/") for n in values)
            counts["stash_ref_present"] = int("refs/stash" in values)
            remote_tips = {v for n, v in values.items() if n.startswith("refs/remotes/")}
            counts["branch_tips_absent_from_cached_remotes"] = sum(
                v not in remote_tips for n, v in values.items() if n.startswith("refs/heads/"))
        for entry in entries:
            parts = entry["parts"]
            if entry["stage"]:
                counts["unmerged_entries"] += 1
            elif entry["mode"] == 0o160000:
                counts["submodules"] += 1
            elif (entry["special_flags"] or entry["mode"] not in (0o100644, 0o100755)
                  or any(sensitive(p) or p.lower() in {".codex", ".claude"} for p in parts)):
                counts["unchecked_entries"] += 1
            else:
                try:
                    info = root.info(parts)
                    if not stat.S_ISREG(info.st_mode):
                        counts["unchecked_entries"] += 1
                    elif (info.st_size != entry["size"]
                          or info.st_mtime_ns != entry["mtime_ns"]
                          or info.st_ctime_ns != entry["ctime_ns"]
                          or bool(info.st_mode & 0o111) != bool(entry["mode"] & 0o111)):
                        counts["metadata_changed"] += 1
                    else:
                        counts["metadata_matches"] += 1
                except FileNotFoundError:
                    counts["tracked_missing"] += 1
                except OSError:
                    counts["unchecked_entries"] += 1
        staging = staging_unknown("git_object_read_not_authorized", "not_inspected")
        if allow_git_object_read:
            if not index_present:
                staging = staging_unknown("index_absent")
            elif values is None:
                staging = staging_unknown("git_refs_incomplete")
            elif any(n.startswith("refs/replace/") for n in values):
                staging = staging_unknown("git_replace_refs_unsupported", "unsupported")
            else:
                head_oid = head if OID.fullmatch(head) else values.get(head[5:].decode("utf-8", "surrogateescape"))
                if head_oid is None:
                    staging = staging_unknown("unborn_or_missing_head_unsupported", "unsupported")
                else:
                    staging = compare_staging(root, entries, bytes.fromhex(head_oid.decode("ascii")))
                    # Reject a mixed index/HEAD observation. Per-file object checks
                    # validate hashes and identity; this still is not a snapshot.
                    try:
                        if (root.metadata((".git", "index"), MAX_METADATA) != index_data
                                or root.metadata((".git", "HEAD"), 4096).strip() != head
                                or refs(root) != values):
                            raise ScopeError("git_state_changed_during_staging_check")
                        root.check_current()
                    except ScopeError as exc:
                        staging = staging_unknown(str(exc))
                    except (OSError, ValueError):
                        staging = staging_unknown("git_state_inaccessible_after_staging_check")
        return {"counts": counts, "inventory": scan, "index_present": index_present,
                "coverage_errors": coverage_errors,
                "detached_head": bool(OID.fullmatch(head)),
                "staging_status": staging["status"], "staging": staging,
                "recoverability": "unknown"}
