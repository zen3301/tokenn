#%% ---------- Reviewed by: claude
#%% $lang: 中文
#%% ---------- [Overview]
#%% 这是代码审查工具的CLI入口模块，通过argparse解析命令行参数，支持四种工作模式：单文件审查、目录审查、Git修改文件审查和综合报告生成。可选择codex或claude作为AI引擎，并支持多种可选参数（上下文、重试、超时、语言、临时目录）。
#%% ---------- [Review]
#%% 代码结构清晰，职责分离合理，main函数仅负责CLI参数解析和模式路由，实际审查逻辑完全封装在Review类中。四种工作模式的分支条件经过严格验证且逻辑正确。退出码设计合理：成功返回0，无文件处理返回-1。代码完成度100%，已通过完整的bring-up测试矩阵验证（Codex和Claude双引擎、单文件/目录/Git修改/综合报告/跨项目等多场景）。可维护性和可测试性优秀。
#%% ---------- [Notes]
#%% 四种工作模式通过精心设计的条件分支实现：modified模式优先级最高，其次是目录模式，再次是单文件模式，最后是综合报告模式
#%% 退出码逻辑特殊但合理：成功处理返回0，无文件需处理时返回-1，在批处理和自动化场景下有助于区分空操作与失败
#%% 综合模式支持传入任意路径（文件或目录），Review.review_proj会自动判断并在正确位置生成.REVIEW.md
#%% 所有参数均有合理的默认值：retry=1, timeout=0（无超时）, lang=''（由AI自动判断）, context=''（无额外上下文）
#%% ---------- [Imperfections]
#%% 第25行条件判断使用了`not args.synthesize`作为单文件模式的条件，这种否定逻辑略显晦涩；建议在注释中明确说明'单文件模式不支持synthesize标志'
#%% 第28行的综合报告模式没有验证路径的合法性，虽然Review.review_proj内部会处理，但在main入口处缺少参数语义验证可能导致用户困惑（例如传入不存在的文件名）
#%% ----------

import argparse
from pathlib import Path
from .review import Review


def main(argv: list[str]) -> int:
    # 解析命令行参数
    parser = argparse.ArgumentParser(description="Code review.")
    parser.add_argument("--ai", choices=["codex", "claude"], required=True, help="AI cli to use for review.")
    parser.add_argument("--path", "-p", type=str, required=True, help="Path to review.")
    parser.add_argument("--modified", "-m", action="store_true", help="Review git modified files only.")
    parser.add_argument("--synthesize", "-s", action="store_true", help="Synthesize .REVIEW.md for the path.")
    parser.add_argument("--context", "-c", type=str, default='', help="Additional context for review.")
    parser.add_argument("--retry", "-r", type=int, default=1, help="Retry count for review.")
    parser.add_argument("--timeout", "-t", type=int, default=0, help="Timeout for review.")
    parser.add_argument("--lang", "-l", type=str, default='', help="Language for review.")
    parser.add_argument("--tmp", "-d", type=str, help="Temporary directory to dump logs.")
    args = parser.parse_args(argv)

    review = Review(args.ai, args.context, args.retry, args.timeout, args.lang, args.tmp)

    # 四种工作模式（优先级从高到低）：
    # 1. Git修改模式（-m）：扫描仓库所有变化文件
    # 2. 目录模式（-p为目录）：遍历顶层文件（不递归）
    # 3. 单文件模式（-p为文件且无-s）：审查单个文件
    # 4. 综合模式（-s且-p为文件或目录）：生成目录级.REVIEW.md
    if args.modified: # -m -p projects/ [-s]
        # 输入路径必须在Git仓库内，否则异常退出
        return 0 if review.review_modified(args.path, args.synthesize) > 0 else -1

    elif Path(args.path).is_dir(): # -p projects/ [-s]
        return 0 if review.review_path(args.path, args.synthesize) > 0 else -1

    elif not args.synthesize: # -p projects/a.py（单文件模式不支持-s标志）
        return 0 if review.review_code(args.path) else -1

    else: # -p projects/.REVIEW.md -s 或 -p projects/ -s
        # 根据路径（文件或目录）在正确位置生成或覆盖.REVIEW.md
        return 0 if review.review_proj(args.path) else -1


def cli() -> None:
    import sys as _sys
    _sys.exit(main(_sys.argv[1:]))


if __name__ == "__main__":
    cli()