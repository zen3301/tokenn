#\/ ---------- Reviewed by: codex @ 2025-10-23 19:20:34
#\/ $lang: English
#\/ ---------- [Overview]
#\/ Implements the main code review coordinator that stitches together reviewers, gathers Git context, and orchestrates file- and project-level reviews with optional parallel execution.
#\/ ---------- [Review]
#\/ The fallback to a single worker when `os.cpu_count()` cannot provide a value resolves the previously reported crash, and the surrounding flow remains coherent and testable without any new concerns.
#\/ ---------- [Notes]
#\/ Parallel execution now safely defaults to a single thread when CPU count cannot be detected, avoiding the earlier ThreadPoolExecutor crash.
#\/ ----------

import os
import json
from git import Repo
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from ..codeparser.index import Parser
from .architecture import Reviewer, ReviewFile, ReviewProject
from .index import Codereview

class TheCodereview(Codereview):
    def __init__(self, ai: str, context = '', timeout=0, lang = '', tmp: str | None = None):
        self.reviewer = Reviewer.create(ai, tmp)
        self.file = ReviewFile.create()
        self.fixer = ReviewFile.createFixer()
        self.project = ReviewProject.create()

        self.context = context
        self.timeout = timeout
        self.lang = lang
        self.tmp = tmp
        # Supported extensions for filtering reviewable files
        self.extensions = tuple(Parser.ext2parser().keys())

    def _collect_references(self, project: str) -> list[str]:
        # Normalize project path and ensure trailing slash
        if project != '' and not project.endswith('/'):
            project += '/'

        references = [str(f) for f in Path(project).glob('*.md') if not f.name.endswith('.REVIEW.md')] # Avoid context polution from outdated review file
        return references

    def _git_diff(self, src_path: str) -> str:
        # Get repository diff for the target file relative to the working tree
        try:
            src = Path(src_path).resolve()  # Convert to absolute path
            repo = Repo(src.parent, search_parent_directories=True)  # Search up to repo root
            src = src.relative_to(repo.working_dir)  # Normalize to repo-relative path
            return repo.git.diff("--", str(src))
        except Exception:
            return ''  # VERIFIED! Return empty diff so callers can continue without diff context.

    def _git_modified(self, path: str) -> list[str]:
        # Collect modified, staged, or untracked files within the git repository
        try:
            path = self._path(path)  # Normalize to an absolute directory path
            repo = Repo(path, search_parent_directories=True)  # Search up to repo root
            try:
                modified = repo.git.diff("HEAD", "--name-only", "--diff-filter=d").splitlines()  # Modified files, excluding deletions
            except Exception: # Repo has no commits yet
                modified = []
            staged   = repo.git.diff("--cached", "--name-only", "--diff-filter=d").splitlines()  # Staged files, excluding deletions
            untracked = repo.untracked_files  # Untracked files
            relative = list(dict.fromkeys(modified + staged + untracked))  # Deduplicate while preserving order
            # Convert to absolute paths
            repo_root = Path(repo.working_tree_dir)
            return [str(repo_root / f) for f in relative]
        except Exception as e:
            raise ValueError(f"Failed to get git modified files: {e}") from e
    
    def _path(self, path: str) -> str:
        # Return directory path for files or normalize already-directory inputs
        p = Path(path).resolve()
        return str(p) if p.is_dir() else str(p.parent)

    def _paths(self, files: list[str]) -> list[str]:
        # Extract unique directory paths from files and keep them ordered
        paths = []
        for file in files:
            path = self._path(file)
            if path not in paths:
                paths.append(path)

        # Sort descending by length so child directories are processed before parents
        return sorted(paths, key=len, reverse=True)
    
    def _diff(self, src_path: str) -> str:
        ctx: dict[str, str] = {}
        diff = self._git_diff(src_path)
        if diff != '':
            ctx['git-diff'] = diff
        if self.context != '':
            ctx['context'] = self.context
        return json.dumps(ctx, indent=2, ensure_ascii=False)

    def review_code(self, src_path: str, fix: int = 0) -> str | None:
        # Review/fix a single source file, fix=0 to review only, >0 as the maximum iterations of fix and review loops
        # Lowercase before suffix comparison so uppercase extensions (e.g., ".PY") stay reviewable.
        if not src_path.lower().endswith(self.extensions):  # Check for supported extensions
            return None

        fn = src_path.replace('\\\\', '/').split('/')[-1]  # Extract filename
        project = src_path[0:-len(fn)]  # Extract parent directory path
        references = self._collect_references(project)

        if fix > 0:
            reviewer = self.fixer
            retry = fix
        else:
            reviewer = self.reviewer
            retry = 1
        return reviewer.review(self.reviewer, src_path, references, self.context, self.lang, self.timeout, retry, self.tmp)

    def review_list(self, files: list[str], parallel: bool = False, fix: int = 0) -> dict[str, str]:
        # Review a list of files and return a mapping: file -> review content
        reviews = {}
        if parallel:
            workers = os.cpu_count() or 1  # Fallback to single worker when CPU count is unavailable.
            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = [executor.submit(self.review_code, file, fix) for file in files]
                results = [future.result() for future in futures]
            for file, review in zip(files, results):
                if review is not None:
                    reviews[file] = review
        else:
            for file in files:
                review = self.review_code(file, fix)
                if review is not None:
                    reviews[file] = review
        return reviews

    def review_path(self, path: str, synthesize: bool = False, parallel: bool = False, fix: int = 0) -> int:
        # Review all supported files located directly under the provided path
        files = [str(f) for f in Path(path).resolve().glob('*.*')]
        n = len(self.review_list(files, parallel, fix))  # Run file-level reviews on all sources
        if synthesize:  # Optionally generate or update .REVIEW.md for the directory
            self.review_proj(path, parallel, fix)
        return n

    def review_modified(self, path: str, synthesize: bool = False, parallel: bool = False, fix: int = 0) -> int:
        # Review files with pending git changes and optionally synthesize directory reviews
        files = self._git_modified(path)
        n = len(self.review_list(files, parallel, fix))  # Run file-level reviews on modified sources
        if synthesize:
            paths = self._paths(files)  # Collect affected directories in descending length order
            for path in paths:  # Regenerate .REVIEW.md for each directory
                self.review_proj(path, parallel, fix)
        return n

    def review_proj(self, path: str, parallel: bool = False, fix: int = 0) -> str | None:
        # Generate a project-level review report (.REVIEW.md)
        path_obj = Path(path).resolve()
        if path_obj.exists() and path_obj.is_dir():
            dir_path = path_obj
            md_path = dir_path / '.REVIEW.md'
        else:
            md_path = path_obj
            dir_path = md_path.parent

        dir_path.mkdir(parents=True, exist_ok=True)
        project = str(dir_path).replace('\\\\', '/')  # Normalize Windows path separators
        references = self._collect_references(project)

        # Include only top-level files whose extensions map to known parsers
        files = [str(f) for f in dir_path.glob('*.*') if f.is_file()]
        # Include only first-level subdirectories and skip dot-prefixed directories
        folders = [str(f) for f in dir_path.glob('*/') if not f.name.startswith('.')]

        reviews = {}
        to_review = []
        md_path_str = str(md_path)
        exts = tuple(Parser.ext2parser().keys())
        codefix = fix > 0
        reviewed = 'fixed' if codefix else 'reviewed'
        for file in files:
            # Lowercase ensures cached reviews are picked up even when filesystem reports uppercase suffixes.
            if not file.lower().endswith(exts):  # Process only supported languages
                continue
            review = self.project.extract_review(file)  # Pull existing review if available
            if review and '---------- [Review]' in review and not (codefix and '---------- [Issues]' in review):
                print(f'{file} already {reviewed}')
                reviews[file] = review
            else:
                print(f'{file} not {reviewed}')
                to_review.append(file)

        reviews.update(self.review_list(to_review, parallel, fix)) # Add newly reviewed files
        return self.project.review(self.reviewer, md_path_str, reviews, folders, references, self.context, self.lang, self.timeout)