#%% ---------- Reviewed by: claude
#%% $lang: 中文
#%% ---------- [Overview]
#%% 该模块是代码评审工具的核心审查执行器，封装了与AI后端（Codex/Claude）的交互逻辑，负责初始化评审请求、执行评审并验证返回JSON数据的完整性和类型正确性。通过AST比较验证代码输出的逻辑一致性，确保评审不改变源码语义。
#%% ---------- [Review]
#%% 代码结构清晰，职责单一，类型标注完整。数据验证逻辑健壮，包括类型检查、必填字段验证和条件性AST比较。错误处理通过元组返回值清晰传递状态，便于调用者处理。系统提示构建支持动态语言插值。整体代码质量优秀，完成度100%，可维护性强，测试性良好。
#%% ---------- [Notes]
#%% 第45行的 isinstance(data, dict) 检查是必要的防护，避免非字典类型（如列表或字符串）导致后续.get()调用失败
#%% 第74行使用parser.parse()进行AST比较是核心设计：确保AI输出的代码与原始输入在语义上完全等价，即使注释被修改
#%% 第75行的设计意图是：即使AST不匹配也返回data，允许调用者决定如何处理（例如记录警告但继续流程），而不是直接丢弃结果
#%% 系统提示中动态替换`comment_language`和`programming_language`占位符的设计使得单个.md模板可复用于多语言场景
#%% ---------- [Imperfections]
#%% 第74行的parser.parse()调用未捕获解析异常，如果data['output']包含语法错误或parser本身抛出异常，会导致整个评审流程中断；建议捕获并返回明确的错误信息
#%% 第67行和第71行对notes/issues/imperfections的空值处理逻辑不一致：空列表、None、空字符串都会被替换为[]，但未验证列表元素是否为字符串类型，可能接受混合类型列表
#%% 第47-48行的error字段检查使用data.get('error')和data['error']混用，虽然逻辑上正确但风格不统一；建议统一使用.get()或先验证键存在
#%% 缺少对data['output']长度的基本验证，理论上AI可能返回过长（如重复代码数百次）或空字符串的output，虽然概率低但可能影响下游处理
#%% ----------

import json
from typing import Any
from pathlib import Path
from ..codeparser.index import Parser
from ..ai2json.index import AI2JSONFactory

class CliReviewer():
    def __init__(self, ai: str):
        self.cli = AI2JSONFactory.create(ai)
    
    def ai(self) -> str:
        return self.cli.ai()

    def init(self, system_md: str, request: Any, parser: Parser | None = None, lang = '', timeout = 0) -> tuple[list[str], str | None, int]:
        # 优先使用调用者强制指定的注释语言，否则使用请求中的默认值
        if not lang or lang == '':
            lang = request['comment_language']
        else:
            request['comment_language'] = lang
        user_prompt = json.dumps(request, indent=2, ensure_ascii=False)

        # 加载系统提示模板并替换占位符
        path = Path(__file__).resolve().parent
        system_path = path / system_md
        system_prompt = system_path.read_text(encoding="utf-8")
        system_prompt = system_prompt.replace('`comment_language`', lang)
        if parser:
            system_prompt = system_prompt.replace('`programming_language`', parser.language())

        return self.cli.init(system_prompt, user_prompt, timeout)

    def exec(
        self,
        args: list[str],
        timeout: int,
        stdin_prompt: str | None = None,
        parser: Parser | None = None,
        expected: str | None = None,
    ) -> tuple[Any, str | None]:
        # 执行AI评审并验证返回数据
        data, err = self.cli.exec(args, timeout, stdin_prompt)
        if data is None or err:
            return None, err
        return self._data_check(data, parser, expected)

    def _data_check(self, data: Any, parser: Parser | None = None, expected: str | None = None) -> tuple[Any, str | None]:
        # 类型检查：确保数据是字典
        if not isinstance(data, dict):
            return None, f"[ERR] _data_check: <data> must be a dictionary"

        # 检查AI是否报告执行错误
        if data.get("error") and data['error'].strip() != "":
            return None, f"[ERR] _data_check: <error> = {data['error']}"

        # 验证必填字段
        required = ["overview", "review"]
        if not all(k in data for k in required):
            return None, f"[ERR] _data_check: required keys not found"

        # 规范化可选的列表字段
        if not data.get("notes"):
            data["notes"] = []
        elif not isinstance(data.get("notes"), list):
            return None, f"[ERR] _data_check: <notes> must be a string list"

        if not data.get("issues"):
            data["issues"] = []
        elif not isinstance(data.get("issues"), list):
            return None, f"[ERR] _data_check: <issues> must be a string list"

        if not data.get("imperfections"):
            data["imperfections"] = []
        elif not isinstance(data.get("imperfections"), list):
            return None, f"[ERR] _data_check: <imperfections> must be a string list"

        # 当提供parser时，验证output字段并进行AST比较
        if parser is not None:
            if not isinstance(data.get("output"), str):
                return None, f"[ERR] _data_check: <output> must be a string"

            # AST比较：确保AI输出的代码与原始输入在语义上等价
            if expected is not None:
                if parser.parse(data["output"]) != expected:
                    # VERIFIED! 即使AST不匹配也返回data，允许调用者记录警告但继续流程
                    return data, f"[ERR] _data_check: <output> does not match the input expected"

        # 所有验证通过
        return data, None