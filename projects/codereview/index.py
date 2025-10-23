#\/ ---------- Reviewed by: codex @ 2025-10-09 23:48:30
#\/ $lang: English
#\/ ---------- [Overview]
#\/ Defines a lightweight abstract `Codereview` interface with typed entry points for multiple review operations plus a static factory that defers to the default concrete implementation via a local import to avoid circular references.
#\/ ---------- [Review]
#\/ The interface delivers a clean abstract surface and meets the stated requirements, with consistent type hints and a reasonable static factory. The concrete dependency pulled in by the factory is intentional, so there are no critical correctness risks detected. Testability depends on the availability of other modules but is acceptable at the interface layer.
#\/ ---------- [Notes]
#\/ Static factory currently hardwires `TheCodereview`; swapping implementations would require edits here.
#\/ ----------

#\% Public facing interface:
#\% - Abstract class and methods only except static method(s), providing all context (without implementation) for callers
#\% - Static factory method(s)

from typing import dict
from abc import ABC, abstractmethod


class Codereview(ABC):
    @abstractmethod
    def review_code(self, src_path: str) -> str | None:
        # Review a single source file
        pass

    @abstractmethod
    def review_list(self, files: list[str], parallel: bool = False) -> dict:
        # Review a list of files and return a mapping: file -> review content
        pass

    @abstractmethod
    def review_path(self, path: str, synthesize: bool = False, parallel: bool = False) -> int:
        # Review all code files in the given path (non-recursive, skips unsupported types)
        pass

    @abstractmethod
    def review_modified(self, path: str, synthesize: bool = False, parallel: bool = False) -> int:
        # Review modified files in the repository; optionally synthesize .REVIEW.md per affected dir
        pass

    @abstractmethod
    def review_proj(self, path: str, parallel: bool = False) -> str | None:
        # Complete outstanding reviews and generate a project-level .REVIEW.md
        pass

    @staticmethod
    def create(ai: str, context = '', retry = 1, timeout=0, lang = '', tmp: str | None = None) -> "Codereview":
        # Factory method returning the default implementation while keeping the import local to dodge circular dependencies
        from .codereview import TheCodereview
        return TheCodereview(ai, context, retry, timeout, lang, tmp)