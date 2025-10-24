#\/ ---------- Reviewed by: claude @ 2025-10-24 15:13:04
#\/ $lang: English
#\/ ---------- [Overview]
#\/ AI2JSON is an abstract base class defining a unified interface for AI CLI integrations. It specifies methods for identifying the AI provider, initializing CLI parameters (with timeout calculation logic), executing subprocesses, and provides a factory method to instantiate concrete implementations (Codex, Claude).
#\/ ---------- [Review]
#\/ The abstract interface is well-designed and follows proper ABC patterns. The contract is clear with detailed docstrings explaining timeout semantics and return value structures. The factory pattern with delayed imports avoids circular dependencies. Interface separation is clean: abstract methods define the contract, static factory provides instantiation. Estimated completion: 100%. The code is straightforward and testable through concrete implementations.
#\/ ---------- [Notes]
#\/ Timeout parameter behavior (0, <0, >0) is documented but somewhat unconventional: negative values being treated as 'per-KB budget' is non-standard API design that may confuse callers.
#\/ Factory method uses delayed imports explicitly to avoid circular dependencies between index.py and ai2json.py.
#\/ The init() method specifies dynamic timeout calculation based on content length, indicating the class handles variable-duration AI operations.
#\/ Return signatures consistently use tuple[T, str | None] pattern for value-or-error results (no exceptions thrown for normal failures).
#\/ ---------- [Imperfections]
#\/ The timeout parameter semantics (especially negative values as per-KB budget) could be simplified. Consider separate parameters like timeout and per_kb_budget for clarity.
#\/ Type hint for exec() return value uses Any for the parsed JSON object when dict[str, Any] would be more precise given the docstring states 'expected to be dict'.
#\/ The static factory method create() accepts tmp parameter but the abstract class doesn't define how tmp should be used, creating an implicit contract that concrete implementations must handle it.
#\/ ----------

from typing import Any
from abc import ABC, abstractmethod

# AI2JSON abstract base class: defines unified AI interface specification; all concrete AI implementations must inherit this class
class AI2JSON(ABC):
    @abstractmethod
    def ai(self) -> str:
        # Return AI provider identifier name, e.g., 'codex', 'claude'
        pass

    @abstractmethod
    def init(self, system_prompt: str, user_prompt: str, timeout: int = 0) -> tuple[list[str], str | None, int]:
        # Initialize CLI invocation parameters
        # Returns: (CLI argument list, stdin prompt content to bypass command-line length limits, final timeout in seconds)
        # timeout=0: dynamically calculate based on content length (default per-KB budget + default base overhead)
        # timeout<0: use absolute value as per-KB budget (seconds), add default base overhead
        # timeout>0: directly use this value as final timeout
        pass

    @abstractmethod
    def exec(self, args: list[str], timeout: int, stdin_prompt: str | None = None) -> tuple[Any, str | None]:
        # Execute CLI subprocess and parse result
        # Returns: (parsed JSON object (expected to be dict), error message or None on success)
        pass

    @staticmethod
    def create(ai: str, tmp: str | None = None) -> "AI2JSON":
        # Factory method: create concrete AI implementation via delayed imports to avoid circular dependencies
        # ai: AI provider identifier ('codex', 'claude', etc.)
        # tmp: optional temporary directory path for debug output
        from .ai2json import TheAI2JSON
        return TheAI2JSON.create(ai, tmp)