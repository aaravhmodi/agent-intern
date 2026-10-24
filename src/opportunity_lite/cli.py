"""Start the local app, or refresh listings from a scheduled job."""

import argparse
from pathlib import Path

from opportunity_lite.dashboard import serve
from opportunity_lite.workspace import Workspace, load_env, refresh


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="intern-agent", description="Open the Intern Agent app in your browser."
    )
    parser.add_argument("--dir", type=Path, default=Path("."), help="Folder for your data")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--no-browser", action="store_true", help="Don't open a browser tab")
    commands = parser.add_subparsers(dest="command")
    search = commands.add_parser("search", help="Refresh every source without opening the app")
    search.add_argument("--web", metavar="QUERY", default="", help="Search the web instead")
    return parser


def main() -> None:
    args = _parser().parse_args()
    ws = Workspace(args.dir)
    load_env(ws.env)
    if args.command == "search":
        new, total, errors = refresh(ws, args.web)
        print(f"{new} new listings; {total} saved.")
        for error in errors:
            print(f"Source unavailable: {error}")
        return
    serve(ws, args.port, open_browser=not args.no_browser)


if __name__ == "__main__":
    main()
