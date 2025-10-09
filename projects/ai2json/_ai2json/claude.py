#\/ ---------- Reviewed by: codex @ 2025-10-09 21:04:23
#\/ $lang: English
#\/ ---------- [Overview]
#\/ Claude2JSON builds a concrete adapter for invoking the Claude CLI from the shared TheAI2JSON base, discovering an executable, tuning permission flags according to platform/root status, and normalizing the CLI’s JSON result by stripping optional code fences before returning it upward.
#\/ ---------- [Review]
#\/ The adapter mirrors the Codex integration conventions, keeps permission-path logic straightforward, and feeds well-validated JSON strings back into the base extractor. The flow is cohesive and testable, though the code currently relies on the CLI emitting the expected `result` string contract. I did not uncover correctness regressions in this revision.
#\/ ---------- [Notes]
#\/ Permission-mode selection is deliberately asymmetric: only UID 0 switches to `acceptEdits`, all other environments rely on `--dangerously-skip-permissions` for reliability.
#\/ CLI discovery prioritizes running the packaged cli.js through node, which sidesteps Windows .cmd shims when Node remains on PATH.
#\/ ----------

import os
import json
import shutil
from pathlib import Path
from ..ai2json import TheAI2JSON

# Claude CLI integration adapter: builds command invocations with platform-aware permission modes
# and parses JSON responses from external Claude CLI subprocess execution
class Claude2JSON(TheAI2JSON):
    def ai(self) -> str:
        return "claude"

    def _get_args(self, system_prompt: str, user_prompt: str) -> tuple[list[str], str | None]:
        # Locate Claude executable, prefer node + cli.js direct invocation (avoids wrapper overhead),
        # fallback to claude binary, then bare string for PATH resolution
        claude_entry = shutil.which("claude")
        node_entry = shutil.which("node")
        args_prefix: list[str]
        if claude_entry and node_entry:
            # Assumes npm standard layout: claude binary's parent contains node_modules/
            candidate = Path(claude_entry).resolve().parent / "node_modules" / "@anthropic-ai" / "claude-code" / "cli.js"
            if candidate.exists():
                args_prefix = [node_entry, str(candidate)]
            else:
                args_prefix = [claude_entry]
        else:
            args_prefix = ["claude"]

        # --print: output to stdout; --output-format json: force JSON format;
        # --append-system-prompt: inject system prompt cleanly
        args = args_prefix + [
            "--print",
            "--output-format",
            "json",
            "--append-system-prompt",
            system_prompt,
        ]

        # Permission strategy (platform-dependent):
        # Linux/macOS root (UID=0): --dangerously-skip-permissions prohibited by CLI → use --permission-mode acceptEdits
        #   acceptEdits auto-grants Read/Glob/Grep/Bash/WebSearch/WebFetch/Write/Edit for pwd and subdirectories,
        #   but blocks parent dirs (../) and external paths (suitable for code review: pwd=/data/Codebase/python, projects in subdirs)
        # Windows/non-root: --dangerously-skip-permissions (most stable on Windows; other modes often fail)
        # Design: not using --allowed-tools (no wildcard support) or --add-dir (pwd already covers all project files)
        is_root = os.getuid() == 0 if hasattr(os, 'getuid') else False
        if is_root:
            args.extend(["--permission-mode", "acceptEdits"])
        else:
            args.append("--dangerously-skip-permissions")

        args.append("-")  # Read user prompt from stdin
        return args, user_prompt

    def _parse_stdout(self, stdout: str) -> tuple[str | None, str | None]:
        # Parse JSON dict from Claude CLI, extract 'result' field, strip optional fence markers
        try:
            data = json.loads(stdout)
        except json.JSONDecodeError:
            return None, "[ERR] _parse_stdout: can't parse JSON from stdout"

        if not isinstance(data, dict):
            return None, "[ERR] _parse_stdout: not a dictionary"

        result = data.get("result")
        if not isinstance(result, str):
            return None, "[ERR] _parse_stdout: string <result> not found"

        result = result.strip()
        if not result:
            return None, "[ERR] _parse_stdout: <result> is empty"

        # Strip ```json...``` fence if present (other fields like usage handled downstream)
        fenced = self._strip_fence(result)
        if fenced is not None:
            result = fenced
        return result, None