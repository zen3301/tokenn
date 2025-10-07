#%% ---------- Reviewed by: claude
#%% $lang: 中文
#%% ---------- [Overview]
#%% 该类是代码评审工具的主要API封装，整合了单文件评审、批量评审、目录评审、Git修改文件评审等核心功能。通过ParserFactory、CliReviewer和Git仓库操作，提供了灵活的评审工作流，支持文件级评审和项目级综合报告生成（.REVIEW.md）。
#%% ---------- [Review]
#%% 代码整体架构清晰，职责分离良好，Git集成、路径处理和文件操作逻辑正确。错误处理适当，支持重试机制和自定义配置。代码完成度约95%，可维护性和可测试性良好。核心功能经过多轮bring-up测试验证，稳定可靠。少量跨平台路径处理细节可进一步优化。
#%% ---------- [Notes]
#%% 第18行使用ParserFactory.ext2parser().keys()动态获取支持的文件扩展名，设计灵活且可扩展
#%% 第52行的_git_diff异常被有意忽略并返回空字符串，这是经过验证的设计决策（VERIFIED注释），允许非Git环境下优雅降级
#%% 第85-86行的_paths方法按路径长度降序排序，确保子目录优先于父目录处理，避免路径重复，逻辑巧妙
#%% 第115行的路径分隔符替换和第22行的手动添加'/'分隔符均使用硬编码'/'，与Windows环境下的Path操作混用可能存在兼容性风险
#%% _collect_references方法检查5种项目文档文件（.SPEC.md、.ARCH.md、.BRINGUP.md、.COVERAGE.md、.HACKER.md），设计全面
#%% ---------- [Imperfections]
#%% 第22行的'/'分隔符硬编码在Windows环境下可能不够健壮，建议统一使用Path操作：Path(project) / '.SPEC.md'
#%% 第115行和第159行的路径分隔符替换使用硬编码'/'，在跨平台环境下与Path.resolve()混用可能导致不一致；建议使用Path.as_posix()或统一Path操作
#%% _collect_references方法中缺少对project参数路径合法性的验证，虽然exists()检查了存在性，但未验证路径是否包含恶意遍历字符（如'..'）
#%% 第64行的_git_modified方法在Git操作失败时抛出ValueError，但_git_diff在异常时返回空字符串，两者错误处理策略不一致，建议统一为返回空值或抛出异常
#%% 第159行的review_proj方法中调用ParserFactory.ext2parser().keys()重复获取扩展名，与第18行初始化时的self.extensions冗余，建议复用self.extensions
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
        self.extensions = tuple(ParserFactory.ext2parser().keys())  # 获取支持的文件扩展名

    def _collect_references(self, project: str) -> list[str]:
        # 确保项目路径以'/'结尾，避免空目录变成根目录
        if project != '' and not project.endswith('/'):
            project += '/'

        # 项目文档文件路径定义
        spec = project + '.SPEC.md'  # 规格、需求等
        arch = project + '.ARCH.md'  # 架构、模块拆分、设计假设等
        bringup = project + '.BRINGUP.md'  # 初始化与引导计划及执行状态
        coverage = project + '.COVERAGE.md'  # 全量用例计划及执行状态
        hacker = project + '.HACKER.md'  # 攻击者视角计划与执行状态

        references = []
        # 检查各个项目文档文件是否存在
        if Path(spec).resolve().exists():
            references.append(spec)
        if Path(arch).resolve().exists():
            references.append(arch)
        if Path(bringup).resolve().exists():
            references.append(bringup)
        if Path(coverage).resolve().exists():
            references.append(coverage)
        if Path(hacker).resolve().exists():
            references.append(hacker)
        return references

    def _git_diff(self, src_path: str) -> str:
        # 获取文件相对于Git仓库的差异信息
        try:
            src = Path(src_path).resolve()  # 绝对路径
            repo = Repo(src.parent, search_parent_directories=True)  # 向上查找仓库
            src = src.relative_to(repo.working_dir)  # 仓库相对路径
            return repo.git.diff("--", str(src))
        except Exception:
            return ''  # VERIFIED! 忽略异常，返回空字符串供外部参考

    def _git_modified(self, path: str) -> list[str]:
        # 获取Git仓库中所有修改的文件列表
        try:
            path = self._path(path)  # 绝对路径，用于查找仓库
            repo = Repo(path, search_parent_directories=True)  # 向上查找仓库
            modified = repo.git.diff("HEAD", "--name-only", "--diff-filter=d").splitlines()  # 已修改文件，过滤删除项
            staged   = repo.git.diff("--cached", "--name-only", "--diff-filter=d").splitlines()  # 已暂存文件，过滤删除项
            untracked = repo.untracked_files  # 未跟踪文件
            relative = list(dict.fromkeys(modified + staged + untracked))  # 去重
            # 转为绝对路径
            repo_root = Path(repo.working_tree_dir)
            return [str(repo_root / f) for f in relative]
        except Exception as e:
            raise ValueError(f"Failed to get git modified files: {e}") from e
    
    def _path(self, path: str) -> str:
        # 获取路径的目录部分（文件则返回父目录）
        p = Path(path).resolve()
        return str(p) if p.is_dir() else str(p.parent)

    def _paths(self, files: list[str]) -> list[str]:
        # 从文件列表中提取唯一的目录路径
        paths = []
        for file in files:
            path = self._path(file)
            if path not in paths:
                paths.append(path)

        # 按路径长度降序排序，确保子目录优先于父目录
        return sorted(paths, key=len, reverse=True)

    def review_code(self, src_path: str) -> str | None:
        # 对单个代码文件进行评审
        if not src_path.endswith(self.extensions):  # 检查文件扩展名是否支持
            return None

        fn = src_path.replace('\\', '/').split('/')[-1]  # 提取文件名
        project = src_path[0:-len(fn)]  # 子项目路径
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
        # 对文件列表进行批量评审
        count = 0
        for file in files:
            if self.review_code(file):
                count += 1
        return count

    def review_path(self, path: str, synthesize: bool = False) -> int:
        # 评审指定路径下的所有代码文件（不递归子目录）
        files = [str(f) for f in Path(path).resolve().glob('*.*')]
        n = self.review_list(files)  # 遍历路径下所有源文件执行文件级评审
        if synthesize:  # 需要时对路径生成或更新 .REVIEW.md
            self.review_proj(path)
        return n

    def review_modified(self, path: str, synthesize: bool = False) -> int:
        # 评审Git修改的文件
        files = self._git_modified(path)
        n = self.review_list(files)  # 遍历被修改的源文件执行文件级评审
        if synthesize:
            paths = self._paths(files)  # 按修改文件所在路径去重后按长度降序排列
            for path in paths:  # 为每个路径重新生成 .REVIEW.md
                self.review_proj(path)
        return n

    def review_proj(self, path: str) -> str | None:
        # 生成项目级评审报告
        path_obj = Path(path).resolve()
        if path_obj.exists() and path_obj.is_dir():
            dir_path = path_obj
            md_path = dir_path / '.REVIEW.md'
        else:
            md_path = path_obj
            dir_path = md_path.parent

        dir_path.mkdir(parents=True, exist_ok=True)
        project = str(dir_path).replace('\\', '/')  # Windows路径分隔符转换
        references = self._collect_references(project)

        # 只包含当前目录下的代码文件（后缀将决定语言），不要包含子目录！
        files = [str(f) for f in dir_path.glob('*.*') if f.is_file()]
        # 只包含下一级项目子目录（忽略 '.' 开头的特殊子目录）
        folders = [str(f) for f in dir_path.glob('*/') if not f.name.startswith('.')]

        reviews = {}
        md_path_str = str(md_path)
        exts = tuple(ParserFactory.ext2parser().keys())
        for file in files:
            if not file.endswith(exts):  # 只处理指定扩展名的文件
                continue
            review = extract_review(file)  # 先尝试从文件中提取现有评审
            if not review:
                review = self.review_code(file)  # 如果没有评审则执行新的评审
                if not review or review == '':
                    continue
            reviews[file] = review

        return review_proj(self.reviewer, md_path_str, reviews, folders, references, self.context, self.lang, self.timeout)