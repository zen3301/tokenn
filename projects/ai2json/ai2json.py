#\/ ---------- Reviewed by: codex @ 2025-10-09 21:16:22
#\/ $lang: English
#\/ ---------- [Overview]
#\/ Shared AI2JSON runner calculates prompt-sensitive timeouts, executes an AI CLI subprocess, and extracts fenced JSON payloads, with adapters providing CLI-specific argument and stdout parsing helpers.
#\/ ---------- [Review]
#\/ Latest change corrects the fallback flow by ensuring recovered fenced payloads are parsed instead of being discarded; overall the module remains small, cohesive, and sufficiently defensive for production use.
#\/ ---------- [Notes]
#\/ Fallback path now properly parses fenced stdout instead of short-circuiting, protecting adapters from structured stream regressions.
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
            # Bit shift by 10 approximates division by 1024 for KB calculation (~2.4% error vs /1000)
            timeout *= len(system_prompt + user_prompt) >> 10
            timeout += self._timeout()  # Add base startup and cleanup overhead

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
                stderr_msg = completed.stderr[:500] if completed.stderr else "no stderr"
                return None, f"[ERR] subprocess.run: returncode={completed.returncode}, stderr: {stderr_msg}"

            self._dump('stdout.txt', completed.stdout)

            payload, err = self._parse_stdout(completed.stdout)
            if payload is None: # Fallback to find fenced payload in stdout
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
        if not self.tmp:
            return False
        fn = f"{self.ai()}.{fn}"
        with open(self.tmp / fn, 'w', encoding='utf-8') as f:
            f.write(text)
        return True

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
        # Do not parse json here, leave it to _extract_json()
        if not payload:
            return None

        # Strip fence prefix/suffix (e.g. ```json ... ```)
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

        # Locate first { and last } to extract JSON string
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
        try:
            data = json.loads(payload)
            if not isinstance(data, dict):
                return None, "[ERR] _extract_json: not a dictionary"
            return data, None
        except json.JSONDecodeError:
            return None, "[ERR] _extract_json: can't parse JSON"

    def _timeout(self) -> int:
        # Base preparation time budget, default 5 minutes (CLI startup, network latency, cleanup)
        return 300

    def _perKB(self) -> int:
        # Processing time budget per KB of prompt content, default 60 seconds
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