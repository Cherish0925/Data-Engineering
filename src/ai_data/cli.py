"""Command-line and machine-readable entry points."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .contracts import record_schema
from .pipeline import build, inspect_release, profile, verify_release


def main(argv=None) -> int:
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(prog="ai-data", description="Build versioned AI data products.")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("profile", "inspect", "verify"):
        command = commands.add_parser(name)
        command.add_argument("path")
    builder = commands.add_parser("build")
    builder.add_argument("recipe")
    builder.add_argument("--output", required=True)
    builder.add_argument("--root", help="source workspace; defaults to recipe directory")
    builder.add_argument("--allow-plugins", action="store_true", help="load trusted installed connector code")
    commands.add_parser("schema")
    server = commands.add_parser("serve")
    server.add_argument("--root", required=True)
    config = commands.add_parser("connect")
    config.add_argument("--root", required=True)
    config.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "build":
            result = build(args.recipe, args.output, root=args.root, allow_plugins=args.allow_plugins)
        elif args.command == "profile":
            result = profile(args.path)
        elif args.command == "inspect":
            result = inspect_release(args.path)
        elif args.command == "verify":
            result = verify_release(args.path)
        elif args.command == "schema":
            result = record_schema()
        elif args.command == "connect":
            root = Path(args.root).resolve(strict=True)
            if not root.is_dir():
                raise ValueError("root must be a directory")
            result = {"mcpServers": {"data-engineering": {
                "command": sys.executable,
                "args": ["-m", "ai_data", "serve", "--root", str(root)],
            }}}
            with Path(args.output).open("x", encoding="utf-8", newline="\n") as stream:
                json.dump(result, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
        else:
            from .mcp_server import create_server
            create_server(args.root).run(transport="stdio")
            return 0
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        return 0
    except (ValueError, OSError, ImportError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
