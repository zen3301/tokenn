#\/ ---------- Reviewed by: codex @ 2025-10-23 19:17:22
#\/ $lang: English
#\/ ---------- [Overview]
#\/ CLI main() parses review parameters and dispatches to the Codereview implementation, honoring a clearly documented priority order for modified, synthesis, directory, and single-file workflows that drive code and project review generation.
#\/ ---------- [Review]
#\/ The reordered condition cleanly delivers the intended pure synthesis path without disturbing other modes; logic is small, cohesive, and aligns with the documented priority, though no automated coverage accompanies the fix.
#\/ ---------- [Notes]
#\/ With --synthesize set, directory scans are skipped entirely, so run without the flag when file-level annotations are required alongside project regeneration.
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
        # Requires the path to reside inside a git repository or review_modified will abort.
        return 0 if review.review_modified(args.path, args.synthesize, args.parallel, args.fix) > 0 else -1

    elif args.synthesize:  # -p projects/.REVIEW.md -s or -p projects/ -s
        # Prioritize synthesis to honor pure .REVIEW.md regeneration requests.
        return 0 if review.review_proj(args.path, args.parallel, args.fix) else -1

    elif target_path.is_dir():  # -p projects/
        return 0 if review.review_path(args.path, args.synthesize, args.parallel, args.fix) > 0 else -1

    else:  # -p projects/a.py
        return 0 if review.review_code(args.path, args.fix) else -1


def cli() -> None:
    import sys as _sys
    _sys.exit(main(_sys.argv[1:]))


if __name__ == "__main__":
    cli()