#\/ ---------- Reviewed by: codex @ 2025-10-24 15:23:40
#\/ $lang: English
#\/ ---------- [Overview]
#\/ CLI entrypoint chooses between modified, synthesis, directory, and single-file review modes, delegating to the shared Codereview abstraction while documenting the expected return values for each pathway.
#\/ ---------- [Review]
#\/ Change correctly treats zero-result runs as success, aligning with Codereview semantics. Code paths remain straightforward, and no further issues surfaced in testing logic or argument handling.
#\/ ---------- [Notes]
#\/ Branch priorities ensure synthesis requests override directory/file heuristics before falling back to single-file review.
#\/ ----------

#\% pip uninstall codereview
#\% pip install git+https://github.com/zen3301/tokenn.git#subdirectory=projects/codereview

#% pip uninstall codereview
#% pip install git+https://github.com/zen3301/tokenn.git#subdirectory=projects/codereview

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
    parser.add_argument("--fix", "-f", type=int, default=0, help="=0 to review only, >0 as the maximum iterations of fix and review loops")
    parser.add_argument("--timeout", "-t", type=int, default=0, help="Timeout for review.")
    parser.add_argument("--lang", "-l", type=str, default='', help="Language for review.")
    parser.add_argument("--tmp", "-d", type=str, help="Temporary directory to dump logs.")
    parser.add_argument("--parallel", action="store_true", help="Enable parallel review.")
    args = parser.parse_args(argv)

    review = Codereview.create(args.ai, args.context, args.timeout, args.lang, args.tmp)
    target_path = Path(args.path)

    # Four operating modes in descending priority:
    # 1. Git modified mode (-m): scan every tracked change in the repository
    # 2. Synthesis mode (-s): regenerate .REVIEW.md for the requested scope
    # 3. Directory mode (-p is a directory): review top-level entries without recursion
    # 4. Single-file mode (-p is file without -s): review the specified file
    if args.modified:  # -m -p projects/ [-s]
        count = review.review_modified(args.path, args.synthesize, args.parallel, args.fix)
        # Non-negative counts represent successful runs, including legitimate no-op scans.
        return 0 if count >= 0 else -1

    elif args.synthesize:  # -p projects/.REVIEW.md -s or -p projects/ -s
        result = review.review_proj(args.path, args.parallel, args.fix)
        # review_proj returns None on failure; empty strings are valid no-op outputs.
        return 0 if result is not None else -1

    elif target_path.is_dir():  # -p projects/
        count = review.review_path(args.path, args.synthesize, args.parallel, args.fix)
        # Directory reviews yield non-negative counts even when no actionable files exist.
        return 0 if count >= 0 else -1

    else:  # -p projects/a.py
        result = review.review_code(args.path, args.fix)
        # review_code uses None to indicate failure; empty strings reflect comment-only sources.
        return 0 if result is not None else -1


def cli() -> None:
    import sys as _sys
    _sys.exit(main(_sys.argv[1:]))


if __name__ == "__main__":
    cli()