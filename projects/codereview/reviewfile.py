#\/ ---------- Reviewed by: codex @ 2025-10-24 15:27:33
#\/ $lang: English
#\/ ---------- [Overview]
#\/ Implements the file review pipeline: loads source with prior annotations, delegates to the Reviewer with retry and AST validation, then reinjects requirements and review metadata while respecting language overrides.
#\/ ---------- [Review]
#\/ The adjustments correctly guard optional sections and ensure caller-provided language overrides flow through to the persisted header; overall logic stays consistent and testable with no regressions spotted.
#\/ ---------- [Notes]
#\/ Language preference now uses the explicit override end-to-end while falling back to stored metadata when absent.
#\/ ----------

import time
from typing import Any
from pathlib import Path
from ..codeparser.index import Parser
from .architecture import ReviewFile, Reviewer

class TheReviewFile(ReviewFile):
    def _load(self, parser: Parser, src_path: str, references: list[str], context: str) -> Any:
        # Build review request payload: compute relative path, read source, extract prior review comments, detect language preference.
        path = Path(src_path).resolve().parent.relative_to(Path.cwd())
        try:
            src_code = Path(src_path).resolve().read_text(encoding="utf-8")
        except Exception as e: # Source file must be in the current working directory
            raise ValueError(f"Failed to read source file {src_path}: {e}") from e

        # Extract review comments tagged with '\/' returning (comments, residual source).
        reviews, source = parser.extract_comments(src_code, '\\/')
        # Extract requirement comments tagged with '\%' returning (comments, residual source).
        requirements, source = parser.extract_comments(source, '\\%')

        # Parse $lang: directive from historical review comments, defaulting to English.
        comment_language = 'English'
        lang = '$lang:'
        for review in reviews:
            if(review.startswith(lang)):
                review = review[len(lang):].strip()
                if review != '':
                    comment_language = review.split(' ')[0]
                break

        return {
            'path': str(path), # Folder only
            'references': references,
            'comment_language': comment_language,
            'prior_review': '\n'.join(reviews),
            'requirements': '\n'.join(requirements),
            'context': context,
            'input': source.strip('\n'),
        }

    def _comment_section(self, comment: str, title: str) -> str:
        # Format a review section as '---------- [Title]\ncontent\n'.
        return f'---------- [{title}]\n{comment}\n'
    
    def _coment_text(self, data: Any, key: str) -> str:
        # Some reviewer outputs omit these sections; handle missing keys gracefully.
        text = data.get(key.lower())
        return '' if (not isinstance(text, str) or text == '') else self._comment_section(text, key)
    
    def _coment_list(self, data: Any, key: str) -> str:
        text = '\n'.join([s for s in data.get(key.lower(), []) if isinstance(s, str) and s.strip() != '']).strip()
        return '' if text == '' else self._comment_section(text, key)

    def _update(self, ai: str, lang: str, parser: Parser, src_path: str, data: Any, requirements: str) -> str:
        # Assemble the review header, prepend it (and requirements, if any), then persist updated annotations.
        txt = f"---------- Reviewed by: {ai} @ {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        txt += '$lang: ' + lang + '\n'
        txt += self._coment_text(data, 'Overview')
        txt += self._coment_text(data, 'Review')
        txt += self._coment_text(data, 'Design')
        txt += self._coment_list(data, 'Notes')
        txt += self._coment_list(data, 'Issues')
        txt += self._coment_list(data, 'Imperfections')
        txt += self._coment_list(data, 'Impediments')
        txt += '----------\n'

        # Trim source code, avoid duplication of review/requirement comments
        source = data['output'].strip('\n')
        _, source = parser.extract_comments(source, '\\/')
        _, source = parser.extract_comments(source, '\\%')

        if requirements != '': # If requirement comments exist, write them back at the top of the source.
            source = parser.insert_comment(source = source, line = 0, comment = requirements + '\n', tag = '\\%', block = False)

        # Insert the review comments at the top of the source.
        source = parser.insert_comment(source = source, line = 0, comment = txt, tag = '\\/', block = False)
        Path(src_path).resolve().write_text(source, encoding="utf-8")
        return txt

    def _error(self, i: int, path: str, data: Any, err: str | None, log: Path | None = None):
        # Log a failed review attempt to stderr and optionally to the retry log.
        print(f"[WARNING] Failed the {self._th(i)} time to review {path}: {err}")
        if log:
            with open(log, 'a', encoding='utf-8') as f:
                f.write(f"#{i}: {err}\n")
                if data and 'output' in data:
                    # Persist AI-modified output to help debug failures.
                    f.write("<<<\n")
                    f.write(data['output'] + '\n')
                    f.write(">>>\n")
    
    def _th(self, i: int) -> str:
        d = i % 10 if (i % 100) // 10 != 1 else 0 # Avoid teen ordinals (11th, 111th, etc.)
        th = 'st' if d == 1 else 'nd' if d == 2 else 'rd' if d == 3 else 'th'
        return f"{i}{th}"

    def _log(self, src_path: str, tmp: str | None = None) -> Path | None:
        # Determine error-log path when a temporary directory is provided.
        if tmp is None or tmp == '':
            return None
        else:
            fn = src_path.replace('\\', '/').split('/')[-1]
            log = Path(tmp).resolve() / f'{fn}.log'
            log.parent.mkdir(parents=True, exist_ok=True)
            return log

    def review(self, reviewer: Reviewer, src_path: str, references: list[str], context = '', lang = '', timeout=0, retry = 1, tmp: str | None = None) -> str | None:
        # Primary review flow: load source, invoke AI reviewer with retries, AST-verify, then write back annotations.
        parser = Parser.create_by_filename(src_path)
        request = self._load(parser, src_path, references, context)
        if request['input'] == '':
            return ''
        return self._review(request, parser, reviewer, src_path, lang, timeout, retry, tmp)

    def _review(self, request: Any, parser: Parser, reviewer: Reviewer, src_path: str, lang = '', timeout=0, retry = 1, tmp: str | None = None) -> str | None:
        # Parse the AST to validate later that AI output preserves logic.
        source = request['input']
        logic = parser.parse(source)

        override_lang = (lang or '').strip()
        runtime_lang = override_lang or request['comment_language']  # Explicit overrides take precedence over stored metadata.
        args, stdin_prompt, timeout = reviewer.init("prompts/codereview.md", request, parser, runtime_lang, timeout)
        ai = reviewer.ai()

        # Determine error-log path when a temporary directory is provided.
        log = self._log(src_path, tmp)

        # Pull requirement comments for reinsertion later when present.
        requirements = request['requirements']

        # Retry loop: attempt up to `retry` times, logging failures between attempts.
        for i in range(retry):
            # Compute ordinal suffix for human-friendly progress output.
            th = '' if retry <= 1 else f"for the {self._th(i+1)} time "
            print(f"Reviewing {src_path} {th}...")
            t0 = time.time()
            # Invoke reviewer and ensure AST validation holds before accepting output.
            data, err = reviewer.exec(args=args, timeout=timeout, stdin_prompt=stdin_prompt, parser=parser, expected=logic)
            dt = time.time() - t0
            print(f"... Reviewed in {int(dt)}\" : {src_path}")
            if data and not err:
                # Successful review with AST match; persist annotations.
                return self._update(ai, runtime_lang, parser, src_path, data, requirements)
            else:
                # Record the failure and continue retrying when allowed.
                self._error(i+1, src_path, data, err, log)
                if i < retry - 1:
                    print(f"Retrying...")
                    continue
                if data:
                    # Final retry failed on AST mismatch: discard AI edits but keep metadata.
                    print(f"Let's ignore the modified inline comments, just update the review metadata.")
                    data['output'] = source
                    return self._update(ai, runtime_lang, parser, src_path, data, requirements)

        return None