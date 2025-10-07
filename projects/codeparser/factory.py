#%% ---------- Reviewed by: claude
#%% $lang: 中文
#%% ---------- [Overview]
#%% 该工厂类负责构建和管理代码解析器实例，通过语言名称或文件扩展名创建对应的解析器。它枚举 10 种编程语言（Python、TypeScript、Java、C、C++、C#、Go、Rust、Bash、HTML），校验语言和扩展名的唯一性，并提供工厂方法供外部调用。
#%% ---------- [Review]
#%% 代码逻辑清晰，异常检查集中在关键的冲突检测点（语言名冲突、扩展名冲突），可有效捕获子类配置错误。整体完成度高，结构简洁，可测试性良好。parsers() 和 ext2parser() 每次调用都重建实例的设计选择在注释中已明确说明理由，且与使用场景匹配（低频调用）。
#%% ---------- [Notes]
#%% parsers() 和 ext2parser() 每次调用均重建全量解析器实例，基于「低频调用、代码简洁性优先」的设计决策，性能影响可忽略
#%% 假定所有解析器子类可无参初始化，且返回的 language() 和 extensions() 唯一且不冲突；代码已显式校验此约束
#%% create_by_filename() 仅使用最后一段扩展名（如 .d.ts → .ts），已足够覆盖实际场景；注释中已明确说明
#%% ---------- [Imperfections]
#%% parsers() 和 create() 中针对解析器初始化失败的 Exception 捕获范围过宽，建议缩小为更具体的异常类型（如 ValueError、TypeError），以便更快定位子类实现问题
#%% ext2parser() 中扩展名冲突时的错误信息显示 map[ext].language() 和 parser.language()，但当多个解析器声明同一扩展名时，报错仅能显示首个注册的解析器，可能导致排查混淆
#%% ----------

import os
from .parser import Parser
from .languages.python import PythonParser
from .languages.typescript import TypescriptParser
from .languages.java import JavaParser
from .languages.c import CParser
from .languages.cpp import CppParser
from .languages.csharp import CSharpParser
from .languages.go import GoParser
from .languages.rust import RustParser
from .languages.bash import BashParser
from .languages.html import HtmlParser


class TheParserFactory:
    @staticmethod
    def parsers() -> dict[str, Parser]:
        # 枚举所有支持的解析器类
        parser_classes = [
            PythonParser,
            TypescriptParser,
            JavaParser,
            CParser,
            CppParser,
            CSharpParser,
            GoParser,
            RustParser,
            BashParser,
            HtmlParser,
        ]

        factory: dict[str, Parser] = {}
        for parser_class in parser_classes:
            try:
                parser = parser_class()
            except Exception as e:  # 不应发生，每个子类应确保各自可被合法创建
                raise ValueError(f"Failed to initialize parser for {parser_class.__name__}") from e
            lang = parser.language()
            if lang in factory:  # 不应发生，每个子类应确保各自语言唯一性
                raise ValueError(f"Language {lang} is shared by multiple parsers: {parser_class.__name__}")
            factory[lang] = parser

        return factory

    @staticmethod
    def ext2parser() -> dict[str, Parser]:
        # 构建文件扩展名到解析器的映射
        map: dict[str, Parser] = {}
        parsers = TheParserFactory.parsers()
        for parser in parsers.values():
            for ext in parser.extensions():
                ext = ext.lower()
                # 各 parser.extensions() 均确保返回带前导点的格式
                if ext in map:  # 不应发生，例如 C/C++ 均需确保各自处理的扩展名不同
                    raise ValueError(f"Extension {ext} is shared by multiple parsers: {map[ext].language()} and {parser.language()}")
                map[ext] = parser
        return map

    @staticmethod
    def create(language: str) -> Parser:
        # 重建全量解析器实例以简化代码，代价极小，频率极低，性能影响忽略不计
        parsers = TheParserFactory.parsers()
        if language not in parsers:
            raise ValueError(f"Language {language} not supported")
        return parsers[language]

    @staticmethod
    def create_by_filename(fn: str) -> Parser:
        # 重建全量解析器实例以简化代码，代价极小，频率极低，性能影响忽略不计
        ext2parser = TheParserFactory.ext2parser()
        # "foo.d.ts" 等多段扩展名将返回最后一段 ".ts"，已足够找到解析器
        _, ext = os.path.splitext(fn)
        ext = ext.lower()
        if ext not in ext2parser:
            raise ValueError(f"Extension {ext} not supported for {fn}")
        return ext2parser[ext]