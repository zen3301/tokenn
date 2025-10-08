#%% ---------- Reviewed by: claude
#%% $lang: 中文
#%% ---------- [Overview]
#%% 该模块是代码评审工具的核心调度层，封装了 AI 评审器（Codex/Claude）的调用逻辑，支持单文件、目录批量、Git 修改集的评审模式，并可生成项目级综合评审报告（.REVIEW.md）。协调 Parser、CliReviewer、git 等组件，提供完整的评审闭环。
#%% ---------- [Review]
#%% 代码结构清晰，职责划分合理，类型注解完整。路径处理逻辑健壮，支持 Windows 路径规范化。Git 集成使用 GitPython 库，错误处理遵循「失败静默」和「异常显式」的混合策略。注释从中文翻译为英文，语义准确但部分过于冗长。整体完成度约 95%，可维护性强，测试性良好。现有 VERIFIED 注释标记的设计决策均已验证。
#%% ---------- [Notes]
#%% 第 41 行 _git_diff 中的空字符串返回是经验性设计（VERIFIED 注释），允许调用者在无 diff 时继续评审流程
#%% 第 50 行 _git_modified 的去重逻辑使用 dict.fromkeys 而非 set，确保保留文件顺序（按 modified、staged、untracked 优先级）
#%% 第 70 行 _paths 函数的降序排序确保子目录优先于父目录合成 .REVIEW.md，避免父目录评审覆盖子目录结果
#%% 第 86 行 review_code 构建的 context 仅在 git-diff 非空或 self.context 非空时包含对应键值，避免传递空数据
#%% 第 130 行 review_proj 中文件扫描仅包含当前目录代码文件，子目录扫描仅包含一级子目录且排除以 '.' 开头的目录，符合模块化设计
#%% ---------- [Imperfections]
#%% 第 26 行 _collect_references 中 Path(project).glob('*.md') 未处理 project 为空字符串时的边界情况，虽然第 23-24 行已确保 project 非空或以 '/' 结尾，但逻辑上 Path('').glob() 会搜索当前目录，可能引入非预期文件
#%% 第 32-35 行的注释翻译过于冗长（'Ensure project path ends with... prevent empty directory from becoming root'），建议简化为 'Normalize project path with trailing slash' 即可表达意图
#%% 第 82 行 fn = src_path.replace('\\\\', '/').split('/')[-1] 使用四个反斜杠匹配原始字符串中的双反斜杠，但 Python 字符串字面量中应使用 '\\\\' 或 r'\\' 表示路径分隔符；建议改用 Path(src_path).name 更清晰
#%% 第 145 行 review = extract_review(file) 未捕获 ParserFactory.create_by_filename 可能抛出的异常（不支持的文件类型），虽然前面已过滤扩展名但存在时序竞争（文件在过滤后被修改）
#%% 第 56 行 repo_root = Path(repo.working_tree_dir) 未验证 working_tree_dir 是否为 None（裸仓库场景），可能导致 Path(None) 抛出 TypeError
#%% ----------

import json
from git import Repo
from pathlib import Path
from ..codeparser.index import ParserFactory
from .reviewer import CliReviewer
from .review_code import review_code
from .review_proj import review_proj, extract_review


class Review:
    def __init__(self, ai: str, context = '', retry = 1, timeout=0, lang = '', tmp: str | None = None):
        self.reviewer = CliReviewer(ai)
        self.context = context
        self.retry = retry
        self.timeout = timeout
        self.lang = lang
        self.tmp = tmp
        # 从 parser 工厂获取所有支持的文件扩展名，用于过滤可评审文件
        self.extensions = tuple(ParserFactory.ext2parser().keys())

    def _collect_references(self, project: str) -> list[str]:
        # 规范化项目路径，确保以 '/' 结尾以避免空路径导致搜索根目录
        if project != '' and not project.endswith('/'):
            project += '/'

        # 收集项目目录下所有 markdown 文件作为评审参考上下文
        references = [project + str(f) for f in Path(project).glob('*.md')]
        return references

    def _git_diff(self, src_path: str) -> str:
        # 获取文件相对于 Git 仓库的 diff 信息
        try:
            src = Path(src_path).resolve()  # 转换为绝对路径
            repo = Repo(src.parent, search_parent_directories=True)  # 向上查找仓库根目录
            src = src.relative_to(repo.working_dir)  # 转换为仓库相对路径
            return repo.git.diff("--", str(src))
        except Exception:
            return ''  # VERIFIED! 失败时返回空字符串，调用者可在无 diff 上下文时继续评审流程

    def _git_modified(self, path: str) -> list[str]:
        # 获取 Git 仓库中所有已修改/已暂存/未跟踪的文件
        try:
            path = self._path(path)  # 规范化为绝对目录路径
            repo = Repo(path, search_parent_directories=True)  # 向上查找仓库根目录
            modified = repo.git.diff("HEAD", "--name-only", "--diff-filter=d").splitlines()  # 已修改，排除已删除
            staged   = repo.git.diff("--cached", "--name-only", "--diff-filter=d").splitlines()  # 已暂存，排除已删除
            untracked = repo.untracked_files  # 未跟踪文件
            relative = list(dict.fromkeys(modified + staged + untracked))  # 去重同时保留顺序
            # 转换为绝对路径
            repo_root = Path(repo.working_tree_dir)
            return [str(repo_root / f) for f in relative]
        except Exception as e:
            raise ValueError(f"Failed to get git modified files: {e}") from e
    
    def _path(self, path: str) -> str:
        # 提取路径的目录部分（若为文件则返回父目录）
        p = Path(path).resolve()
        return str(p) if p.is_dir() else str(p.parent)

    def _paths(self, files: list[str]) -> list[str]:
        # 从文件列表中提取唯一的目录路径，按长度降序排序
        paths = []
        for file in files:
            path = self._path(file)
            if path not in paths:
                paths.append(path)

        # 按长度降序排序，确保子目录优先于父目录处理，避免评审覆盖
        return sorted(paths, key=len, reverse=True)

    def review_code(self, src_path: str) -> str | None:
        # 对单个代码文件执行评审，跳过不支持的文件类型
        if not src_path.endswith(self.extensions):  # 检查文件扩展名是否在支持列表中
            return None

        fn = src_path.replace('\\', '/').split('/')[-1]  # 提取文件名
        project = src_path[0:-len(fn)]  # 提取项目路径（父目录）
        references = self._collect_references(project)

        ctx: dict[str, str] = {}
        diff = self._git_diff(src_path)
        if diff != '':
            ctx['git-diff'] = diff
        if self.context != '':
            ctx['context'] = self.context
        context = json.dumps(ctx, indent=2, ensure_ascii=False)
        return review_code(self.reviewer, src_path, references, context, self.lang, self.timeout, self.retry, self.tmp)

    def review_list(self, files: list[str]) -> int:
        # 对文件列表执行批量评审，返回成功评审的文件数
        count = 0
        for file in files:
            if self.review_code(file):
                count += 1
        return count

    def review_path(self, path: str, synthesize: bool = False) -> int:
        # 评审指定路径下的所有代码文件（非递归）
        files = [str(f) for f in Path(path).resolve().glob('*.*')]
        n = self.review_list(files)  # 对所有源文件执行文件级评审
        if synthesize:  # 可选地为该路径生成或更新 .REVIEW.md
            self.review_proj(path)
        return n

    def review_modified(self, path: str, synthesize: bool = False) -> int:
        # 评审 Git 修改的文件，可选地为受影响的目录合成 .REVIEW.md
        files = self._git_modified(path)
        n = self.review_list(files)  # 对修改的源文件执行文件级评审
        if synthesize:
            paths = self._paths(files)  # 提取受影响目录，按长度降序排序
            for path in paths:  # 为每个目录重新生成 .REVIEW.md
                self.review_proj(path)
        return n

    def review_proj(self, path: str) -> str | None:
        # 生成项目级评审报告（.REVIEW.md）
        path_obj = Path(path).resolve()
        if path_obj.exists() and path_obj.is_dir():
            dir_path = path_obj
            md_path = dir_path / '.REVIEW.md'
        else:
            md_path = path_obj
            dir_path = md_path.parent

        dir_path.mkdir(parents=True, exist_ok=True)
        project = str(dir_path).replace('\\', '/')  # 规范化 Windows 路径分隔符
        references = self._collect_references(project)

        # 仅包含当前目录下的代码文件（扩展名决定语言），不递归子目录
        files = [str(f) for f in dir_path.glob('*.*') if f.is_file()]
        # 仅包含一级子目录（忽略以 '.' 开头的特殊目录）
        folders = [str(f) for f in dir_path.glob('*/') if not f.name.startswith('.')]

        reviews = {}
        md_path_str = str(md_path)
        exts = tuple(ParserFactory.ext2parser().keys())
        for file in files:
            if not file.endswith(exts):  # 仅处理支持的文件类型
                continue
            review = extract_review(file)  # 尝试从文件中提取现有评审
            if not review:
                review = self.review_code(file)  # 若无现有评审则执行新评审
                if not review or review == '':
                    continue
            reviews[file] = review

        return review_proj(self.reviewer, md_path_str, reviews, folders, references, self.context, self.lang, self.timeout)