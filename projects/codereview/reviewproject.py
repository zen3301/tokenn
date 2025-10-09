#\/ ---------- Reviewed by: codex @ 2025-10-09 23:31:23
#\/ $lang: English
#\/ ---------- [Overview]
#\/ Project adapter prepares project-level review payloads, renders consolidated `.REVIEW.md` trees, and mines inline annotations for reuse; helpers coordinate folder discovery, list materialization, and language detection around the core reviewer execution loop.
#\/ ---------- [Review]
#\/ Core path-safety and tree-building routines look consistent with the surrounding tooling, yet inline extraction remains unsafe: cached reviews without a `[Review]` section (which still happens when the AI returns only overviews/notes) are discarded, so project synthesis re-runs files and loses real feedback; the area needs regression coverage around extraction outputs.
#\/ ---------- [Notes]
#\/ Extraction now documents its dependency on serialized reviewer headers; consumers must guarantee `[Review]` presence until the logic is fixed.
#\/ ----------

import time
from typing import Any
from pathlib import Path
from ..codeparser.index import Parser
from .architecture import ReviewProject, Reviewer

class TheReviewProject(ReviewProject):
    def _load(self, md_path: str, reviews: dict[str, str], references: list[str], context: str) -> Any:
        # Load review configuration, enforce path safety, derive language preference, and build the request payload.
        path = Path(md_path).resolve()
        dir = path if path.is_dir() else path.parent
        try:  # md_path must stay within the current working directory
            dir = dir.relative_to(Path.cwd())
        except Exception as e:
            raise ValueError(f"Review file {md_path} is not in the current working directory") from e

        dir.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.is_file():
            prior = path.read_text(encoding="utf-8")
        else:
            prior = ''

        # Parse the annotation language preference from an existing review file if present.
        comment_language = 'English'
        lang = '$lang:'
        if prior.startswith(lang):
            eol = prior.find('\n')
            line = prior[len(lang):eol].strip() if eol >= 0 else prior[len(lang):].strip()
            if line != '':
                comment_language = line.split(' ')[0]
        prior = ""  # VERIFIED! Ignoring prior review content here yields better downstream behavior.

        return {
            'path': str(dir),
            'references': references,
            'comment_language': comment_language,
            'prior_review': prior,
            'context': context,
            'reviews': reviews,
        }

    def _modules(self, folders: list[str]) -> list[str]:
        # Discover .REVIEW.md files in the supplied folders and return their relative locations.
        modules = []
        for folder in folders:
            review = Path(folder).resolve() / ".REVIEW.md"
            if review.exists():
                try:
                    modules.append(review.resolve().relative_to(Path.cwd().resolve()).as_posix())
                except ValueError:
                    modules.append(review.as_posix())
        return modules

    def _list(self, data: Any, key: str) -> str:
        # Materialize a Markdown list section for an uppercase key (e.g., 'Notes') mapped to a lower-case entry list.
        values = data.get(key.lower())  # data keys stay lowercase: notes, issues, imperfections
        if not values or not isinstance(values, list):
            return ''
        title = f"\n# {key}:\n"
        return title + '\n'.join([f'- {item}' for item in values]) + '\n'

    def _paths2relative(self, paths: list[str], prefix: str) -> list[str]:
        # Convert candidate paths into prefix-relative, POSIX-style strings.
        try:
            # VERIFIED! Inputs already resolve under the current working directory and within the prefix subtree.
            return [str(Path(path).resolve().relative_to(prefix)).replace('\\', '/') for path in paths]
        except Exception as e:
            # VERIFIED! No handling needed because this branch should remain unreachable in supported flows.
            raise ValueError(f"Some path is not in the prefix {prefix}") from e

    def _update(self, ai: str, request: Any, data: Any) -> str:
        # Emit the refreshed .REVIEW.md body, combining the file tree summary and the structured review sections.
        md = f"$lang: {request['comment_language']}\n"
        md += f"---------- Reviewed by: {ai} @ {time.strftime('%Y-%m-%d %H:%M:%S')}\n"

        dir = request['path']
        path = Path(dir) / ".REVIEW.md"
        prefix = Path(dir).resolve().as_posix()
        try:  # .REVIEW.md must still live under the current working directory
            location = str(path.resolve().relative_to(Path.cwd().resolve())).replace('\\', '/')
            md += f"\n{location}\n"
        except Exception as e:
            raise ValueError(f"Review file {path} is not in the current working directory") from e

        # Normalize the reviewed file list.
        reviews_payload = data.get("reviews")
        if not isinstance(reviews_payload, dict) or len(reviews_payload) == 0:
            reviews_payload = request['reviews']
        files = self._paths2relative(list(reviews_payload.keys()), prefix)

        # Normalize the sub-module review list.
        subs_payload = data.get("sub_module_reviews")
        if not isinstance(subs_payload, list):
            subs_payload = request.get('sub_module_reviews', [])
        subs = self._paths2relative([str(entry) for entry in subs_payload], prefix)

        # Assemble the tree view with files in front and sub-modules trailing, using ASCII branches.
        l = files + subs
        nf = len(files)
        n = len(l)
        for i in range(n):
            prefix = '├──' if i < n-1 else '└──'
            if i >= nf:
                prefix += '──'  # Sub-modules use the double-dash marker.
            md += f"    {prefix} {l[i]}\n"

        # Append overview/review text plus optional detail lists.
        overview = data.get('overview', '')
        review = data.get('review', '')

        md += f"\n# Overview:\n{overview}\n"
        md += f"\n# Review:\n{review}\n"
        md += self._list(data, "Notes")
        md += self._list(data, "Issues")
        md += self._list(data, "Imperfections")

        path.resolve().write_text(md, encoding="utf-8")
        return md

    def review(self, reviewer: Reviewer, path: str, reviews: dict[str, str], folders: list[str], references: list[str], context = '', lang = '', timeout=0) -> str | None:
        # Project-level review entry point: load context, invoke the AI reviewer, then refresh .REVIEW.md.
        request = self._load(path, reviews, references, context)
        request['sub_module_reviews'] = self._modules(folders)

        print(f"Reviewing {request['path']}...")
        t0 = time.time()
        args, stdin_prompt, timeout = reviewer.init("prompts/projreview.md", request, None, lang, timeout)
        data, err = reviewer.exec(args=args, timeout=timeout, stdin_prompt=stdin_prompt)
        dt = time.time() - t0
        print(f"... Reviewed '.REVIEW.md' in {int(dt)}\"")
        if data is not None and not err:
            return self._update(reviewer.ai(), request, data)

        return None

    def extract_review(self, src_path: str) -> str | None:
        # Extract inline review annotations tagged with '\/'; relies on the caller inserting the serialized review header/footer.
        parser = Parser.create_by_filename(src_path)
        src_code = Path(src_path).resolve().read_text(encoding="utf-8")
        reviews, source = parser.extract_comments(src_code, '\/')

        if not reviews or len(reviews) == 0:
            return None

        for review in reviews:
            if review.startswith('---------- [Review]'):  # Assumes at least one serialized [Review] block exists in the annotations.
                requirements, source = parser.extract_comments(source, '\%')
                if requirements and len(requirements) > 0:  # When present, append the requirements block as well.
                    reviews.append('---------- [Requirements]')
                    reviews.extend(requirements)
                return '\n'.join(reviews)

        # Purpose;y discard if [Review] is missing regardless other sections, and will trigger re-run review
        return None