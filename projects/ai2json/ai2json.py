#%% ---------- Reviewed by: codex
#%% $lang: 中文
#%% ---------- [Overview]
#%% 该抽象类通过 CLI 调用外部 AI 进程，结合提示规模动态计算超时时间，并从围栏包裹的输出中提取 JSON，服务于 Codex/Claude 等子类的通用执行骨架。
#%% ---------- [Review]
#%% 代码组织清晰，接口职责划分合理，异常路径均统一包装返回，整体完成度高且易于扩展；仅需关注部分实现对运行环境编码与字符集的隐含假设。
#%% ---------- [Notes]
#%% 超时计算依赖字符长度估算提示规模，默认假设提示多为 ASCII。
#%% JSON 提取逻辑剥离围栏后只保留首尾花括号，适合 Markdown 包裹输出但对多余片段会截断。
#%% ---------- [Imperfections]
#%% subprocess.run 依赖 text=True 默认编码，在非 UTF-8 环境可能解码失败，建议显式指定 encoding。
#%% 超时预算按字符数右移估算 KB，对多字节字符的提示会低估时间预算，有潜在超时风险。
#%% ----------

import json
import subprocess
from typing import Any
from abc import abstractmethod
from projects.ai2json.index import AI2JSON

# 通过 CLI 调用的 AI 评审器，子类（如 Codex、Claude）位于 ./ai/
class ThisAI2JSON(AI2JSON):
    def init(self, system_prompt: str, user_prompt: str, timeout = 0) -> tuple[list[str], str | None, int]:
        # 返回 CLI 参数列表、标准输入提示以及最终超时时间
        # timeout=0: 按内容长度动态计算（每 KB 预算 + 基础开销）
        # timeout<0: 其绝对值作为每 KB 预算（秒），再加基础开销
        # timeout>0: 直接使用该值作为最终超时
        if timeout <= 0:
            timeout = self._perKB() if timeout == 0 else - timeout
            timeout *= len(system_prompt + user_prompt) >> 10  # 位移 10 位相当于除以 1024，近似按字符数折算为 KB
            timeout += self._timeout()  # 加上基础启动与清理开销

        args, stdin_prompt = self._get_args(system_prompt, user_prompt)
        return args, stdin_prompt, timeout

    def exec(self, args: list[str], timeout: int, stdin_prompt: str | None = None) -> tuple[Any, str | None]:
        # 执行子进程，返回解析后的 JSON 对象及错误信息（若失败）
        try:
            completed = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=timeout,
                input=stdin_prompt,
            )
            if completed.returncode != 0:
                return None, f"[ERR] subprocess.run: returncode={completed.returncode}"

            payload, err = self._parse_stdout(completed.stdout)
            if payload is None:
                return None, err

            data, err = self._extract_json(payload)
            if data is None:
                return None, err

            return data, None
        except subprocess.TimeoutExpired as e:
            return None, f"[ERR] subprocess.TimeoutExpired: {e}"
        except Exception as e:
            return None, f"[ERR] subprocess.Exception: {e}"

    @abstractmethod
    def _get_args(self, system_prompt: str, user_prompt: str) -> tuple[list[str], str | None]:
        # 子类实现：返回 CLI 参数列表，用户提示通过标准输入传入以避免命令行字符限制
        pass

    @abstractmethod
    def _parse_stdout(self, stdout: str) -> tuple[str | None, str | None]:
        # 子类实现：从 CLI 输出中提取 AI 响应字符串及错误信息（如有）
        pass

    def _fence(self) -> str:
        # 围栏语法标记，默认 Markdown 三反引号，子类可覆盖
        return '```'

    def _extract_json(self, payload: str) -> tuple[Any, str | None]:
        # 从可能带围栏的文本中提取单一 JSON 对象字典
        if not payload:
            return None, "[ERR] _extract_json: payload is empty"

        # 去掉围栏前后缀（如 ```json ... ```）
        fence = self._fence()
        i = payload.find(fence)
        if i >= 0:
            payload = payload[i + len(fence):]
            i = payload.rfind(fence)
            if i >= 0:
                payload = payload[:i]

        # 定位首个 { 与最后一个 } 提取 JSON 字符串
        i = payload.find("{")
        if i < 0:
            return None, "[ERR] _extract_json: can't find { in payload"
        payload = payload[i:]
        i = payload.rfind("}")
        if i < 0:
            return None, "[ERR] _extract_json: can't find } in payload"
        payload = payload[:i+1]

        # 解析并校验为字典类型
        try:
            data = json.loads(payload)
            if not isinstance(data, dict):
                return None, "[ERR] _extract_json: not a dictionary"
            return data, None
        except json.JSONDecodeError:
            return None, "[ERR] _extract_json: can't parse JSON"

    def _timeout(self) -> int:
        # 基础准备时间预算，默认 5 分钟（启动 CLI、网络延迟、清理）
        return 300

    def _perKB(self) -> int:
        # 每 KB 提示内容的处理时间预算，默认 60 秒
        return 60