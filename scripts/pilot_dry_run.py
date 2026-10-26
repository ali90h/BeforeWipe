"""Synthetic-only pilot rehearsal. Never accepts existing developer data.

Run: python3 -B scripts/pilot_dry_run.py --directory /physical/path/to/NEW/tree
Creates fixtures and evidence there; refuses existing destinations. Git is used
only by this harness for fixture construction and independent local oracles.
"""
import argparse
import builtins
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import shutil
import socket
import subprocess
import sys
import time
from unittest.mock import patch

WORKSPACE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORKSPACE))
from beforewipe.__main__ import main
from beforewipe.core import render_text
from beforewipe.fs import Root, absolute_scope_path


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


def snapshot(root):
    result = {}
    for path in root.rglob("*"):
        st = path.lstat()
        result[str(path.relative_to(root))] = [st.st_mode, st.st_size, st.st_mtime_ns,
            os.readlink(path) if path.is_symlink() else
            hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None]
    return result


def rehearse(target):
    # Same no-symlink ancestor rule as the CLI; no existing tree can be supplied.
    with Root(target.parent):
        pass
    target.mkdir(mode=0o700, exist_ok=False)
    home, machine, copies, evidence = [target / n for n in ("isolated-home", "machine", "copies", "evidence")]
    for directory in (home, machine, copies, evidence):
        directory.mkdir()
    git_bin = shutil.which("git")
    require(git_bin is not None, "Git required for synthetic setup")
    env = {"PATH": os.defpath, "HOME": str(home), "XDG_CONFIG_HOME": str(home),
           "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
           "GIT_TERMINAL_PROMPT": "0", "GIT_ALLOW_PROTOCOL": "file", "GIT_OPTIONAL_LOCKS": "0",
           "LC_ALL": "C", "PYTHONDONTWRITEBYTECODE": "1"}

    def git(repo, *args, ok=True):
        command = [git_bin, "-c", "core.hooksPath=" + os.devnull, "-c", "core.fsmonitor=false",
                   "-c", "commit.gpgsign=false", "-c", "gc.auto=0", "-c", "maintenance.auto=false",
                   "-c", "user.name=Synthetic", "-c", "user.email=pilot@example.invalid", *args]
        result = subprocess.run(command, cwd=repo, env=env, capture_output=True, timeout=30)
        if ok:
            require(result.returncode == 0, "synthetic Git failed: " + repr(args) + " " + result.stderr.decode())
        return result

    def init(name):
        repo = machine / name
        repo.mkdir()
        git(repo, "init", "-b", "main")
        (repo / "src").mkdir()
        (repo / "src/app.py").write_text("print('synthetic baseline')\n")
        (repo / "notes.md").write_text("baseline notes\n")
        (repo / ".gitignore").write_text("build/\nscratch.md\n.env\n")
        git(repo, "add", ".")
        git(repo, "commit", "-m", "synthetic baseline")
        git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
        return repo

    seed = init("seed")
    # A small multi-commit source with nested trees and reused historical objects.
    (seed / "docs").mkdir()
    for revision in range(1, 7):
        (seed / ("src/module%d.py" % revision)).write_text("VALUE = %d\n" % revision)
        (seed / "docs/design.md").write_text("synthetic design revision %d\n" % revision)
        git(seed, "add", ".")
        git(seed, "commit", "-m", "synthetic history %d" % revision)
    git(seed, "update-ref", "refs/remotes/origin/main", "HEAD")
    repos = {"loose": init("loose"), "gc": init("gc"), "mixed": init("mixed"),
             "index-v4": init("index-v4"), "reflog": init("reflog")}
    for name, flags in (("clone-local", []), ("clone-copy", ["--no-hardlinks"]),
                        ("clone-transport", ["--no-local"])):
        git(machine, "clone", *flags, str(seed), str(machine / name))
        repos[name] = machine / name
    for name in ("gc", "mixed"):
        git(repos[name], "gc")
    git(repos["mixed"], "commit", "--allow-empty", "-m", "loose commit with packed tree")
    git(repos["mixed"], "update-ref", "refs/remotes/origin/main", "HEAD")

    # Reflog retains an important commit with no surviving branch or stash ref.
    r = repos["reflog"]
    git(r, "checkout", "-b", "temporary")
    (r / "draft.md").write_text("important synthetic abandoned commit\n")
    git(r, "add", "draft.md")
    git(r, "commit", "-m", "important synthetic draft")
    reflog_oid = git(r, "rev-parse", "HEAD").stdout.strip().decode()
    git(r, "checkout", "main")
    git(r, "branch", "-D", "temporary")
    # Source has a stash, separate from the staged-only version made below.
    loose = repos["loose"]
    (loose / "notes.md").write_text("important stashed design\n")
    git(loose, "stash", "push", "-m", "synthetic design")
    for name, repo in repos.items():
        if name == "reflog":
            continue
        (repo / "src/app.py").write_text("print('important version ONLY in index')\n")
        git(repo, "add", "src/app.py")
        git(repo, "restore", "--source=HEAD", "--worktree", "src/app.py")
    git(repos["index-v4"], "update-index", "--index-version", "4")
    (loose / "idea.md").write_text("important untracked design\n")
    (loose / "scratch.md").write_text("important ignored scratch work\n")
    (loose / "build").mkdir()
    (loose / "build/cache.txt").write_text("disposable generated cache\n")
    (loose / ".env").write_text("SYNTHETIC_CONFIGURATION=excluded\n")
    (loose / "notes.md").write_text("important changed notes\n")
    # One pure metadata false alarm, one branch-tip ancestry false alarm.
    noisy = init("noise")
    git(noisy, "branch", "older")
    (noisy / "notes.md").write_text("already in cached remote history\n")
    git(noisy, "add", "notes.md")
    git(noisy, "commit", "-m", "synthetic published successor")
    git(noisy, "update-ref", "refs/remotes/origin/main", "HEAD")
    st = (noisy / "notes.md").stat()
    os.utime(noisy / "notes.md", ns=(st.st_atime_ns, st.st_mtime_ns + 1000000000))
    repos["noise"] = noisy
    forgotten = init("forgotten")
    (forgotten / "forgotten.md").write_text("important work outside initial scope\n")
    (loose / "shortcut").symlink_to(forgotten, target_is_directory=True)
    sessions = machine / "sessions"
    sessions.mkdir()
    for day in (1, 2):
        (sessions / ("day%d.jsonl" % day)).write_text('{"synthetic":true}\n')
    session_copy = copies / "sessions"
    session_copy.mkdir()
    shutil.copyfile(sessions / "day1.jsonl", session_copy / "day1.jsonl")
    working_copy = copies / "working-only"
    shutil.copytree(loose, working_copy, ignore=shutil.ignore_patterns(
        ".git", ".env", "idea.md", "scratch.md", "build", "shortcut"))
    (working_copy / "notes.md").write_text("baseline notes\n")
    # Full independent repository copy; used only to demonstrate a synthetic restore.
    full_copy = copies / "repository"
    shutil.copytree(loose, full_copy, symlinks=True)

    plan = {"version": 1, "projects": [{"id": k, "path": str(v)} for k, v in repos.items()],
            "sessions": [{"id": "sessions", "path": str(sessions), "tool": "other"}],
            "recoveries": [{"id": "working-copy", "source": str(loose), "restored": str(working_copy),
                            "files": ["src/app.py"]}]}
    plan_path = target / "plan.json"
    save(plan_path, plan)
    revised = json.loads(json.dumps(plan))
    revised["recoveries"][0]["files"] += ["notes.md", "idea.md"]
    revised_path = target / "revised-plan.json"
    save(revised_path, revised)
    expanded = json.loads(json.dumps(plan))
    expanded["projects"].append({"id": "forgotten", "path": str(forgotten)})
    expanded_path = target / "expanded-plan.json"
    save(expanded_path, expanded)

    # Independent Git truth and allowed commit/tree inode set, before assessments.
    oracles, structural, objects = {}, set(), set()
    for name, repo in dict(repos, forgotten=forgotten).items():
        raw = git(repo, "diff", "--cached", "--no-renames", "--name-status", "-z").stdout.split(b"\0")
        counts = dict(added=0, modified=0, deleted=0)
        for status in raw[:-1:2]:
            counts[{b"A": "added", b"M": "modified", b"T": "modified", b"D": "deleted"}[status]] += 1
        head = git(repo, "rev-parse", "HEAD").stdout.strip().decode()
        tree = git(repo, "rev-parse", "HEAD^{tree}").stdout.strip().decode()
        tree_ids = [tree]
        for row in git(repo, "ls-tree", "-r", "-t", "HEAD").stdout.splitlines():
            fields = row.split(b"\t", 1)[0].split()
            if fields[1] == b"tree":
                tree_ids.append(fields[2].decode())
        for oid in [head] + tree_ids:
            path = repo / ".git/objects" / oid[:2] / oid[2:]
            if path.exists():
                objects.add(path)
        candidates = [repo / ".git" / n for n in ("index", "HEAD", "packed-refs")]
        candidates += list((repo / ".git/refs").rglob("*"))
        structural.update(p for p in candidates if p.is_file())
        oracles[name] = {"staged_changes": counts,
                         "working_matches_head": (repo / "src/app.py").read_bytes() == git(repo, "show", "HEAD:src/app.py").stdout,
                         "head_loose": (repo / ".git/objects" / head[:2] / head[2:]).exists(),
                         "tree_loose": (repo / ".git/objects" / tree[:2] / tree[2:]).exists(),
                         "head_links": (repo / ".git/objects" / head[:2] / head[2:]).stat().st_nlink
                            if (repo / ".git/objects" / head[:2] / head[2:]).exists() else None,
                         "count_objects": git(repo, "count-objects", "-v").stdout.decode()}
    staged_restore = copies / "recovered-index.py"
    staged_restore.write_bytes(git(full_copy, "show", ":src/app.py").stdout)
    recovered_program = subprocess.run([sys.executable, "-B", str(staged_restore)], cwd=copies,
                                       env=env, capture_output=True, timeout=5, check=True)
    require(recovered_program.stdout == b"important version ONLY in index\n", "synthetic staged restore did not run")
    recovery_oracle = {
        "restored_staged_program_output": recovered_program.stdout.decode().strip(),
        "working_bytes_equal": (loose / "src/app.py").read_bytes() == (working_copy / "src/app.py").read_bytes(),
        "staged_bytes_equal_to_working_copy": git(loose, "show", ":src/app.py").stdout == (working_copy / "src/app.py").read_bytes(),
        "working_copy_git_present": (working_copy / ".git").exists(),
        "working_copy_idea_present": (working_copy / "idea.md").exists(),
        "full_copy_staged_bytes_equal": git(loose, "show", ":src/app.py").stdout == git(full_copy, "show", ":src/app.py").stdout,
        "full_copy_refs_equal": git(loose, "show-ref").stdout == git(full_copy, "show-ref").stdout,
        "full_copy_index_equal": (loose / ".git/index").read_bytes() == (full_copy / ".git/index").read_bytes(),
        "full_copy_fsck_exit": git(full_copy, "fsck", "--strict", ok=False).returncode,
        "full_copy_stash_equal": git(loose, "show", "stash:notes.md").stdout == git(full_copy, "show", "stash:notes.md").stdout,
        "session_copy_missing_files": sorted(p.name for p in sessions.iterdir() if not (session_copy / p.name).exists()),
        "reflog_only_commit_exists": git(r, "cat-file", "-e", reflog_oid).returncode == 0,
        "reflog_only_commit_referenced": bool(git(r, "for-each-ref", "--contains=" + reflog_oid).stdout),
        "reflog_mentions_commit": reflog_oid.encode() in git(r, "reflog", "show", "--all", "--format=%H").stdout,
        "noise_working_bytes_equal_head": (noisy / "notes.md").read_bytes() == git(noisy, "show", "HEAD:notes.md").stdout,
        "noise_older_is_remote_ancestor": git(noisy, "merge-base", "--is-ancestor", "older", "refs/remotes/origin/main").returncode == 0}
    save(evidence / "oracle.json", {"projects": oracles, "recovery": recovery_oracle})
    original = {"machine": snapshot(machine), "copies": snapshot(copies)}
    approvals, runs = [], {}

    def run(label, selected_plan, flags=(), expected=1):
        # Synthetic authorization records are NOT human consent; all bytes above are authored fixtures.
        selected = json.loads(selected_plan.read_text())
        reviewed_scope = json.loads(json.dumps(selected))
        for category in ("projects", "sessions", "recoveries"):
            for item in reviewed_scope[category]:
                for field in (("source", "restored") if category == "recoveries" else ("path",)):
                    item[field] = str(Path(item[field]).relative_to(target))
        approvals.append({"run": label, "synthetic_only": True,
                          "basis": "authored non-sensitive fixture; simulated approval, not human consent",
                          "reviewed_scope_relative_to_new_tree": reviewed_scope,
                          "plan_sha256": hashlib.sha256(selected_plan.read_bytes()).hexdigest(),
                          "project_ids": [p["id"] for p in selected["projects"]],
                          "object_reads": "--allow-git-object-read" in flags,
                          "selected_file_reads": "--allow-content-read" in flags})
        argv = ["verify" if "--allow-content-read" in flags else "assess", "--plan", str(selected_plan), "--format", "json", *flags]
        started = time.monotonic()
        cli = subprocess.run([sys.executable, "-B", "-m", "beforewipe", *argv], cwd=WORKSPACE,
                             env=env, capture_output=True, timeout=30)
        require(cli.returncode == expected, label + ": unexpected CLI exit")
        report = json.loads(cli.stdout)
        (evidence / (label + ".json")).write_bytes(cli.stdout)
        text_argv = list(argv)
        text_argv[text_argv.index("--format") + 1] = "text"
        text_cli = subprocess.run([sys.executable, "-B", "-m", "beforewipe", *text_argv], cwd=WORKSPACE,
                                  env=env, capture_output=True, timeout=30)
        require(text_cli.returncode == expected, "text CLI exit differs")
        without_time = lambda text: [line for line in text.splitlines() if not line.startswith("Checked: ")]
        require(without_time(text_cli.stdout.decode()) == without_time(render_text(report)), "text and JSON evidence differ")
        (evidence / (label + ".txt")).write_bytes(text_cli.stdout)
        object_consent, content_consent = "--allow-git-object-read" in flags, "--allow-content-read" in flags
        allowed_roots = {selected_plan.parent} | {Path(p["path"]) for p in selected["projects"] + selected["sessions"]}
        if content_consent:
            allowed_roots |= {Path(p[k]) for p in selected["recoveries"] for k in ("source", "restored")}
        allowed_files = {selected_plan} | {p for p in structural if any(p.is_relative_to(Path(i["path"])) for i in selected["projects"])}
        if object_consent:
            allowed_files |= {p for p in objects if any(p.is_relative_to(Path(i["path"])) for i in selected["projects"])}
        if content_consent:
            allowed_files |= {Path(p[k]) / f for p in selected["recoveries"] for k in ("source", "restored") for f in p["files"] if (Path(p[k]) / f).is_file()}
        identities = {(p.stat().st_dev, p.stat().st_ino) for p in allowed_files}
        original_read, original_open, original_enter, original_scan = os.read, os.open, Root.__enter__, os.scandir
        reads, enumerations = set(), 0
        scan_roots = [Path(i["path"]) for i in selected["projects"] + selected["sessions"]]
        scan_ids = set()
        for root in scan_roots:
            for directory in [root] + [p for p in root.rglob("*") if p.is_dir() and not p.is_symlink()]:
                rel = directory.relative_to(root).parts
                if ".git" in rel and rel[:2] != (".git", "refs"):
                    continue
                st = directory.stat()
                scan_ids.add((st.st_dev, st.st_ino))

        def enter(root):
            require(root.path in allowed_roots, label + ": undeclared root")
            return original_enter(root)

        def read(fd, size):
            st = os.fstat(fd)
            identity = (st.st_dev, st.st_ino)
            require(identity in identities, label + ": unauthorized byte read")
            reads.add(identity)
            return original_read(fd, size)

        def readonly(path, flags, *args, **kwargs):
            require(not flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND), "assessment write")
            return original_open(path, flags, *args, **kwargs)

        def scan(fd):
            nonlocal enumerations
            st = os.fstat(fd)
            require((st.st_dev, st.st_ino) in scan_ids, label + ": unauthorized enumeration")
            enumerations += 1
            return original_scan(fd)

        def forbidden(*args, **kwargs):
            raise AssertionError("assessment used forbidden open, process or network")

        output = io.StringIO()
        with patch.object(Root, "__enter__", enter), patch("os.read", read), patch("os.open", readonly), \
             patch("os.scandir", scan), patch("subprocess.run", forbidden), patch.object(socket, "socket", forbidden), \
             patch.object(builtins, "open", forbidden), patch.object(io, "open", forbidden), contextlib.redirect_stdout(output):
            code = main(argv)
        audited = json.loads(output.getvalue())
        require(code == cli.returncode, "audited CLI exit differs")
        audited.pop("checked_at")
        comparable = dict(report)
        comparable.pop("checked_at")
        require(audited == comparable, "audited CLI differs")
        require(report["readiness"] == "not_determined", "readiness promoted")
        require(original == {"machine": snapshot(machine), "copies": snapshot(copies)}, "assessed fixtures modified")
        runs[label] = {"exit": code, "summary": report["summary"], "seconds_cli_and_audit": round(time.monotonic() - started, 3),
                       "audited_byte_read_inodes": len(reads), "audited_directory_enumerations": enumerations,
                       "scope_and_authorization_audit": "passed", "fixtures_unchanged_excluding_atime": True,
                       "items": {i["id"]: {"status": i["status"], "staging": i.get("observations", {}).get("staging"),
                                                "reason": i.get("reason"), "checks": i.get("checks")} for i in report["items"]}}
        return report

    default = run("01-default", plan_path)
    objects_report = run("02-objects-only", plan_path, ["--allow-git-object-read"])
    content = run("03-content-only", plan_path, ["--allow-content-read"])
    both = run("04-both", plan_path, ["--allow-content-read", "--allow-git-object-read"])
    followup = run("05-revised-selections", revised_path, ["--allow-content-read"])
    widened = run("06-approved-new-root", expanded_path)
    recovery_only = dict(plan, projects=[], sessions=[])
    recovery_only_path = target / "recovery-only-plan.json"
    save(recovery_only_path, recovery_only)
    run("07-recovery-only", recovery_only_path, ["--allow-content-read"], expected=0)
    items = lambda report: {i["id"]: i for i in report["items"]}
    require(items(objects_report)["working-copy"]["reason"] == "content_read_not_authorized", "objects granted file access")
    require(items(content)["loose"]["observations"]["staging"]["coverage"] == "not_inspected", "content granted object access")
    require(items(both)["working-copy"]["status"] == "verified_content_match", "selected byte match missing")
    require(items(both)["loose"]["observations"]["staging"]["changes"] == oracles["loose"]["staged_changes"], "loose oracle differs")
    for name in ("clone-local", "clone-transport", "gc", "mixed"):
        require(items(both)[name]["observations"]["staging"]["coverage"] != "complete", "expected object gap missing")
    require(items(both)["clone-copy"]["observations"]["staging"]["status"] == "confirmed_risk", "loose copied clone failed")
    require(items(both)["index-v4"]["observations"]["staging"]["coverage"] == "unsupported", "unsupported gap missing")
    require(items(both)["reflog"]["observations"]["staging"]["status"] == "no_difference_observed", "reflog fixture invalid")
    require([c["status"] for c in items(followup)["working-copy"]["checks"]] == ["match", "mismatch", "unknown"], "selection gaps missing")
    require(items(default)["noise"]["observations"]["counts"]["metadata_changed"] == 1, "metadata-only noise fixture refreshed")
    require("forgotten" not in items(default) and "forgotten" in items(widened), "scope silently expanded")
    # A plan cannot grant an optional capability, and verify needs its flag.
    injected = dict(plan, allow_git_object_read=True)
    injection_path = target / "injected-plan.json"
    save(injection_path, injected)
    rejected = subprocess.run([sys.executable, "-B", "-m", "beforewipe", "assess", "--plan", str(injection_path)],
                              cwd=WORKSPACE, env=env, capture_output=True, timeout=30)
    unconsented = subprocess.run([sys.executable, "-B", "-m", "beforewipe", "verify", "--plan", str(plan_path)],
                                cwd=WORKSPACE, env=env, capture_output=True, timeout=30)
    require(rejected.returncode == unconsented.returncode == 2, "authorization refusal failed")
    save(evidence / "approvals.json", approvals)
    save(evidence / "results.json", {"synthetic_only": True, "human_participants": 0,
        "environment": {"platform": platform.platform(), "python": platform.python_version(), "git": git(machine, "--version").stdout.decode().strip()},
        "runs": runs, "authorization_refusals": {"plan_injection_exit": rejected.returncode, "verify_without_consent_exit": unconsented.returncode},
        "source_sha256": {str(p.relative_to(WORKSPACE)): hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in list((WORKSPACE / "beforewipe").glob("*.py")) + [Path(__file__)]}})
    print("Synthetic pilot completed; evidence: " + str(evidence))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", required=True, help="NEW physical path; existing destinations refused")
    args = parser.parse_args()
    rehearse(absolute_scope_path(args.directory))
