#\/ ---------- Reviewed by: codex @ 2025-10-24 15:31:07
#\/ $lang: English
#\/ ---------- [Overview]
#\/ Implements the fixer pass for previously reviewed files: decides whether a new fixing attempt is needed, invokes the fixer workflow, confirms a valid output, updates logs/context, and re-runs the reviewer with updated code until issues clear or retries exhaust.
#\/ ---------- [Review]
#\/ The guard and delayed logging address the prior fault; control flow for retries, logging, and context propagation now appears sound with no new correctness or reliability concerns detected.
#\/ ---------- [Notes]
#\/ Summary/context updates now occur only after confirming fixer output, preventing misleading success logs during retries.
#\/ ----------

import time
from typing import Any
from ..codeparser.index import Parser
from .architecture import Reviewer
from .reviewfile import TheReviewFile

class TheReviewFix(TheReviewFile):
    def _to_fix(self, review: str, src_path: str) -> bool:
        if '---------- [Issues]' not in review:  # Nothing to fix
            return False
        if '---------- [Impediments]' in review:  # Impediments found, cannot fix
            print(f"--- Impediments found in {src_path}:\n{review}\n")
            return False
        return True

    def review(self, reviewer: Reviewer, src_path: str, references: list[str], context = '', lang = '', timeout=0, retry = 1, tmp: str | None = None) -> str | None:
        parser = Parser.create_by_filename(src_path)
        request = self._load(parser, src_path, references, context)
        if request['input'] == '':
            return ''

        prior_review = request['prior_review']
        if '---------- [Review]' not in prior_review:  # Never reviewed before, review it first
            if not self._review(request, parser, reviewer, src_path, lang, timeout, 1, tmp):
                return None
            # Resubmit with any context produced by the initial review.
            return self.review(reviewer, src_path, references, request['context'], lang, timeout, retry, tmp)

        if not self._to_fix(prior_review, src_path):
            return prior_review

        # Initialize code fixer prompts and runtime parameters.
        args, stdin_prompt, timeout = reviewer.init("prompts/codefix.md", request, parser, lang, timeout)

        print(f"{retry} more {'tries' if retry > 1 else 'try'} to fix {src_path}...")
        t0 = time.time()
        # Invoke code fixer
        data, err = reviewer.exec(args=args, timeout=timeout, stdin_prompt=stdin_prompt)
        dt = time.time() - t0
        print(f"... Code fixed in {int(dt)}\" : {src_path}")
        if not data or err:
            if retry <= 1:
                return None
            # Preserve accumulated context between fix retries.
            return self.review(reviewer, src_path, references, request['context'], lang, timeout, retry - 1, tmp)

        summary = ''
        bug_fix = data.get('overview', '')
        discussion = data.get('review', '')
        if bug_fix != '':
            summary += f'[Bug fix]\n{bug_fix}\n'
        if discussion != '':
            summary += f'[Discussion]\n{discussion}\n'

        output = data.get('output')
        if output is None:
            # Retry when fixer omits output instead of crashing.
            if retry <= 1:
                return None
            return self.review(reviewer, src_path, references, request['context'], lang, timeout, retry - 1, tmp)

        # Only persist summary once we know we received an output to keep retries honest.
        log = self._log(src_path, tmp)
        if not log:
            print(f"---------- Code fixed:\n{summary}\n")
        else:
            with open(log, 'a', encoding='utf-8') as f:
                f.write(summary)

        request['context'] += '\n' + summary
        request['input'] = output  # Review the fixed code
        prior_review = self._review(request, parser, reviewer, src_path, lang, timeout, 1, tmp)
        if not prior_review:
            return None

        if retry <= 1 or not self._to_fix(prior_review, src_path):  # Stop here
            return prior_review

        # Retry with the expanded context from this pass.
        return self.review(reviewer, src_path, references, request['context'], lang, timeout, retry - 1, tmp)