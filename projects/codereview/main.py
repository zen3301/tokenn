#\/ ---------- Reviewed by: codex @ 2025-10-09 21:46:31
#\/ $lang: English
#\/ ---------- [Overview]
#\/ CLI entry point wires parsed command-line flags to Codereview factory construction and dispatches to modified, directory, single-file, or synthesis workflows determined by path and synthesize flags.
#\/ ---------- [Review]
#\/ Structure is straightforward and aligns with the abstract Codereview contract; dispatch ordering guards mode precedence correctly, and early exits encode success via positive counts or truthy review payloads. Error propagation relies entirely on downstream Codereview methods, so this wrapper remains light but should inherit their edge-case handling.
#\/ ---------- [Notes]
#\/ Exit codes rely on downstream review methods returning either positive counts or truthy strings; any extension should preserve those conventions to avoid confusing CLI outcomes.
#\/ ----------

import argparse
from pathlib import Path
from .index import Codereview


def main(argv: list[str]) -> int:
    # Parse CLI arguments.
    parser = argparse.ArgumentParser(description="Code review.")
    parser.add_argument("--ai", choices=["codex", "claude"], required=True, help="AI cli to use for review.")
    parser.add_argument("--path", "-p", type=str, required=True, help="Path to review.")
    parser.add_argument("--modified", "-m", action="store_true", help="Review git modified files only.")
    parser.add_argument("--synthesize", "-s", action="store_true", help="Synthesize .REVIEW.md for the path.")
    parser.add_argument("--context", "-c", type=str, default='', help="Additional context for review.")
    parser.add_argument("--retry", "-r", type=int, default=1, help="Retry count for review.")
    parser.add_argument("--timeout", "-t", type=int, default=0, help="Timeout for review.")
    parser.add_argument("--lang", "-l", type=str, default='', help="Language for review.")
    parser.add_argument("--tmp", "-d", type=str, help="Temporary directory to dump logs.")
    parser.add_argument("--parallel", action="store_true", help="Enable parallel review.")
    args = parser.parse_args(argv)

    review = Codereview.create(args.ai, args.context, args.retry, args.timeout, args.lang, args.tmp)

    # Four operating modes in descending priority:
    # 1. Git modified mode (-m): scan every tracked change in the repository
    # 2. Directory mode (-p is a directory): review top-level entries without recursion
    # 3. Single-file mode (-p is file without -s): review the specified file
    # 4. Synthesis mode (-s with file or directory): regenerate .REVIEW.md for the target scope
    if args.modified: # -m -p projects/ [-s]
        # Requires the path to reside inside a git repository or review_modified will abort.
        return 0 if review.review_modified(args.path, args.synthesize, args.parallel) > 0 else -1

    elif Path(args.path).is_dir(): # -p projects/ [-s]
        return 0 if review.review_path(args.path, args.synthesize, args.parallel) > 0 else -1

    elif not args.synthesize: # -p projects/a.py (single-file mode does not allow -s)
        return 0 if review.review_code(args.path, args.parallel) else -1

    else: # -p projects/.REVIEW.md -s or -p projects/ -s
        # Generate or update .REVIEW.md in the correct location for the provided path.
        return 0 if review.review_proj(args.path, args.parallel) else -1


def cli() -> None:
    import sys as _sys
    _sys.exit(main(_sys.argv[1:]))


if __name__ == "__main__":
    cli()