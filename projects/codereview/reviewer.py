#\/ ---------- Reviewed by: codex @ 2025-10-24 15:22:44
#\/ $lang: English
#\/ ---------- [Overview]
#\/ TheReviewer orchestrates CLI interactions by loading system prompts, serializing requests, and validating the AI JSON reply before passing it back to callers. It also enforces optional AST equivalence when a parser is provided, ensuring downstream review workflows can trust the structured payload.
#\/ ---------- [Review]
#\/ Implementation appears production-ready: prompt assembly handles defaults, CLI response validation guards required fields, and AST comparison reports mismatches while returning data for retries. Behavior aligns with surrounding pipeline expectations, and code remains testable via injection of Parser and AI2JSON adapters.
#\/ ---------- [Notes]
#\/ AST validation returns both the structured payload and the mismatch error, enabling callers to reuse metadata while discarding unsafe edits.
#\/ ----------

import json
from typing import Any
from pathlib import Path
from ..codeparser.index import Parser
from ..ai2json.index import AI2JSON
from .architecture import Reviewer

class TheReviewer(Reviewer):
    def __init__(self, ai: str, tmp: str | None = None):
        self.cli = AI2JSON.create(ai, tmp)
    
    def ai(self) -> str:
        return self.cli.ai()

    def init(self, system_md: str, request: Any, parser: Parser | None = None, lang = '', timeout = 0) -> tuple[list[str], str | None, int]:
        # Prefer the caller-specified annotation language; otherwise fall back to the request default.
        if not lang or lang == '':
            lang = request['comment_language']
        else:
            request['comment_language'] = lang
        user_prompt = json.dumps(request, indent=2, ensure_ascii=False)

        # Load the system prompt template and substitute placeholders.
        path = Path(__file__).resolve().parent
        system_path = path / system_md
        system_prompt = system_path.read_text(encoding="utf-8")
        system_prompt = system_prompt.replace('`comment_language`', lang)
        if parser:
            system_prompt = system_prompt.replace('`programming_language`', parser.language())

        return self.cli.init(system_prompt, user_prompt, timeout)

    def exec(
        self,
        args: list[str],
        timeout: int,
        stdin_prompt: str | None = None,
        parser: Parser | None = None,
        expected: str | None = None,
    ) -> tuple[Any, str | None]:
        # Run the AI review and validate its structured response.
        data, err = self.cli.exec(args, timeout, stdin_prompt)
        if data is None or err:
            return None, err
        return self._data_check(data, parser, expected)

    def _data_check(self, data: Any, parser: Parser | None = None, expected: str | None = None) -> tuple[Any, str | None]:
        # Ensure the payload is a dictionary before inspecting fields.
        if not isinstance(data, dict):
            return None, f"[ERR] _data_check: <data> must be a dictionary"

        # Surface AI-side execution failures immediately.
        if data.get("error") and data['error'].strip() != "":
            return None, f"[ERR] _data_check: <error> = {data['error']}"

        # Require the minimal mandatory fields from the AI payload.
        required = ["overview", "review"]
        if not all(k in data for k in required):
            return None, f"[ERR] _data_check: required keys not found"

        # Normalize optional list fields for downstream consumers.
        if not data.get("notes"):
            data["notes"] = []
        elif not isinstance(data.get("notes"), list):
            return None, f"[ERR] _data_check: <notes> must be a string list"

        if not data.get("issues"):
            data["issues"] = []
        elif not isinstance(data.get("issues"), list):
            return None, f"[ERR] _data_check: <issues> must be a string list"

        if not data.get("imperfections"):
            data["imperfections"] = []
        elif not isinstance(data.get("imperfections"), list):
            return None, f"[ERR] _data_check: <imperfections> must be a string list"

        if not data.get("impediments"):
            data["impediments"] = []
        elif not isinstance(data.get("impediments"), list):
            return None, f"[ERR] _data_check: <impediments> must be a string list"

        # When a parser is provided, enforce output typing and optionally compare ASTs.
        if parser is not None:
            if not isinstance(data.get("output"), str):
                return None, f"[ERR] _data_check: <output> must be a string"

            if expected is not None:
                try:
                    # Check output AST json string against 'expected' which is AST json string from input source code
                    ast_output = parser.parse(data["output"])
                    if ast_output != expected:
                        # SPEC: Return data with AST mismatch, let caller to decide what to do
                        return data, f"[WARNING] _data_check: <output> does not match the input expected"
                except Exception as e:
                    return None, f"[ERR] _data_check: <output> parsing failed: {e}"

        # All validations passed.
        return data, None