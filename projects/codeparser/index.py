#\/ ---------- Reviewed by: codex @ 2025-10-09 21:20:18
#\/ $lang: English
#\/ ---------- [Overview]
#\/ Abstract Parser interface defines parsing, comment manipulation, and factory helpers for multi-language handling, with clear contracts for how parsing output relates to comment-only edits and standardized factory accessors.
#\/ ---------- [Review]
#\/ The interface remains concise and well-documented, with contracts that codify deterministic parsing outputs and negative indexing expectations; testability depends on downstream implementations but the surface API is coherent and consistent.
#\/ ---------- [Notes]
#\/ Documented expectation that insert_comment must treat block=True consistently with block_comment helpers.
#\/ ----------

from abc import ABC, abstractmethod

# Public interface without concrete implementation; provides minimal context for consumers.
# Supports multi-language parsing plus comment insertion and extraction.
# Callers are responsible for supplying valid inputs.
class Parser(ABC):
    @abstractmethod
    def language(self) -> str:
        # Return tree-sitter language key such as 'python' or 'typescript'.
        pass

    @abstractmethod
    def extensions(self) -> list[str]:
        # Return supported file extensions such as ['.py'] or ['.ts', '.js'].
        pass

    @abstractmethod
    def parse(self, source: str) -> str:
        # Contract requirements:
        # - Different source logic must yield distinct output strings.
        # - Changes limited to comments must preserve the exact output string.
        pass

    @abstractmethod
    def comment(self, source: str, line: int, comment: str, tag = '') -> str:
        # Append an end-of-line comment at the specified line; negative lines index from the end.
        pass

    @abstractmethod
    def insert_comment(self, source: str, line: int, comment: str, tag = '', block = False) -> str:
        # Insert a comment at the given line; negative lines index from the end.
        # Implementers must honor block comment insertion when block=True for consistency with block_comment().
        pass

    @abstractmethod
    def block_comment(self, comment: str, tag = '') -> str:
        # Return a block comment string.
        pass

    @abstractmethod
    def line_comment(self, comment: str, tag = '') -> str:
        # Return a single-line comment string.
        pass

    @abstractmethod
    def extract_comments(self, source: str, tag: str, first = 0, last = -1) -> tuple[list[str], str]:
        # Extract tagged comments and return (comment_list, source_without_comments).
        # first/last define the inclusive line range and accept negative indices.
        # Supports only full-line line comments (no block or inline trailing comments).
        pass

    # Use function-scoped imports to avoid circular dependencies.
    @staticmethod
    def parsers() -> dict[str, "Parser"]:
        from .parser import TheParser
        return TheParser.parsers()

    @staticmethod
    def ext2parser() -> dict[str, "Parser"]:
        from .parser import TheParser
        return TheParser.ext2parser()

    @staticmethod
    def create(language: str) -> "Parser":
        from .parser import TheParser
        return TheParser.create(language)

    @staticmethod
    def create_by_filename(fn: str) -> "Parser":
        from .parser import TheParser
        return TheParser.create_by_filename(fn)