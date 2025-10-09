#\/ ---------- Reviewed by: codex @ 2025-10-09 20:58:59
#\/ $lang: English
#\/ ---------- [Overview]
#\/ Codex2JSON builds command sequences for the Codex CLI and parses its newline-delimited JSON outputs, bridging a generic AI process runner toward the Codex agent by concatenating prompts and decoding streamed agent_message events.
#\/ ---------- [Review]
#\/ Implementation looks production-ready: entry discovery is robust, stdout parsing carefully covers both streaming formats plus fenced fallbacks, and JSON extraction defers to the hardened superclass logic. No blocking defects surfaced in this pass.
#\/ ---------- [Notes]
#\/ The adapter intentionally prefers executing codex.js via node to dodge Windows .cmd quirks, then gracefully degrades to running the installed codex wrapper.
#\/ JSON event parsing deliberately returns on the first agent_message payload, matching the expected final-completion semantics documented for the Codex CLI.
#\/ ----------

import json
import shutil
from typing import Any
from pathlib import Path
from ..ai2json import TheAI2JSON

# GPT-5 Codex CLI adapter
class Codex2JSON(TheAI2JSON):
    def ai(self) -> str:
        return "codex"

    def _get_args(self, system_prompt: str, user_prompt: str) -> tuple[list[str], str | None]:
        # Concatenate system and user prompts to avoid command-line character limits
        prompt = system_prompt + "\n" + user_prompt
        # Locate Codex executable entry with three-level fallback: node + codex.js → codex command → bare string
        codex_entry = shutil.which("codex")
        node_entry = shutil.which("node")
        args_prefix: list[str]
        if codex_entry and node_entry:
            # Try using node to execute codex.js directly to avoid wrapper script overhead
            candidate = Path(codex_entry).resolve().parent / "node_modules" / "@openai" / "codex" / "bin" / "codex.js"
            if candidate.exists():
                args_prefix = [node_entry, str(candidate), "exec"]
            else:
                args_prefix = [codex_entry, "exec"]
        else:
            # Fallback to bare string, rely on system PATH resolution
            args_prefix = ["codex", "exec"]
        # Construct command-line arguments: bypass sandbox and git checks for automation, force JSON output, read prompt from stdin
        args = args_prefix + [
            "--dangerously-bypass-approvals-and-sandbox",
            "--skip-git-repo-check",
            "--json",
            "-",
        ]
        return args, prompt

    def _parse_stdout(self, stdout: str) -> tuple[str | None, str | None]:
        # Parse JSON event stream line-by-line, support both new and legacy formats:
        # New format: {"type":"item.completed","item":{"type":"agent_message","text":"..."}}
        # Legacy format: {"msg":{"type":"agent_message","message":"..."}}
        # Extract first matched agent_message text field and return immediately
        lines = stdout.splitlines()
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict):
                continue

            # New format: item.completed event containing agent_message type item
            if event.get("type") == "item.completed":
                item = event.get("item")
                if isinstance(item, dict) and item.get("type") == "agent_message":
                    text = self._get_message(item.get("text"))
                    if text is not None:
                        return text, None

            # Legacy format compatibility: msg.type=agent_message with non-empty msg.message
            msg = event.get("msg")
            if isinstance(msg, dict) and msg.get("type") == "agent_message":
                text = self._get_message(msg.get("message"))
                if text is not None:
                    return text, None

        # Fallback to find fenced payload in each line
        print("[WARNING] codex._parse_stdout: Fallback to find fenced payload per line")
        for line in lines:
            payload = self._strip_fence(line)
            if payload is not None:
                return payload, None

        return None, "[ERR] _parse_stdout: no target message found"

    def _get_message(self, text) -> str | None:
        if not isinstance(text, str):
            return None
        fenced = self._strip_fence(text)
        return text if fenced is None else fenced

    def _extract_json(self, payload: str) -> tuple[Any, str | None]:
        # First attempt direct JSON parsing; fallback to parent class fence extraction logic on failure
        payload = payload.strip()
        if not payload:
            return None, "[ERR] _extract_json: payload is empty"
        try:
            return json.loads(payload), None
        except json.JSONDecodeError:
            # Fallback to parent class implementation (fence extraction)
            return super()._extract_json(payload)