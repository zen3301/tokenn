#\/ ---------- Reviewed by: codex @ 2025-10-23 19:13:34
#\/ $lang: English
#\/ ---------- [Overview]
#\/ The file defines an abstract Codereview interface with uniform method signatures for reviewing individual files, lists, paths, modified content, and entire projects, alongside a static factory for obtaining the concrete implementation.
#\/ ---------- [Review]
#\/ Interface design is consistent and abstract-only as required, with clear parameters and return annotations. The static factory delegates instantiation cleanly via a local import. Overall structure appears complete and ready for implementation.
#\/ ---------- [Notes]
#\/ Local import inside create() avoids circular dependencies while keeping the interface lightweight.
#\/ ----------

#\% Public facing interface:
#\% - Abstract class and methods only except static method(s), providing all context (without implementation) for callers
#\% - Static factory method(s)

from abc import ABC, abstractmethod


class Codereview(ABC):
    @abstractmethod
    def review_code(self, src_path: str, fix: int = 0) -> str | None:
        # Review/fix a single source file, fix=0 to review only, >0 as the maximum iterations of fix and review loops
        pass

    @abstractmethod
    def review_list(self, files: list[str], parallel: bool = False, fix: int = 0) -> dict[str, str]:
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