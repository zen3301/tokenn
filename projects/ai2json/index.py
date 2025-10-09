#\/ ---------- Reviewed by: codex @ 2025-10-09 21:07:24
#\/ $lang: English
#\/ ---------- [Overview]
#\/ Defines an abstract AI2JSON base class with required lifecycle steps and a factory method that delegates creation to a concrete implementation resolved via delayed import.
#\/ ---------- [Review]
#\/ The class offers a clear ABC contract with detailed comments; implementation specifics appear deferred to other modules, leaving no actionable defects in this snippet.
#\/ ----------

from typing import Any
from abc import ABC, abstractmethod

# AI2JSON abstract base class: defines unified AI interface specification; all concrete AI implementations must inherit this class
class AI2JSON(ABC):
    @abstractmethod
    def ai(self) -> str:
        # Return AI identifier name, e.g., 'codex', 'claude'
        pass

    @abstractmethod
    def init(self, system_prompt: str, user_prompt: str, timeout: int = 0) -> tuple[list[str], str | None, int]:
        # Initialize CLI invocation parameters
        # Returns: CLI argument list, stdin prompt content (to bypass command-line character limits), final timeout value (seconds)
        # timeout=0: dynamically calculate based on content length (default per-KB budget + default base overhead)
        # timeout<0: use absolute value as per-KB budget (seconds), add default base overhead
        # timeout>0: directly use this value as final timeout
        pass

    @abstractmethod
    def exec(self, args: list[str], timeout: int, stdin_prompt: str | None = None) -> tuple[Any, str | None]:
        # Execute CLI and parse result
        # Returns: parsed JSON object (expected to be dict), error message (None on success)
        pass

    @staticmethod
    def create(ai: str, tmp: str | None = None) -> "AI2JSON":
        # Factory method: create concrete AI implementation via delayed imports to avoid circular dependencies
        # Supported AI: 'codex' or 'claude'
        from .ai2json import TheAI2JSON
        return TheAI2JSON.create(ai, tmp)