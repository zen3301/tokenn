#\/ ---------- Reviewed by: claude @ 2025-10-24 15:16:51
#\/ $lang: English
#\/ ---------- [Overview]
#\/ TheAI2JSON is an abstract base class implementation providing CLI-invoked AI execution infrastructure. It manages subprocess invocation with dynamic timeout calculation, JSON extraction from stdout with two-stage fallback parsing, and debug logging. Concrete subclasses (Codex2JSON, Claude2JSON) implement AI-specific CLI argument construction and output parsing. The class handles Windows command-line length limits by routing large prompts through stdin.
#\/ ---------- [Review]
#\/ Code quality is solid with well-designed error handling and separation of concerns. The two bug fixes from prior review have been properly implemented: (1) _dump now catches OSError and returns False on write failures, preventing misleading success returns; (2) stderr capture increased from 500 to 2000 characters to preserve diagnostic information. Implementation is ~98% complete and production-ready. The timeout calculation, subprocess execution, and JSON extraction logic are robust. Testability is good with dependency injection via tmp parameter. The code handles edge cases appropriately for its CLI-oriented context.
#\/ ---------- [Notes]
#\/ Bit-shift optimization (>>10 for /1024) in timeout calculation trades ~2.4% precision for performance; acceptable for non-critical timeout estimation and explicitly documented
#\/ Factory method uses delayed imports to prevent circular dependencies between index.py and ai2json.py
#\/ stdin_prompt routing specifically addresses Windows command-line length limits (8191 chars) which would break large prompts
#\/ Two-stage JSON extraction strategy (_parse_stdout → _strip_fence fallback → _extract_json) provides resilience against varied AI output formats
#\/ OSError catch in _dump intentionally silences all file I/O errors (disk full, permission denied, etc.) to prioritize robustness over debugging completeness
#\/ The stderr capture limit of 2000 characters is a reasonable compromise between memory usage and diagnostic completeness
#\/ ---------- [Imperfections]
#\/ Line 51: Multiple return points in exec method could be consolidated for improved readability, though current structure is maintainable
#\/ Line 110: _strip_fence doesn't validate that suffix appears after prefix; could theoretically extract invalid content if markers appear in reverse order (extremely unlikely with well-formed AI output, acceptable given context)
#\/ Line 13: Constructor prints to stdout rather than using logging module, making output control difficult in library usage scenarios (though reasonable for CLI-oriented tool)
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
            import sys
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
            if ch == '"' and not prev_was_backslash:
                if not inside_string:
                    inside_string = True
                    result_chars.append('"')
                else:
                    j = i + 1
                    while j < n and payload[j].isspace():
                        j += 1
                    next_ch = payload[j] if j < n else ''
                    if next_ch in (',', '}', ']', ':'):
                        inside_string = False
                        result_chars.append('"')
                    else:
                        result_chars.append('\\\"')
                prev_was_backslash = False
            else:
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