#\/ ---------- Reviewed by: claude @ 2025-10-09 21:34:49
#\/ $lang: English
#\/ ---------- [Overview]
#\/ TheParser is a tree-sitter-based abstract syntax tree parser implementing the Parser interface. It provides language-agnostic parsing with comment-aware transformations, privacy-preserving hashing of identifiers, and multi-language factory methods. The recent change fixes extract_comments() to reject negative first indices, addressing a previously documented contract violation.
#\/ ---------- [Review]
#\/ The implementation is solid, well-commented, and thoughtfully designed with privacy concerns (hashing leaf values) and performance trade-offs explicitly documented. The recent fix properly addresses the negative index bug by adding an assertion at line 136. Code is ~95% complete with good testability through clean separation of concerns. Minor imperfections exist around edge case handling and performance in factory methods.
#\/ ---------- [Notes]
#\/ Privacy-first design hashes identifiers/literals to enable structural comparison without exposing sensitive data.
#\/ Deliberately skips recursion depth protection, accepting RecursionError as acceptable failure mode for extreme cases.
#\/ Intentional design: extract_comments() only handles full-line comments, ignoring inline end-of-line and block comments per documented contract.
#\/ Factory methods parsers()/ext2parser() rebuild instances on every call for code simplicity despite minor overhead.
#\/ ---------- [Imperfections]
#\/ line_comment() at line 130: When tag is non-empty and line is empty, produces malformed output like '// TAG' with no space before TAG (missing space insertion logic for empty lines).
#\/ extract_comments() at line 140-145: After normalizing negative last, the function allows last < first to return empty results rather than raising an error, which may silently hide caller bugs where invalid ranges are passed.
#\/ parsers()/ext2parser() at lines 195-246: Rebuild entire parser factory on every call. For read-heavy workloads, consider module-level caching with @lru_cache or lazy singleton pattern.
#\/ parse() at line 24: JSON output uses ensure_ascii=False which may cause issues if consumers expect ASCII-only output or have encoding compatibility concerns with non-English identifiers.
#\/ ----------

import os
import json
import hashlib
from typing import Any
from tree_sitter import Parser as TSParser  # type: ignore
from tree_sitter_languages import get_language  # type: ignore
from .index import Parser

# Internal use only for language-specific subclasses, not part of public API
# Don't over-engineer! For example: extreme syntax tree depth is acceptable, no need to preserve Windows line endings, can uniformly reorganize as '\n'
# Requires Python 3.10+
class TheParser(Parser):
    def __init__(self):
        # Initialize parser using tree-sitter
        # Subclasses must have language() return the tree_sitter_parser key, e.g., 'typescript'
        self._parser = TSParser()
        self._parser.set_language(get_language(self.language()))

    def parse(self, source: str) -> str:
        # Key requirements:
        # - Different source semantics must produce different output strings
        # - Comment-only changes should generate identical output strings
        tree = self._parse(source)
        return json.dumps(tree, ensure_ascii=False, sort_keys=True, separators=(',', ':'))

    def _parse(self, source: str) -> Any:
        # Can be overridden by specific language implementations if needed
        source_bytes = source.encode('utf-8')
        tree = self._parser.parse(source_bytes)
        root = tree.root_node

        def node_to_dict(node) -> dict[str, Any]:
            # Recursion depth limited by Python stack (~1000 levels), extreme nesting will trigger RecursionError
            result: dict[str, Any] = {
                'type': node.type,
                'named': bool(node.is_named),
            }

            # Provide privacy-friendly hash fingerprint for named leaf nodes (identifiers, numbers, strings, etc.)
            has_named_child = any(c.is_named for c in node.children)
            if node.is_named and not has_named_child:
                start, end = node.start_byte, node.end_byte
                if end > start:
                    s = source_bytes[start:end]
                    result['value_meta'] = {
                        'length': end - start,
                        'value_hash': hashlib.sha256(s).hexdigest()[:32], # 128-bit hash, collision probability ~2^-128
                    }

            if node.child_count:
                children = []
                token_hashes: list[str] = []
                token_positions: list[int] = []
                named_index = 0
                for child in node.children:
                    if child.is_named:
                        # Skip comment nodes to ensure comment changes don't affect parse() output
                        if 'comment' in child.type.lower():
                            continue
                        children.append(node_to_dict(child))
                        named_index += 1
                    else:
                        # Skip unnamed comment tokens
                        if 'comment' in child.type.lower():
                            continue
                        # Capture fingerprint of non-named tokens like operators/punctuation, and record their relative position (before which named child)
                        start, end = child.start_byte, child.end_byte
                        if end > start:
                            token_hashes.append(hashlib.sha256(source_bytes[start:end]).hexdigest()[:32])
                            token_positions.append(named_index)
                if children:
                    result['children'] = children
                if token_hashes:
                    result['tokens'] = token_hashes
                    result['token_positions'] = token_positions
            return result

        return {
            'language': self.language(),
            'version': 1,
            'tree': node_to_dict(root),
        }

    def comment(self, source: str, line: int, comment: str, tag = '') -> str:
        # Append comment to end of specified line; line < 0 counts backward from end
        lines = source.splitlines()
        n = len(lines)
        if line < 0:
            line += n
        if line < 0 or line >= n:
            raise ValueError(f"Line {line} is out of range")
        comment = self.line_comment(comment, tag)
        if comment is None:
            raise ValueError("Line comment is not supported")
        lines[line] += ' ' + comment
        return '\n'.join(lines) # Uniformly use '\n' and remove trailing newline, caller must handle their own needs

    def insert_comment(self, source: str, line: int, comment: str, tag = '', block = False) -> str:
        # Insert comment at given line; line < 0 counts backward from end
        comment = self.block_comment(comment, tag) if block else self.line_comment(comment, tag)
        if comment is None:
            raise ValueError("Comment is not supported")
        lines = source.splitlines()
        n = len(lines)
        if line < 0:
            line += n
        line = max(0, min(line, n))  # Allow insertion at end
        lines.insert(line, comment)
        return '\n'.join(lines) # Uniformly use '\n' and remove trailing newline, caller must handle their own needs

    def block_comment(self, comment: str, tag = '', force = False) -> str | None:
        # Can be overridden by specific language implementations if needed
        prefix = self._block_comment_prefix()
        if prefix == '':
            return None if force else self.line_comment(comment, tag, True)
        suffix = self._block_comment_suffix()
        if suffix in comment: # Don't escape here, user can avoid with e.g., '* /'
            raise ValueError(f"Block comment suffix '{suffix}' found in comment")
        space = '\n' if '\n' in comment else ' '
        return prefix + tag + space + comment + space + suffix

    def line_comment(self, comment: str, tag = '', force = False) -> str | None:
        # Can be overridden by specific language implementations if needed
        prefix = self._line_comment_prefix()
        if prefix == '':
            return None if force else self.block_comment(comment, tag, True)
        lines = comment.split('\n')
        for i, line in enumerate(lines):
            if line.strip() != '':
                line = prefix + tag + ' ' + line
            lines[i] = line
        return '\n'.join(lines)

    def extract_comments(self, source: str, tag: str, first = 0, last = -1) -> tuple[list[str], str]:
        # Extract tagged comments from source (line range [first, last]); only supports full-line line comments, ignores block comments and inline end-of-line comments
        assert first >= 0, "Negative `first` indexes are not supported"

        lines = source.splitlines()
        n = len(lines)
        if last < 0:
            last += n
        elif last >= n:
            last = n - 1
        if last < first:
            return [], source

        next = last + 1
        comments = []
        kept: list[str] = []
        kept.extend(lines[0:first])
        for i in range(first, next):
            line = lines[i]
            # Intentionally skip inline end-of-line comments, only capture full-line comments
            comment = self._extract_line_comment(line.strip(), tag)
            if comment is None:
                kept.append(line)
            else:
                comments.append(comment)
        kept.extend(lines[next:])
        return comments, '\n'.join(kept) # Uniformly use '\n' and remove trailing newline, caller must handle their own needs

    def _extract_line_comment(self, line: str, tag: str) -> str | None:
        # Only match full-line comments (starting at column 0 after strip); multi-line content generated by block_comment() remains unchanged
        # Tags requiring leading space should include it themselves (e.g., ' Author:')
        line = line.strip()
        prefix = self._line_comment_prefix()
        if prefix != '': # Line comment example: // Author: Elon Musk
            prefix += tag
            if line.startswith(prefix):
                return line[len(prefix):].strip() # Returns 'Elon Musk'
            return None

        prefix = self._block_comment_prefix()
        if prefix != '': # Only handle single-line block comments, e.g., /* Author: Elon Musk */
            prefix += tag
            suffix = self._block_comment_suffix()
            if line.startswith(prefix) and line.endswith(suffix):
                return line[len(prefix):-len(suffix)].strip() # Returns 'Elon Musk'
            return None
        return None

    def _block_comment_prefix(self) -> str:
        # Can be overridden by specific language implementations if needed
        return '/*'

    def _block_comment_suffix(self) -> str:
        # Can be overridden by specific language implementations if needed
        return '*/'

    def _line_comment_prefix(self) -> str:
        # Can be overridden by specific language implementations if needed
        return '//'

    @staticmethod
    def parsers() -> dict[str, Parser]:
        # Dynamically import all supported parser classes to avoid circular imports
        from ._parser.python import PythonParser
        from ._parser.typescript import TypescriptParser
        from ._parser.java import JavaParser
        from ._parser.c import CParser
        from ._parser.cpp import CppParser
        from ._parser.csharp import CSharpParser
        from ._parser.go import GoParser
        from ._parser.rust import RustParser
        from ._parser.bash import BashParser
        from ._parser.html import HtmlParser

        parser_classes = [
            PythonParser,
            TypescriptParser,
            JavaParser,
            CParser,
            CppParser,
            CSharpParser,
            GoParser,
            RustParser,
            BashParser,
            HtmlParser,
        ]

        factory: dict[str, Parser] = {}
        for parser_class in parser_classes:
            try:
                parser = parser_class()
            except Exception as e:  # Should not occur; each subclass should ensure it can be legally instantiated
                raise ValueError(f"Failed to initialize parser for {parser_class.__name__}") from e
            lang = parser.language()
            if lang in factory:  # Should not occur; each subclass should ensure its language is unique
                raise ValueError(f"Language {lang} is shared by multiple parsers: {parser_class.__name__}")
            factory[lang] = parser

        return factory

    @staticmethod
    def ext2parser() -> dict[str, Parser]:
        # Build mapping from file extensions to parsers
        map: dict[str, Parser] = {}
        parsers = TheParser.parsers()
        for parser in parsers.values():
            for ext in parser.extensions():
                ext = ext.lower()
                # Each parser.extensions() ensures returned format has leading dot
                if ext in map:  # Should not occur; e.g., C/C++ must each ensure their handled extensions are different
                    raise ValueError(f"Extension {ext} is shared by multiple parsers: {map[ext].language()} and {parser.language()}")
                map[ext] = parser
        return map

    @staticmethod
    def create(language: str) -> Parser:
        # Rebuild full parser instances to simplify code; cost is minimal, frequency is extremely low, performance impact negligible
        parsers = TheParser.parsers()
        if language not in parsers:
            raise ValueError(f"Language {language} not supported")
        return parsers[language]

    @staticmethod
    def create_by_filename(fn: str) -> Parser:
        # Rebuild full parser instances to simplify code; cost is minimal, frequency is extremely low, performance impact negligible
        ext2parser = TheParser.ext2parser()
        # Multi-segment extensions like "foo.d.ts" will return last segment ".ts", sufficient to find parser
        _, ext = os.path.splitext(fn)
        ext = ext.lower()
        if ext not in ext2parser:
            raise ValueError(f"Extension {ext} not supported for {fn}")
        return ext2parser[ext]