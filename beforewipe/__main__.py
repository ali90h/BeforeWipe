import argparse
import json
import os
import sys

from . import __version__
from .core import assess, load_plan, render_text
from .fs import ScopeError


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="beforewipe", description="Local pre-wipe evidence for explicitly selected work. Never a wipe approval.")
    parser.add_argument("--version", action="version", version="BeforeWipe " + __version__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("assess", "verify"):
        command = commands.add_parser(name, help="Read-only metadata assessment" if name == "assess" else "Also compare explicitly selected non-sensitive file bytes")
        command.add_argument("--plan", required=True, help="User-reviewed JSON scope plan; relative roots are relative to this file")
        command.add_argument("--format", choices=("text", "json"), default="text")
        command.add_argument("--allow-git-object-read", action="store_true",
                             help="Authorize local loose HEAD commit/tree object reads for ALL declared projects. "
                             "Confirm repositories are reviewed and non-sensitive: reads include commit messages and tree filenames; "
                             "malformed/disguised objects may contain ANY bytes, including secrets. "
                             "Does not follow blob entries, packs, config, external stores, or Git subprocesses.")
        if name == "verify":
            command.add_argument("--allow-content-read", action="store_true", required=True,
                                 help="Confirm ALL selected file contents are non-sensitive and authorize reading both copies; name filters cannot detect embedded secrets")
    demo = commands.add_parser("demo", help="Write synthetic fixtures into a NEW directory (requires Git)")
    demo.add_argument("--directory", required=True)
    args = parser.parse_args(argv)
    if os.name != "posix":
        parser.error("this version requires a POSIX filesystem API (macOS/Linux)")
    try:
        if args.command == "demo":
            from .demo import create_demo
            create_demo(args.directory)
            print("Synthetic fixtures created. Review plan.json in the selected directory.\n"
                  "Run assess --plan <directory>/plan.json, then verify with --allow-content-read.\n"
                  "Assessment and verification exit 1 when attention or unknowns remain.")
            return 0
        plan = load_plan(args.plan)
        report = assess(plan, verify=args.command == "verify", allow_git_object_read=args.allow_git_object_read)
        print(json.dumps(report, indent=2, ensure_ascii=True) if args.format == "json" else render_text(report))
        return 1 if report["summary"]["attention"] or report["summary"]["unknown"] else 0
    except ScopeError as exc:
        print("BeforeWipe: " + str(exc) + ". No assessment conclusion was produced.", file=sys.stderr)
    except FileExistsError:
        print("BeforeWipe: demo destination must not already exist; nothing was overwritten.", file=sys.stderr)
    except (OSError, ValueError):
        # Never print exception text: it can contain paths or other private data.
        print("BeforeWipe: input inaccessible or invalid. No assessment conclusion was produced.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
