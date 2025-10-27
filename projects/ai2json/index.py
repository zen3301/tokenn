#\/ ---------- Reviewed by: claude @ 2025-10-27 16:10:02
#\/ $lang: English
#\/ ---------- [Overview]
#\/ AI2JSON is an abstract base class defining a unified interface for AI providers that generate JSON output via CLI subprocess invocation. It specifies three abstract methods (ai, init, exec) and provides a static factory method for instantiating concrete implementations (Codex, Claude). This serves as the top-level API contract for the ai2json system.
#\/ ---------- [Review]
#\/ The code is well-designed as a clean interface specification with proper abstraction boundaries. The docstrings are clear and comprehensive, explaining parameter semantics (especially timeout modes), return types, and design rationale (e.g., stdin routing for command-line length limits). The factory method pattern with delayed imports avoids circular dependencies. Code quality is high. Completion: 100%. Testability: excellent due to clear contracts. No functional defects identified.
#\/ ---------- [Notes]
#\/ ASSUMPTION: Callers must provide valid AI provider identifiers ('codex', 'claude') to the factory method; invalid values will raise ValueError from TheAI2JSON.create.
#\/ ASSUMPTION: Concrete implementations must honor the timeout semantics documented in init: timeout=0 triggers dynamic calculation, timeout<0 uses absolute value as per-KB budget, timeout>0 uses the value directly.
#\/ ASSUMPTION: The exec method contract expects a dict as the primary return value; callers should validate the type after receiving a non-None result.
#\/ The factory method uses delayed imports (from .ai2json import TheAI2JSON) to avoid circular dependencies between index.py and ai2json.py; this is a deliberate design choice.
#\/ ---------- [Imperfections]
#\/ The ai() abstract method lacks documentation on whether it should return a constant or a computed value; consider clarifying that it's expected to be a constant identifier.
#\/ The create factory method comment mentions 'etc.' for supported AI providers but the actual implementation (in TheAI2JSON) only supports 'codex' and 'claude'; consider either removing 'etc.' or making the list exhaustive.
#\/ The exec method's first return value is typed as 'Any' but the comment specifies '(expected to be dict)'; consider using 'dict[str, Any] | None' for stronger type safety, or at minimum document why the weaker type is necessary.
#\/ ----------

from typing import Any
from abc import ABC, abstractmethod

# AI2JSON abstract base class: defines unified AI interface specification; all concrete AI implementations must inherit this class
class AI2JSON(ABC):
    @abstractmethod
    def ai(self) -> str:
        # Return AI provider identifier name (constant), e.g., 'codex', 'claude'
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
        # ai: AI provider identifier; supported values: 'codex', 'claude'
        # tmp: optional temporary directory path for debug output
        from .ai2json import TheAI2JSON
        return TheAI2JSON.create(ai, tmp)