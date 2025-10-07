#%% ---------- Reviewed by: codex
#%% $lang: 中文
#%% ---------- [Overview]
#%% 该模块提供 AI2JSON 抽象基类与工厂，规范不同 AI 适配器的初始化与执行接口，并通过延迟导入返回具体实现，整体结构简洁清晰，便于扩展新的 CLI 驱动 AI。
#%% ---------- [Review]
#%% 抽象基类接口清晰、类型标注完整，工厂模式实现得当且延迟导入避免循环依赖，当前实现可直接集成。建议在错误提示中包含支持的 AI 名称以提升可用性，除此之外无阻塞性问题。
#%% ---------- [Notes]
#%% 工厂通过延迟导入解耦具体实现，确保新增 AI 时只需扩展该分支。
#%% ---------- [Imperfections]
#%% 工厂抛出的 ValueError 未列出可用 AI 名称，调用方调试体验略差，可考虑在消息中补充支持列表。
#%% ----------

from typing import Any
from abc import ABC, abstractmethod

# AI2JSON 抽象基类：定义统一的 AI 接口规范，所有具体 AI 实现需继承此类
class AI2JSON(ABC):
    @abstractmethod
    def ai(self) -> str:
        # 返回 AI 名称标识，如 'codex'、'claude'
        pass

    @abstractmethod
    def init(self, system_prompt: str, user_prompt: str, timeout = 0) -> tuple[list[str], str | None, int]:
        # 初始化 CLI 调用参数
        # 返回：CLI 参数列表、标准输入提示内容（用于绕过命令行字符限制）、最终超时时间（秒）
        pass

    @abstractmethod
    def exec(self, args: list[str], timeout: int, stdin_prompt: str | None = None) -> tuple[Any, str | None]:
        # 执行 CLI 并解析结果
        # 返回：解析后的 JSON 对象（字典）、错误信息（成功时为 None）
        pass


# 工厂类：通过延迟导入创建具体 AI 实现，避免循环依赖
class AI2JSONFactory:
    @staticmethod
    def create(ai: str) -> AI2JSON:
        # 根据 AI 名称创建对应实现
        if ai == 'codex':
            from .ai.codex import Codex2JSON
            return Codex2JSON()
        elif ai == 'claude':
            from .ai.claude import Claude2JSON
            return Claude2JSON()
        else:
            # 建议在错误提示中列出受支持的 AI 名称，方便调用方快速定位配置错误
            raise ValueError(f"Invalid AI: {ai}")