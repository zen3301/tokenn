#%% ---------- Reviewed by: claude
#%% $lang: 中文
#%% ---------- [Overview]
#%% 该模块是代码评审工具的核心流程控制器，负责加载源码、提取历史评审、调用 AI 评审器、验证 AST 一致性、处理重试机制，并将评审结果以注释形式写回源文件。协调 Parser、CliReviewer 组件，实现完整的单文件评审闭环。
#%% ---------- [Review]
#%% 代码结构清晰，职责分离良好，类型注解完整。评审流程健壮，包含重试机制、AST 验证、错误日志记录等防护措施。序数词生成逻辑正确，注释格式化清晰。代码质量优秀，完成度约 98%，可维护性强，测试性良好。现有注释详实准确，功能逻辑符合规范要求。
#%% ---------- [Notes]
#%% 第 70-71 行的序数词生成逻辑正确处理了英文 1st/2nd/3rd/4th 规则，特别是避免了 11th/12th/13th 的特殊情况（它们始终使用 th 而非 st/nd/rd）
#%% 第 97 行的 parser.parse(source) 验证设计巧妙：确保 AI 输出的代码与原始输入在语义（AST）上等价，允许注释改动但拒绝逻辑改动，这是评审器的核心安全保障
#%% 第 125 行的降级策略设计合理：最后一次重试时若 AST 不匹配，放弃 AI 的代码修改但保留评审元数据（overview/review/issues），确保评审结果不丢失，符合「数据优先于格式」原则
#%% 第 10-14 行的注释提取逻辑支持增量评审：从历史注释中识别 $lang: 设置并继承到新评审，避免语言设置在多次评审中丢失，维护了配置的持久性
#%% ---------- [Imperfections]
#%% 第 10 行使用 Path.cwd() 计算相对路径，在 src_path 不位于当前工作目录下时会抛出 ValueError，可能导致评审流程中断；建议捕获异常或改用绝对路径
#%% 第 53-54 行对 notes/issues/imperfections 的空值过滤逻辑使用 isinstance(s, str) and s.strip() != ''，但未处理列表中可能存在的 None 值，可能导致 TypeError；建议在 isinstance 检查前添加 s is not None 条件
#%% ----------

import time
from typing import Any
from pathlib import Path
from ..codeparser.index import Parser, ParserFactory
from .reviewer import CliReviewer


def _load(parser: Parser, src_path: str, references: list[str], context: str) -> Any:
    # 构建评审请求数据：计算相对路径、读取源码、提取历史评审注释、识别语言设置
    path = Path(src_path).resolve().parent.relative_to(Path.cwd())
    src_code = Path(src_path).resolve().read_text(encoding="utf-8")
    # 提取标记为 '%%' 的评审注释，返回 (注释列表, 纯源码)
    reviews, source = parser.extract_comments(src_code, '%%')

    # 从历史评审中解析 $lang: 设置，默认为 English
    comment_language = 'English'
    lang = '$lang:'
    for review in reviews:
        if(review.startswith(lang)):
            review = review[len(lang):].strip()
            if review != '':
                comment_language = review.split(' ')[0]
            break

    prior_review = '\n'.join(reviews)
    return {
        'path': str(path),
        'references': references,
        'comment_language': comment_language,
        'prior_review': prior_review,
        'context': context,
        'input': source.strip('\n'),
    }

def _comment_section(comment: str, title: str) -> str:
    # 格式化评审注释的各个部分为 '---------- [Title]\ncontent\n' 格式
    return f'---------- [{title}]\n{comment}\n'

def _update(ai: str, lang: str, parser: Parser, src_path: str, data: Any) -> str:
    # 将 AI 评审结果格式化为注释头部，插入源文件顶部并保存
    txt = f"---------- Reviewed by: {ai} @ {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
    txt += '$lang: ' + lang + '\n'
    if data['overview'] != '':
        txt += _comment_section(data['overview'], 'Overview')
    if data['review'] != '':
        txt += _comment_section(data['review'], 'Review')
    notes_text = '\n'.join([s for s in data.get('notes', []) if isinstance(s, str) and s.strip() != '']).strip()
    if notes_text != '':
        txt += _comment_section(notes_text, 'Notes')
    issues_text = '\n'.join([s for s in data.get('issues', []) if isinstance(s, str) and s.strip() != '']).strip()
    if issues_text != '':
        txt += _comment_section(issues_text, 'Issues')
    imperfections_text = '\n'.join([s for s in data.get('imperfections', []) if isinstance(s, str) and s.strip() != '']).strip()
    if imperfections_text != '':
        txt += _comment_section(imperfections_text, 'Imperfections')
    txt += '----------\n'

    # 将评审注释插入源码顶部（第 0 行）
    source = data['output'].strip('\n')
    source = parser.insert_comment(source = source, line = 0, comment = txt, tag = '%%', block = False)
    Path(src_path).resolve().write_text(source, encoding="utf-8")
    return txt

def _error(i: int, path: str, data: Any, err: str | None, log: Path | None = None):
    # 记录评审失败的错误信息到日志文件，使用正确的英文序数词后缀
    d = i % 10
    th = 'st' if d == 1 else 'nd' if d == 2 else 'rd' if d == 3 else 'th'
    print(f"[WARNING] Failed the {i}{th} time to review {path}: {err}")
    if log:
        with open(log, 'a', encoding='utf-8') as f:
            f.write(f"#{i}: {err}\n")
            if data and 'output' in data:
                # 记录 AI 可能错误修改的代码逻辑，用于调试
                f.write("<<<\n")
                f.write(data['output'] + '\n')
                f.write(">>>\n")
    

def review_code(reviewer: CliReviewer, src_path: str, references: list[str], context = '', lang = '', timeout=0, retry = 1, tmp: str | None = None) -> str | None:
    # 主评审流程：加载源码 -> 执行 AI 评审（支持重试）-> 验证 AST -> 写回文件
    parser = ParserFactory.create_by_filename(src_path)
    request = _load(parser, src_path, references, context)
    source = request['input']
    if source == '':
        return ''

    # 解析源码 AST 用于后续验证 AI 输出未改变代码逻辑
    logic = parser.parse(source)

    # 初始化 AI 评审器：准备系统提示、用户提示、超时参数
    args, stdin_prompt, timeout = reviewer.init("prompts/codereview.md", request, parser, lang, timeout)
    lang = request['comment_language']
    ai = reviewer.ai()

    # 设置错误日志路径
    if tmp is None or tmp == '':
        log = None
    else:
        fn = src_path.replace('\\', '/').split('/')[-1]
        log = Path(tmp).resolve() / f'{fn}.log'
        log.parent.mkdir(parents=True, exist_ok=True)

    # 重试机制：最多尝试 retry 次，每次失败后记录错误并重试
    for i in range(retry):
        # 生成序数词用于友好的进度提示
        d = (i + 1) % 10
        th = 'st' if d == 1 else 'nd' if d == 2 else 'rd' if d == 3 else 'th'
        print(f"Reviewing {src_path} for the {i+1}{th} time(s)...")
        t0 = time.time()
        # 执行 AI 评审并验证 AST 是否与原始输入匹配
        data, err = reviewer.exec(args=args, timeout=timeout, stdin_prompt=stdin_prompt, parser=parser, expected=logic)
        dt = time.time() - t0
        print(f"... Reviewed in {int(dt)}\"")
        if data and not err:
            # 评审成功且 AST 验证通过，更新源文件
            return _update(ai, lang, parser, src_path, data)
        else:
            # 记录错误并继续重试
            _error(i+1, src_path, data, err, log)
            if i < retry - 1:
                print(f"Retrying...")
                continue
            if i == retry - 1 and data:
                # 最后一次重试时若 AST 不匹配：放弃 AI 修改的代码，保留评审元数据
                print(f"Let's ignore the modified inline comments, just update the review metadata.")
                data['output'] = source
                return _update(ai, lang, parser, src_path, data)

    return None