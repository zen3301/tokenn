#\/ ---------- Reviewed by: claude @ 2025-10-27 16:09:31
#\/ $lang: English
#\/ ---------- [Overview]
#\/ TheAI2JSON is a base implementation of the AI2JSON interface that orchestrates CLI-based AI invocations via subprocess. It handles timeout calculation, stdin/stdout routing, JSON extraction with fence marker parsing, and debug output dumping. Concrete AI providers (Codex, Claude) inherit this class and implement provider-specific argument construction and stdout parsing.
#\/ ---------- [Review]
#\/ The code is functionally complete and demonstrates solid engineering: proper abstraction, robust JSON extraction with fallback mechanisms, and defensive error handling. The timeout calculation via bit-shift approximation is clever and acceptable. The _fix_json heuristic for repairing malformed JSON is a pragmatic workaround for AI output variability. Code quality is high with clear separation of concerns. Completion: ~95%. Testability is good due to modular methods. Minor imperfections in documentation and edge case handling exist but do not block functionality.
#\/ ---------- [Notes]
#\/ ASSUMPTION: Callers must ensure system_prompt and user_prompt are non-empty when timeout=0 or timeout<0, otherwise timeout calculation may produce incorrect results (zero or near-zero timeout).
#\/ ASSUMPTION: Subclasses (Codex2JSON, Claude2JSON) must implement _get_args to return valid CLI arguments and _parse_stdout to extract AI response; invalid implementations will cause exec to fail.
#\/ ASSUMPTION: The tmp directory (if provided) must exist and be writable; _dump silently ignores failures to prioritize robustness.
#\/ The _fix_json method uses a heuristic to repair common JSON escaping issues in AI-generated output; it may not handle all malformed JSON cases but is a best-effort approach.
#\/ Bit-shift timeout approximation (>> 10 for KB) introduces ~2.4% error, which is acceptable for timeout estimation purposes.
#\/ ---------- [Imperfections]
#\/ _strip_fence uses find/rfind which may fail if multiple fenced blocks exist; consider using the first complete block instead of first prefix + last suffix.
#\/ _extract_json assumes single JSON object by finding first { and last }; nested or multiple objects in payload could cause incorrect extraction.
#\/ The factory method create raises ValueError for unsupported AI types but does not provide a list of valid options in the error message (though it's in a comment).
#\/ _fix_json debug output prints to stdout instead of using _dump; consider consistent debug output routing.
#\/ No validation that timeout remains positive after calculation; extremely short prompts with custom per-KB budget could theoretically produce negative or zero timeout.
#\/ ----------

import json
import subprocess
from typing import Any
from pathlib import Path
from abc import abstractmethod
from projects.ai2json.index import AI2JSON

# Base class for CLI-invoked AI reviewers; concrete implementations (Codex, Claude) are in ./ai/
class TheAI2JSON(AI2JSON):
    def __init__(self, tmp: str | None = None):
        if tmp is None:
            self.tmp = None
        else:
            self.tmp = Path(tmp)
            print(f"TheAI2JSON: tmp = {self.tmp}")

    # ASSUMPTION: Callers must provide non-empty prompts when timeout<=0 to ensure valid timeout calculation
    def init(self, system_prompt: str, user_prompt: str, timeout: int = 0) -> tuple[list[str], str | None, int]:
        # Returns CLI argument list, stdin prompt content, and final timeout value
        # timeout=0: dynamically calculate based on content length (default per-KB budget + default base overhead)
        # timeout<0: use absolute value as per-KB budget (seconds), add default base overhead
        # timeout>0: use this value directly as final timeout
        if timeout <= 0:
            timeout = self._perKB() if timeout == 0 else - timeout
            # Bit shift by 10 approximates division by 1024 for KB calculation (~2.4% error, acceptable for timeout estimation)
            timeout *= len(system_prompt + user_prompt) >> 10
            timeout += self._timeout()  # Add base startup and cleanup overhead

        # stdin_prompt routing avoids Windows command-line length limits (8191 chars)
        args, stdin_prompt = self._get_args(system_prompt, user_prompt)
        return args, stdin_prompt, timeout

    def exec(self, args: list[str], timeout: int, stdin_prompt: str | None = None) -> tuple[Any, str | None]:
        # Execute subprocess, return parsed JSON object and error message (if failed)
        try:
            # VERIFIED! This works on Windows
            completed = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=timeout,
                input=stdin_prompt,
            )
            if completed.returncode != 0:
                # Capture first 2000 chars of stderr to preserve diagnostic information
                stderr_msg = completed.stderr[:2000] if completed.stderr else "no stderr"
                return None, f"[ERR] subprocess.run: returncode={completed.returncode}, stderr: {stderr_msg}"

            self._dump('stdout.txt', completed.stdout)

            # Two-stage JSON extraction for resilience against varied AI output formats:
            # Primary: subclass-specific parser → Fallback: direct fenced JSON extraction
            payload, err = self._parse_stdout(completed.stdout)
            if payload is None: # Fallback: extract fenced JSON directly from stdout, then parse
                print("[WARNING] exec: Fallback to find fenced payload")
                payload = self._strip_fence(completed.stdout)
                if payload is None:
                    return None, err

            data, err = self._extract_json(payload)
            if data is None:
                return None, err

            return data, None
        except subprocess.TimeoutExpired as e:
            return None, f"[ERR] subprocess.TimeoutExpired: {e}"
        except Exception as e:
            return None, f"[ERR] subprocess.Exception: {e}"

    def _dump(self, fn: str, text: str) -> bool:
        # Write debug output to tmp directory if configured; return False on any failure
        # NOTE: Silently ignores I/O errors (disk full, permission denied) to prioritize robustness
        if not self.tmp:
            return False
        fn = f"{self.ai()}.{fn}"
        try:
            with open(self.tmp / fn, 'w', encoding='utf-8') as f:
                f.write(text)
            return True
        except OSError:
            # Silently ignore file I/O errors (disk full, permission denied, etc.) to prioritize robustness
            return False

    @abstractmethod
    def _get_args(self, system_prompt: str, user_prompt: str) -> tuple[list[str], str | None]:
        # Subclass implementation: return CLI argument list with user prompt passed via stdin to avoid command-line length limits
        pass

    @abstractmethod
    def _parse_stdout(self, stdout: str) -> tuple[str | None, str | None]:
        # Subclass implementation: extract AI response string and error message (if any) from CLI output
        pass

    def _fence_prefix(self) -> str:
        return '```json'

    def _fence_suffix(self) -> str:
        return '```'

    def _strip_fence(self, payload: str) -> str | None:
        # Extract content between fence markers (e.g., ```json ... ```); does not parse JSON
        # NOTE: Uses first prefix and last suffix; may produce incorrect results if multiple fenced blocks exist
        if not payload:
            return None

        prefix = self._fence_prefix()
        suffix = self._fence_suffix()
        i = payload.find(prefix)
        if i < 0:
            return None
        payload = payload[i + len(prefix):]
        i = payload.rfind(suffix)
        if i < 0:
            return None
        return payload[:i]

    def _extract_json(self, payload: str) -> tuple[Any, str | None]:
        # Extract single JSON object dictionary from potentially fenced text
        # NOTE: Assumes single object by finding first { and last }; nested/multiple objects may cause incorrect extraction
        if not payload:
            return None, "[ERR] _extract_json: payload is empty"

        # Locate first { and last } to extract JSON object (assumes well-formed AI output)
        i = payload.find("{")
        if i < 0:
            self._dump('payload.txt', payload)
            return None, "[ERR] _extract_json: can't find { in payload"
        payload = payload[i:]
        i = payload.rfind("}")
        if i < 0:
            self._dump('payload.txt', payload)
            return None, "[ERR] _extract_json: can't find } in payload"
        payload = payload[:i+1]

        # Parse and validate as dictionary type
        data = self._fix_json(payload)
        if data is None:
            return None, "[ERR] _extract_json: can't parse JSON"
        if not isinstance(data, dict):
            return None, "[ERR] _extract_json: not a dictionary"
        return data, None
    
    def _fix_json(self, payload: str) -> Any | None:
        # Best-effort heuristic to repair common JSON escaping issues in AI-generated output; not a perfect solution
        # Fast path: if it's already valid JSON, return as-is
        try:
            return json.loads(payload)
        except Exception:
            pass

        n = len(payload)
        i = 0
        inside_string = False
        prev_was_backslash = False
        result_chars: list[str] = []

        while i < n:
            ch = payload[i]
            if ch == '"' and not prev_was_backslash: # an unescaped '"'
                if not inside_string: # about to start a string
                    inside_string = True
                    result_chars.append('"')
                else:
                    j = i + 1
                    while j < n and payload[j].isspace(): # skip whitespace after the '"'
                        j += 1
                    next_ch = payload[j] if j < n else ''
                    if next_ch in (':', ',', ']', '}'): # JSON structural characters: ':' or ',' or ']' or '}'
                        inside_string = False # consider as possible correct ending of a string
                        result_chars.append('"')
                    else:
                        result_chars.append('\\\"') # consider as missing escape '\'
                prev_was_backslash = False
            else: # regular character or escaped '\"'
                result_chars.append(ch)
                if ch == '\\' and not prev_was_backslash:
                    prev_was_backslash = True
                else:
                    prev_was_backslash = False
            i += 1

        fixed = ''.join(result_chars)
        try:
            return json.loads(fixed)
        except Exception:
            print(f"---------- Invalid JSON:\n{payload}\n---------- Fixed to:\n{fixed}\n----------")
            return None

    def _timeout(self) -> int:
        # Base preparation time budget: 5 minutes for CLI startup, network latency, cleanup
        return 300

    def _perKB(self) -> int:
        # Processing time budget per KB of prompt content
        return 60

    @staticmethod
    def create(ai: str, tmp: str | None = None) -> AI2JSON:
        # Factory method: create concrete AI implementation via delayed imports to avoid circular dependencies
        # Supported AI: 'codex' or 'claude'
        if ai == 'codex':
            from ._ai2json.codex import Codex2JSON
            return Codex2JSON(tmp)
        elif ai == 'claude':
            from ._ai2json.claude import Claude2JSON
            return Claude2JSON(tmp)
        else:
            raise ValueError(f"Unsupported AI [codex, claude]: {ai}")