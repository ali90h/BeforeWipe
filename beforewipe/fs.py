"""Bounded filesystem access. No symlink traversal, including path ancestors."""

import hashlib
import os
import stat
import unicodedata
from pathlib import Path

MAX_ENTRIES = 20000
MAX_DEPTH = 32
MAX_FILE_BYTES = 32 * 1024 * 1024


class ScopeError(Exception):
    """A safe, content-free reason that access could not be completed."""


def sensitive(name):
    name = name.lower()
    return (
        name.startswith(".env")
        or name in {".ssh", ".aws", ".azure", ".gnupg", ".kube", ".config",
                    ".npmrc", ".pypirc", ".netrc", ".git-credentials",
                    ".gitconfig", "auth.json", "credentials.json", "config.json",
                    "id_rsa", "id_ed25519", "keychain", ".ds_store"}
        or any(word in name for word in ("secret", "credential", "password", "token"))
        or name.endswith((".pem", ".key", ".p12", ".pfx", ".kdbx"))
    )


def relative_parts(value):
    if not isinstance(value, str) or not value or "\x00" in value or "\\" in value:
        raise ScopeError("invalid_relative_path")
    parts = value.split("/")
    if any(p in {"", ".", ".."} for p in parts) or value.startswith("/"):
        raise ScopeError("invalid_relative_path")
    return tuple(parts)


def absolute_scope_path(value):
    # Do not erase a symlink/.. component before no-follow traversal can see it.
    if ".." in Path(value).parts:
        raise ScopeError("ambiguous_scope_path")
    # POSIX abspath preserves exactly two leading slashes. Our descriptor walk
    # starts at '/', so normalize that spelling before applying scope guards.
    return Path("/" + os.path.abspath(value).lstrip("/"))


def scope_key(path):
    # Conservatively reject aliases on case/normalization-insensitive filesystems.
    # This can over-refuse distinct case-sensitive roots, which is safer here.
    return tuple(unicodedata.normalize("NFC", p).casefold() for p in path.parts)


class Root:
    """Open directories using descriptors so a substituted symlink cannot escape."""

    def __init__(self, path):
        self.path = absolute_scope_path(path)
        if self.path == Path("/") or scope_key(self.path) == scope_key(absolute_scope_path(Path.home())):
            raise ScopeError("scope_too_broad")
        if any(sensitive(p) for p in self.path.parts[1:]):
            raise ScopeError("sensitive_scope_refused")
        self.fd = None

    def __enter__(self):
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        fd = os.open("/", flags)
        try:
            for component in self.path.parts[1:]:
                next_fd = os.open(component, flags, dir_fd=fd)
                os.close(fd)
                fd = next_fd
            self.fd = fd
            return self
        except BaseException:
            os.close(fd)
            raise

    def __exit__(self, *args):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None

    def directory(self, parts=()):
        fd = os.dup(self.fd)
        try:
            for part in parts:
                next_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                  dir_fd=fd)
                os.close(fd)
                fd = next_fd
            return fd
        except BaseException:
            os.close(fd)
            raise

    def info(self, parts):
        fd = self.directory(parts[:-1])
        try:
            return os.stat(parts[-1], dir_fd=fd, follow_symlinks=False)
        finally:
            os.close(fd)

    def check_current(self):
        """Detect a declared root renamed/replaced while its descriptor was held."""
        with Root(self.path) as current:
            if fingerprint(os.fstat(self.fd))[:2] != fingerprint(os.fstat(current.fd))[:2]:
                raise ScopeError("root_replaced_during_check")

    def open_file(self, parts, expected=None, single_link=False):
        before = self.info(parts)
        if not stat.S_ISREG(before.st_mode):
            raise ScopeError("not_regular_file")
        if expected is not None and fingerprint(before) != fingerprint(expected):
            raise ScopeError("file_replaced_before_read")
        if single_link and before.st_nlink != 1:
            raise ScopeError("hardlinked_metadata_refused")
        fd = self.directory(parts[:-1])
        try:
            # NONBLOCK prevents a FIFO substituted during the open from hanging.
            result = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                             dir_fd=fd)
        finally:
            os.close(fd)
        try:
            opened = os.fstat(result)
            if not stat.S_ISREG(opened.st_mode):
                raise ScopeError("not_regular_file")
            if single_link and opened.st_nlink != 1:
                raise ScopeError("hardlinked_metadata_refused")
            if fingerprint(opened) != fingerprint(before):
                raise ScopeError("file_replaced_before_read")
        except BaseException:
            os.close(result)
            raise
        return result

    def metadata(self, parts, limit):
        # Only the user-selected plan and known Git structure, never config/logs.
        fd = self.open_file(parts, single_link=True)
        try:
            before = os.fstat(fd)
            if before.st_size > limit:
                raise ScopeError("metadata_limit_exceeded")
            data = bytearray()
            while len(data) <= limit:
                chunk = os.read(fd, min(65536, limit + 1 - len(data)))
                if not chunk:
                    break
                data.extend(chunk)
            if len(data) > limit:
                raise ScopeError("metadata_limit_exceeded")
            after = os.fstat(fd)
            if (fingerprint(before) != fingerprint(after) or len(data) != after.st_size
                    or after.st_nlink != 1 or fingerprint(self.info(parts)) != fingerprint(after)):
                raise ScopeError("metadata_changed_during_check")
            return bytes(data)
        finally:
            os.close(fd)

    def inventory(self, start=(), skip_git=True, known_git_root=False):
        files, stats = {}, {"excluded": 0, "symlinks": 0, "errors": 0,
                            "special": 0, "limited": False, "git_entries_skipped": 0}
        stack, visited = [(start, 0)], 0
        while stack:
            parts, depth = stack.pop()
            try:
                fd = self.directory(parts)
            except OSError:
                stats["errors"] += 1
                continue
            try:
                with os.scandir(fd) as entries:
                    for entry in entries:
                        visited += 1
                        if visited > MAX_ENTRIES:
                            stats["limited"] = True
                            return files, stats
                        name = entry.name
                        if name.lower() == ".git" and skip_git:
                            if parts or not known_git_root:
                                stats["git_entries_skipped"] += 1
                            continue
                        if sensitive(name) or name.lower() in {".codex", ".claude"}:
                            stats["excluded"] += 1
                            continue
                        child = parts + (name,)
                        try:
                            info = entry.stat(follow_symlinks=False)
                            if stat.S_ISLNK(info.st_mode):
                                stats["symlinks"] += 1
                            elif stat.S_ISDIR(info.st_mode):
                                if depth >= MAX_DEPTH:
                                    stats["limited"] = True
                                else:
                                    stack.append((child, depth + 1))
                            elif stat.S_ISREG(info.st_mode):
                                files[child] = info
                            else:
                                stats["special"] += 1
                        except OSError:
                            stats["errors"] += 1
            except OSError:
                stats["errors"] += 1
            finally:
                os.close(fd)
        return files, stats


def fingerprint(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def digest_file(root, parts, expected=None):
    fd = root.open_file(parts, expected=expected)
    try:
        before = os.fstat(fd)
        if before.st_size > MAX_FILE_BYTES:
            raise ScopeError("file_size_limit_exceeded")
        digest, total = hashlib.sha256(), 0
        while True:
            chunk = os.read(fd, 65536)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_FILE_BYTES:
                raise ScopeError("file_size_limit_exceeded")
            digest.update(chunk)
        after = os.fstat(fd)
        if fingerprint(before) != fingerprint(after) or total != after.st_size:
            raise ScopeError("file_changed_during_check")
        if fingerprint(root.info(parts)) != fingerprint(after):
            raise ScopeError("file_replaced_during_check")
        return digest.digest(), after
    finally:
        os.close(fd)
