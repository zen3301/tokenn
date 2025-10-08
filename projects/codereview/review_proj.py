#%% ---------- Reviewed by: claude
#%% $lang: 中文
#%% ---------- [Overview]
#%% 该模块是项目级代码评审工具的核心协调器，负责加载配置、扫描子模块、调用AI评审器、生成并更新.REVIEW.md文件，以及从源码中提取评审注释。它整合了路径安全性验证、markdown文档生成和多语言注释提取功能，为CLI提供项目综合评审能力。
#%% ---------- [Review]
#%% 代码整体结构清晰，职责划分明确，类型标注完整。路径操作通过resolve()和relative_to()确保安全性，异常处理覆盖关键路径越界场景。prior_review被主动清空是经过验证的设计决策（L26注释）。核心逻辑正确，markdown生成逻辑健壮。代码完成度约95%，可维护性和测试性良好。
#%% ---------- [Notes]
#%% L26的prior_review清空是经验性设计决策（VERIFIED注释），避免历史评审干扰当前评审质量
#%% L14-15和L82-84的路径相对化逻辑使用异常捕获确保所有路径均在工作目录内，防止路径遍历攻击
#%% L63的_paths2relative函数注释明确说明传入路径已被保证在prefix下，因此L67-69的异常分支理论上不可达
#%% _list函数接收大写key但查询小写键（L49），依赖调用者传入正确的大写字符串（如'Notes'、'Issues'）
#%% extract_review函数未验证ParserFactory.create_by_filename是否成功，假定调用者传入支持的文件类型
#%% ---------- [Imperfections]
#%% L49的data.get(key.lower())逻辑要求调用者传入大写键名，但函数签名和实现未明确此约束，建议在函数文档或参数校验中说明
#%% L123的extract_review函数未捕获ParserFactory.create_by_filename可能抛出的异常（不支持的文件类型），可能导致调用栈中断
#%% L124的parser.extract_comments调用未处理解析失败或返回空列表的边界情况，虽然L126已检查空列表但未区分「文件无注释」和「解析失败」
#%% L67-69的异常处理分支被注释标记为不可达（VERIFIED），但保留了raise语句，建议改为assert False或移除该分支以提升代码清晰度
#%% ----------

import time
from typing import Any
from pathlib import Path
from ..codeparser.index import ParserFactory
from .reviewer import CliReviewer


def _load(md_path: str, reviews: dict[str, str], references: list[str], context: str) -> Any:
    # 加载评审配置，验证路径安全性，提取语言偏好，初始化请求数据结构
    path = Path(md_path).resolve()
    dir = path if path.is_dir() else path.parent
    try: # md_path 必须位于当前工作目录下
        dir = dir.relative_to(Path.cwd())
    except Exception as e:
        raise ValueError(f"Review file {md_path} is not in the current working directory") from e

    dir.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.is_file():
        prior = path.read_text(encoding="utf-8")
    else:
        prior = ''

    # 从已有评审文件中提取注释语言偏好
    comment_language = 'English'
    lang = '$lang:'
    if prior.startswith(lang):
        eol = prior.find('\n')
        line = prior[len(lang):eol].strip() if eol >= 0 else prior[len(lang):].strip()
        if line != '':
            comment_language = line.split(' ')[0]
    prior = ""  # VERIFIED! 此处忽略以往评审结果效果更好

    return {
        'path': str(dir),
        'references': references,
        'comment_language': comment_language,
        'prior_review': prior,
        'context': context,
        'reviews': reviews,
    }


def _modules(folders: list[str]) -> list[str]:
    # 扫描子目录中的.REVIEW.md文件，返回相对路径列表
    modules = []
    for folder in folders:
        review = Path(folder).resolve() / ".REVIEW.md"
        if review.exists():
            try:
                modules.append(review.resolve().relative_to(Path.cwd().resolve()).as_posix())
            except ValueError:
                modules.append(review.as_posix())
    return modules


def _list(data: Any, key: str) -> str:
    # 生成markdown格式的列表内容，接收大写key（如'Notes'）并查询小写键
    values = data.get(key.lower()) # data 使用全小写键值：notes, issues, imperfections
    if not values or not isinstance(values, list):
        return ''
    title = f"\n# {key}:\n"
    return title + '\n'.join([f'- {item}' for item in values]) + '\n'


def _paths2relative(paths: list[str], prefix: str) -> list[str]:
    # 将绝对路径转换为相对于prefix的路径
    try:
        # VERIFIED! 此处逻辑正确且已验证！传入的路径均保证基于当前工作目录（而非仓库或 request['path']），且均在 prefix 目录下
        return [str(Path(path).resolve().relative_to(prefix)).replace('\\', '/') for path in paths]
    except Exception as e:
        # VERIFIED! 此处不需处理，实际上不会进入此分支
        raise ValueError(f"Some path is not in the prefix {prefix}") from e


def _update(ai: str, request: Any, data: Any) -> str:
    # 根据评审结果更新.REVIEW.md文件，生成文件树和各评审章节
    md = f"$lang: {request['comment_language']}\n"
    md += f"---------- Reviewed by: {ai} @ {time.strftime('%Y-%m-%d %H:%M:%S')}\n"

    dir = request['path']
    path = Path(dir) / ".REVIEW.md"
    prefix = Path(dir).resolve().as_posix()
    try: # .REVIEW.md 必须位于当前工作目录下
        location = str(path.resolve().relative_to(Path.cwd().resolve())).replace('\\', '/')
        md += f"\n{location}\n"
    except Exception as e:
        raise ValueError(f"Review file {path} is not in the current working directory") from e

    # 处理评审过的文件列表
    reviews_payload = data.get("reviews")
    if not isinstance(reviews_payload, dict) or len(reviews_payload) == 0:
        reviews_payload = request['reviews']
    files = _paths2relative(list(reviews_payload.keys()), prefix)

    # 处理子模块评审列表
    subs_payload = data.get("sub_module_reviews")
    if not isinstance(subs_payload, list):
        subs_payload = request.get('sub_module_reviews', [])
    subs = _paths2relative([str(entry) for entry in subs_payload], prefix)

    # 生成文件树结构，文件在前、子模块在后，使用树状符号表示层级
    l = files + subs
    nf = len(files)
    n = len(l)
    for i in range(n):
        prefix = '├──' if i < n-1 else '└──'
        if i >= nf:
            prefix += '──'  # 子模块使用双横线标记
        md += f"    {prefix} {l[i]}\n"

    # 添加评审内容各部分：总览、评审意见、备注、问题、瑕疵
    overview = data.get('overview', '')
    review = data.get('review', '')

    md += f"\n# Overview:\n{overview}\n"
    md += f"\n# Review:\n{review}\n"
    md += _list(data, "Notes")
    md += _list(data, "Issues")
    md += _list(data, "Imperfections")

    path.resolve().write_text(md, encoding="utf-8")
    return md


def review_proj(reviewer: CliReviewer, md_path: str, reviews: dict[str, str], folders: list[str], references: list[str], context = '', lang = '', timeout=0) -> str:
    # 项目级别代码评审的主要入口函数：加载配置、执行AI评审、更新.REVIEW.md
    request = _load(md_path, reviews, references, context)
    request['sub_module_reviews'] = _modules(folders)

    print(f"Reviewing {request['path']}...")
    t0 = time.time()
    args, stdin_prompt, timeout = reviewer.init("prompts/projreview.md", request, None, lang, timeout)
    data, err = reviewer.exec(args=args, timeout=timeout, stdin_prompt=stdin_prompt)
    dt = time.time() - t0
    print(f"... Reviewed '.REVIEW.md' in {int(dt)}\"")
    if data is not None and not err:
        return _update(reviewer.ai(), request, data)

    return None


def extract_review(src_path: str) -> str:
    # 从源码文件中提取评审注释（使用%%标记的注释），返回拼接后的字符串或None
    parser = ParserFactory.create_by_filename(src_path)
    src_code = Path(src_path).resolve().read_text(encoding="utf-8")
    reviews, _ = parser.extract_comments(src_code, '%%')

    if not reviews or len(reviews) == 0:
        return None
    return '\n'.join(reviews)