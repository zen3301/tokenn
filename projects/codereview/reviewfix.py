#\/ ---------- Reviewed by: codex @ 2025-10-23 19:34:04
#\/ $lang: English
#\/ ---------- [Overview]
#\/ The module orchestrates an iterative fix-and-review loop: it loads the target source, triggers the reviewer to evaluate it, invokes a fixer prompt when issues remain, and repeats until the retry budget is exhausted or the code passes review.
#\/ ---------- [Review]
#\/ The updated retry flow correctly continues past fixer execution failures and threads the accumulated context through subsequent reviews; overall structure remains coherent and testable with no new correctness or safety risks observed within the provided scope.
#\/ ---------- [Notes]
#\/ Recursive retries re-read fresh parser state and reuse the growing context string so later prompts see the latest summaries.
#\/ ----------

import time
from typing import Any
from ..codeparser.index import Parser
from .architecture import Reviewer
from .reviewfile import TheReviewFile

class TheReviewFix(TheReviewFile):
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

        if '---------- [Issues]' not in prior_review:  # Nothing to fix
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

        # Determine error-log path when a temporary directory is provided.
        log = self._log(src_path, tmp)
        if not log:
            print(f"---------- Code fixed:\n{summary}\n")
        else:
            with open(log, 'a', encoding='utf-8') as f:
                f.write(summary)

        request['context'] += '\n' + summary
        request['input'] = data['output'] # Review the fixed code
        prior_review = self._review(request, parser, reviewer, src_path, lang, timeout, 1, tmp)
        if not prior_review:
            return None

        if retry <= 1 or '---------- [Issues]' not in prior_review:  # Stop here
            return prior_review

        # Retry with the expanded context from this pass.
        return self.review(reviewer, src_path, references, request['context'], lang, timeout, retry - 1, tmp)