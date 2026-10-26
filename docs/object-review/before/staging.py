"""Opt-in index/physical-HEAD comparison; never execute Git or open blob paths.

Only local loose commit/tree objects are supported. These bytes cross the default
metadata boundary: commit messages and tree names can be private. Callers must
obtain explicit informed authorization; filenames/types cannot prove provenance.
"""

import hashlib
import re
import zlib

from .fs import ScopeError, relative_parts

MAX_OBJECT_BYTES = 8 * 1024 * 1024
MAX_TOTAL_BYTES = 32 * 1024 * 1024
MAX_OBJECTS = 4096
MAX_TREE_ENTRIES = 100000
MAX_TREE_DEPTH = 32


def staging_unknown(reason, coverage="incomplete"):
    return {"status": "unsupported" if coverage == "unsupported" else "unknown",
            "coverage": coverage, "reason_codes": [reason],
            "comparison": "index_vs_physical_head_tree_ids_and_modes",
            "changes": {"added": 0, "modified": 0, "deleted": 0},
            "counts_are_lower_bounds": True, "paths_compared": 0}


class LooseObjects:
    def __init__(self, root):
        self.root = root
        self.objects = self.total = self.compressed_total = self.entries = 0

    def read(self, oid, expected):
        # OIDs originate in validated binary structures, never filesystem paths.
        if len(oid) != 20 or not any(oid):
            raise ScopeError("invalid_git_object_id")
        self.objects += 1
        if self.objects > MAX_OBJECTS:
            raise ScopeError("git_object_count_limit")
        name = oid.hex()
        compressed_limit = min(MAX_OBJECT_BYTES, MAX_TOTAL_BYTES - self.compressed_total)
        if compressed_limit <= 0:
            raise ScopeError("git_object_byte_limit")
        try:
            compressed = self.root.metadata((".git", "objects", name[:2], name[2:]), compressed_limit)
        except FileNotFoundError:
            raise ScopeError("loose_object_missing_packed_or_external_unsupported") from None
        self.compressed_total += len(compressed)
        limit = min(MAX_OBJECT_BYTES, MAX_TOTAL_BYTES - self.total)
        if limit <= 0:
            raise ScopeError("git_object_byte_limit")
        try:
            inflater = zlib.decompressobj()
            raw = inflater.decompress(compressed, limit + 1)
        except zlib.error:
            raise ScopeError("invalid_git_object_compression") from None
        self.total += len(raw)
        if len(raw) > limit:
            raise ScopeError("git_object_byte_limit")
        if not inflater.eof or inflater.unused_data or inflater.unconsumed_tail:
            raise ScopeError("invalid_git_object_compression")
        header, sep, body = raw.partition(b"\0")
        if not sep or header != expected + b" " + str(len(body)).encode("ascii"):
            raise ScopeError("invalid_git_object_type_or_size")
        if hashlib.sha1(raw).digest() != oid:
            raise ScopeError("invalid_git_object_checksum")
        return body

    def tree(self, oid):
        data = self.read(oid, b"tree")
        entries, seen, pos, previous = [], set(), 0, None
        while pos < len(data):
            stop = data.find(b"\0", pos)
            if stop < 0 or stop + 21 > len(data):
                raise ScopeError("invalid_git_tree")
            mode, sep, raw = data[pos:stop].partition(b" ")
            if not sep or mode not in (b"40000", b"100644", b"100755", b"120000", b"160000"):
                raise ScopeError("unsupported_git_tree_mode")
            try:
                parts = relative_parts(raw.decode("utf-8", "surrogateescape"))
            except ScopeError:
                raise ScopeError("invalid_git_tree_path") from None
            if len(parts) != 1 or parts[0].lower() == ".git" or raw in seen:
                raise ScopeError("invalid_git_tree_path")
            key = raw + (b"/" if mode == b"40000" else b"\0")
            if previous is not None and key <= previous:
                raise ScopeError("invalid_git_tree_order")
            seen.add(raw)
            previous = key
            child_oid = data[stop + 1:stop + 21]
            if not any(child_oid):
                raise ScopeError("invalid_git_object_id")
            entries.append((parts[0], int(mode, 8), child_oid))
            pos = stop + 21
            self.entries += 1
            if self.entries > MAX_TREE_ENTRIES:
                raise ScopeError("git_tree_entry_limit")
        return entries


def compare_staging(root, entries, head_oid):
    """Counts are lower bounds when a subtree or index entry cannot be compared.

    Rename pairing requires no extra evidence for risk: report its deletion and
    addition, without claiming rename identity. Blob existence/content is unknown.
    """
    reader = LooseObjects(root)
    try:
        commit = reader.read(head_oid, b"commit")
        headers, separator, _ = commit.partition(b"\n\n")
        lines = headers.split(b"\n")
        first = lines[0]
        if (not separator or b"\0" in commit
                or not re.fullmatch(rb"tree [0-9a-f]{40}", first)
                or sum(line.startswith(b"author ") for line in lines) != 1
                or sum(line.startswith(b"committer ") for line in lines) != 1
                or any(line.startswith(b"tree ") for line in lines[1:])
                or any(line.startswith(b"parent ") and not re.fullmatch(rb"parent [0-9a-f]{40}", line)
                       for line in lines[1:])):
            raise ScopeError("invalid_git_commit_tree")
        try:
            tree_oid = bytes.fromhex(first[5:].decode("ascii"))
        except (ValueError, UnicodeError):
            raise ScopeError("invalid_git_commit_tree") from None
        if len(tree_oid) != 20:
            raise ScopeError("invalid_git_commit_tree")
    except ScopeError as exc:
        return staging_unknown(str(exc))
    except OSError:
        return staging_unknown("git_object_inaccessible_or_symlink")

    baseline, unknown_prefixes, reasons = {}, set(), set()
    stack = [((), tree_oid)]
    while stack:
        prefix, oid = stack.pop()
        try:
            if len(prefix) > MAX_TREE_DEPTH:
                raise ScopeError("git_tree_depth_limit")
            children = reader.tree(oid)
        except ScopeError as exc:
            unknown_prefixes.add(prefix)
            reasons.add(str(exc))
            continue
        except OSError:
            unknown_prefixes.add(prefix)
            reasons.add("git_object_inaccessible_or_symlink")
            continue
        for name, mode, child_oid in children:
            path = prefix + (name,)
            if mode == 0o40000:
                stack.append((path, child_oid))
            else:
                baseline[path] = (mode, child_oid)

    staged, unchecked = {}, set()
    for entry in entries:
        path = entry["parts"]
        if entry["stage"] or entry["intent_to_add"]:
            unchecked.add(path)
            reasons.add("unmerged_or_intent_to_add_index_entries")
        else:
            staged[path] = (entry["mode"], entry["oid"])
    changes = {"added": 0, "modified": 0, "deleted": 0}
    compared = 0
    for path in baseline.keys() | staged.keys():
        if path in unchecked or any(path[:i] in unknown_prefixes for i in range(len(path) + 1)):
            continue
        before, after = baseline.get(path), staged.get(path)
        compared += 1
        if before != after:
            changes["added" if before is None else "deleted" if after is None else "modified"] += 1
    complete = not reasons
    return {"status": "confirmed_risk" if any(changes.values()) else "no_difference_observed" if complete else "unknown",
            "coverage": "complete" if complete else "incomplete", "reason_codes": sorted(reasons),
            "comparison": "index_vs_physical_head_tree_ids_and_modes",
            "changes": changes, "counts_are_lower_bounds": not complete, "paths_compared": compared}
