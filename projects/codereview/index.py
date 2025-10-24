#\/ ---------- Reviewed by: codex @ 2025-10-24 15:18:43
#\/ $lang: English
#\/ ---------- [Overview]
#\/ Defines the abstract Codereview interface that exposes review entry points for single files, lists, paths, modified sets, and full projects, plus a factory method to obtain the concrete implementation.
#\/ ---------- [Review]
#\/ The abstraction cleanly matches the stated requirements: all public methods remain abstract (besides the static factory), signatures appear consistent, and the factory defers import to avoid circular dependencies. No defects found.
#\/ ---------- [Notes]
#\/ Static factory defers importing TheCodereview until call time to avoid circular imports.
#\/ ----------

#\% Public facing interface:
#\% - Abstract class and methods only except static method(s), providing all context (without implementation) for callers
#\% - Static factory method(s)

from abc import ABC, abstractmethod


class Codereview(ABC):
    @abstractmethod
    def review_code(self, src_path: str, fix: int = 0, git_diff: bool = False) -> str | None:
        # Review/fix a single source file (optionally include the git diff in context), fix=0 to review only, >0 as the maximum iterations of fix and review loops
        pass

    @abstractmethod
    def review_list(self, files: list[str], parallel: bool = False, fix: int = 0, git_diff: bool = False) -> dict[str, str]:
        # Review/fix a list of files and return a mapping: file -> review content
        pass

    @abstractmethod
    def review_path(self, path: str, synthesize: bool = False, parallel: bool = False, fix: int = 0) -> int:
        # Review/fix all code files in the given path (non-recursive, skips unsupported types)
        pass

    @abstractmethod
    def review_modified(self, path: str, synthesize: bool = False, parallel: bool = False, fix: int = 0) -> int:
        # Review/fix modified files in the repository; optionally synthesize .REVIEW.md per affected dir
        pass

    @abstractmethod
    def review_proj(self, path: str, parallel: bool = False, fix: int = 0) -> str | None:
        # Complete/fix outstanding reviews and generate a project-level .REVIEW.md
        pass

    @staticmethod
    def create(ai: str, context = '', timeout=0, lang = '', tmp: str | None = None) -> "Codereview":
        # Factory method returning the default implementation while keeping the import local to dodge circular dependencies
        from .codereview import TheCodereview
        return TheCodereview(ai, context, timeout, lang, tmp)