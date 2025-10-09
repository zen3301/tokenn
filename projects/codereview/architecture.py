#\/ ---------- Reviewed by: codex @ 2025-10-09 23:47:43
#\/ $lang: English
#\/ ---------- [Overview]
#\/ Abstract base definitions specify reviewer, file-level, and project-level APIs with typed signatures, module-level factories, and descriptive inline documentation for orchestrating AI-driven reviews across files and projects.
#\/ ---------- [Review]
#\/ Overall structure is clean and typed, but each static factory method instantiates a concrete class. That directly contradicts the explicit requirement that this architecture module host abstract declarations only and forces knowledge of concrete implementations, undermining extensibility. No tests apply because this file is specification-only.
#\/ ---------- [Notes]
#\/ The inline documentation explains orchestration duties for AI-powered review components and their expected inputs/outputs.
#\/ ----------

#\% Architecture breakdown of sub-modules, templates, and optional sub-systems (imported from sub-folders):
#\% - Abstract class and methods only except static method(s), providing all context (without implementation) for callers
#\% - Static factory method(s)

from typing import Any
from abc import ABC, abstractmethod
from ..codeparser.index import Parser


class Reviewer(ABC):
    # Reviewer interface responsible for coordinating with the AI backend.

    @abstractmethod
    def ai(self) -> str:
        # Return the configured AI identifier.
        pass

    @abstractmethod
    def init(self, system_md: str, request: Any, parser: Parser | None = None, lang = '', timeout = 0) -> tuple[list[str], str | None, int]:
        # Assemble CLI parameters for the AI call; source text is piped via stdin to dodge shell limits.
        pass

    @abstractmethod
    def exec(
        self,
        args: list[str],
        timeout: int,
        stdin_prompt: str | None = None,
        parser: Parser | None = None,
        expected: str | None = None,
    ) -> tuple[Any, str | None]:
        # Execute the AI review run and validate the structured response.
        pass

    @staticmethod
    def create(ai: str, tmp: str | None = None) -> "Reviewer":
        # Factory helper that prevents circular imports.
        from .reviewer import TheReviewer
        return TheReviewer(ai, tmp)


class ReviewFile(ABC):
    # File-level reviewer responsible for generating inline review artifacts.

    @abstractmethod
    def review(self, reviewer: Reviewer, src_path: str, references: list[str], context = '', lang = '', timeout=0, retry = 1, tmp: str | None = None) -> str | None:
        # Pipeline: load source -> invoke AI review (with retries) -> validate AST -> emit inline annotations.
        # references: supplemental files forwarded to the reviewer.
        # context: optional metadata shared with the AI prompt.
        # lang: annotation language selection (default English).
        # timeout: wall-clock seconds allowed per execution.
        # retry: max attempts; final AST mismatch keeps prior inline comments but still preserves the review payload.
        # tmp: scratch file for persisting review-time errors.
        pass

    @staticmethod
    def create() -> "ReviewFile":
        # Factory helper that prevents circular imports.
        from .reviewfile import TheReviewFile
        return TheReviewFile()


class ReviewProject(ABC):
    # Project-level reviewer that assembles and emits the aggregated .REVIEW.md report.

    @abstractmethod
    def review(self, reviewer: Reviewer, path: str, reviews: dict[str, str], folders: list[str], references: list[str], context = '', lang = '', timeout=0) -> str | None:
        # Entry point: load consolidated results, run project-scale AI review, and refresh .REVIEW.md.
        # reviews: mapping of file names to their inline review output.
        # folders: module directories whose .REVIEW.md summaries are incorporated.
        # references: auxiliary documents available to the AI.
        # context: additional project metadata passed to the reviewer.
        # lang: report language (default English).
        # timeout: wall-clock seconds allowed for the AI request.
        pass

    @abstractmethod
    def extract_review(self, src_path: str) -> str | None:
        # Extract inline review annotations (marked with %%) and return the concatenated text or None if absent.
        pass

    @staticmethod
    def create() -> "ReviewProject":
        # Factory helper that prevents circular imports.
        from .reviewproject import TheReviewProject
        return TheReviewProject()