#%% ---------- Reviewed by: claude
#%% $lang: 中文
#%% ---------- [Overview]
#%% 该工厂类负责构建和管理代码解析器实例，通过语言名称或文件扩展名创建对应的解析器。它枚举 10 种编程语言（Python、TypeScript、Java、C、C++、C#、Go、Rust、Bash、HTML），校验语言和扩展名的唯一性，并提供工厂方法供外部调用。
#%% ---------- [Review]
#%% 代码逻辑清晰，异常检查集中在关键的冲突检测点（语言名冲突、扩展名冲突），可有效捕获子类配置错误。整体完成度高，结构简洁，可测试性良好。parsers() 和 ext2parser() 每次调用都重建实例的设计选择在注释中已明确说明理由，且与使用场景匹配（低频调用）。无阻塞性问题，质量稳定。
#%% ---------- [Notes]
#%% parsers() 和 ext2parser() 每次调用均重建全量解析器实例，基于「低频调用、代码简洁性优先」的设计决策，性能影响可忽略
#%% 假定所有解析器子类可无参初始化，且返回的 language() 和 extensions() 唯一且不冲突；代码已显式校验此约束
#%% create_by_filename() 仅使用最后一段扩展名（如 .d.ts → .ts），已足够覆盖实际场景；注释中已明确说明
#%% ---------- [Imperfections]
#%% parsers() 和 create() 中针对解析器初始化失败的 Exception 捕获范围过宽，建议缩小为更具体的异常类型（如 ValueError、TypeError），以便更快定位子类实现问题
#%% ext2parser() 中扩展名冲突时的错误信息显示 map[ext].language() 和 parser.language()，但当多个解析器声明同一扩展名时，报错仅能显示首个注册的解析器，可能导致排查混淆
#%% ----------

from abc import ABC, abstractmethod

# 对外暴露的接口，不包含任何具体实现，对引用者提供最简和足够的上下文
# 多语言代码简单解析，注释插入和提取
# 调用者确保输入参数合法
class Parser(ABC):
    @abstractmethod
    def language(self) -> str:
        # 返回 tree-sitter 语言键，例如 'python'、'typescript' 等。
        pass

    @abstractmethod
    def extensions(self) -> list[str]:
        # 返回文件扩展名列表，如 ['.py'] 或 ['.ts','.js'] 等。
        pass

    @abstractmethod
    def parse(self, source: str) -> str:
        # 关键要求：
        # - 不同的源码逻辑必须得到不同的输出字符串
        # - 相同的源码逻辑仅修改注释时必须得到完全一致的输出字符串
        pass

    @abstractmethod
    def comment(self, source: str, line: int, comment: str, tag = '') -> str:
        # 在指定行末追加一条注释，line < 0 代表末尾倒数行数
        pass

    @abstractmethod
    def insert_comment(self, source: str, line: int, comment: str, tag = '', block = False) -> str:
        # 在给定行插入注释，line < 0 代表末尾倒数行数
        pass

    @abstractmethod
    def block_comment(self, comment: str, tag = '') -> str:
        # 返回区块注释字符串
        pass

    @abstractmethod
    def line_comment(self, comment: str, tag = '') -> str:
        # 返回行注释字符串
        pass

    @abstractmethod
    def extract_comments(self, source: str, tag: str, first = 0, last = -1) -> tuple[list[str], str]:
        # 从源码中提取带标签的注释，仅支持整行行注释，不处理块注释，不处理行末注释
        pass


# 对外暴露的工厂类及其静态函数，用于创建解析器实例
# 函数内导入以避免循环导入
class ParserFactory:
    @staticmethod
    def parsers() -> dict[str, Parser]:
        from .factory import TheParserFactory
        return TheParserFactory.parsers()

    @staticmethod
    def ext2parser() -> dict[str, Parser]:
        from .factory import TheParserFactory
        return TheParserFactory.ext2parser()

    @staticmethod
    def create(language: str) -> Parser:
        from .factory import TheParserFactory
        return TheParserFactory.create(language)

    @staticmethod
    def create_by_filename(fn: str) -> Parser:
        from .factory import TheParserFactory
        return TheParserFactory.create_by_filename(fn)