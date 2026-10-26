"""Create ONLY new synthetic fixtures; assessment itself never invokes Git."""

import json
import os
import shutil
import subprocess

from .fs import Root, ScopeError, absolute_scope_path


def create_demo(directory):
    target = absolute_scope_path(directory)
    # Validate ancestors without following links and refuse existing destinations.
    with Root(target.parent):
        pass
    git = shutil.which("git")
    if git is None:
        raise ScopeError("demo_requires_git")
    target.mkdir(mode=0o700, exist_ok=False)
    project, restored = target / "project", target / "restored"
    project.mkdir()
    restored.mkdir()
    # An isolated HOME prevents global Git config, credentials, and hooks being read.
    isolated_home = target / "isolated-git-home"
    isolated_home.mkdir()
    env = {"PATH": os.defpath, "HOME": str(isolated_home), "XDG_CONFIG_HOME": str(isolated_home),
           "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
           "GIT_TERMINAL_PROMPT": "0", "LC_ALL": "C"}

    def run(*args):
        try:
            process = subprocess.run([git, "-c", "core.hooksPath=" + os.devnull,
                                      "-c", "core.fsmonitor=false", *args], cwd=project,
                                     env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                     timeout=15, check=False)
        except subprocess.TimeoutExpired:
            raise ScopeError("synthetic_git_setup_timed_out") from None
        if process.returncode:
            raise ScopeError("synthetic_git_setup_failed")

    (project / "src").mkdir()
    (restored / "src").mkdir()
    (project / "src" / "app.py").write_text("print('synthetic recovered work')\n")
    (project / "notes.md").write_text("Synthetic design notes, version one.\n")
    (project / ".gitignore").write_text(".env\nscratch.txt\n")
    run("init", "-b", "main")
    run("-c", "user.name=Synthetic Developer", "-c", "user.email=fixture@example.invalid",
        "add", "src/app.py", "notes.md", ".gitignore")
    run("-c", "user.name=Synthetic Developer", "-c", "user.email=fixture@example.invalid",
        "commit", "-m", "Synthetic initial work")
    run("update-ref", "refs/remotes/origin/main", "HEAD")
    (project / "notes.md").write_text("Synthetic design notes, version two; local edit.\n")
    (project / "untracked.md").write_text("An overlooked synthetic idea.\n")
    (project / "scratch.txt").write_text("Ignored synthetic work.\n")
    (project / ".env").write_text("SYNTHETIC_SECRET=never-open-this-fixture\n")
    shutil.copyfile(project / "src" / "app.py", restored / "src" / "app.py")
    (restored / "notes.md").write_text("Synthetic design notes, version one.\n")
    sessions = target / "sessions"
    sessions.mkdir()
    (sessions / "session.jsonl").write_text('{"synthetic":true,"text":"not opened by assessment"}\n')
    plan = {"version": 1, "projects": [{"id": "demo-project", "path": "project"}],
            "sessions": [{"id": "demo-sessions", "path": "sessions", "tool": "codex"}],
            "recoveries": [{"id": "recovered-code", "source": "project", "restored": "restored", "files": ["src/app.py"]},
                           {"id": "stale-notes", "source": "project", "restored": "restored", "files": ["notes.md"]},
                           {"id": "missing-idea", "source": "project", "restored": "restored", "files": ["untracked.md"]}]}
    (target / "plan.json").write_text(json.dumps(plan, indent=2) + "\n")
    return target / "plan.json"
