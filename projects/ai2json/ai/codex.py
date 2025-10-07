#%% ---------- Reviewed by: claude
#%% $lang: 中文
#%% ---------- [Overview]
#%% 该模块实现 GPT-5 Codex CLI 适配器，继承 ThisAI2JSON 基类，负责定位 codex 可执行入口（优先 node + codex.js，次选 codex 命令），构造跳过审批与 git 检查的 CLI 参数，从 stdout 逐行解析 JSON 事件流（支持新旧格式），提取 agent_message 中的文本内容，最后尝试直接解析 JSON 或回退至父类的围栏提取逻辑。
#%% ---------- [Review]
#%% 整体实现遵循父类契约，类型安全且逻辑清晰；入口定位回退机制与 claude.py 保持一致，JSON 事件流解析兼容新旧两种格式，_extract_json 首次尝试直接解析后回退至父类围栏提取，设计合理且健壮；当前未发现阻塞性缺陷，可直接用于生产。完成度约 100%，可测试性良好。
#%% ---------- [Notes]
#%% 入口定位采用三级回退策略（node + codex.js → codex 命令 → 裸 'codex' 字符串），与 claude.py 保持一致，保证跨环境兼容性
#%% _parse_stdout 同时支持新格式 {type:item.completed, item:{type:agent_message, text:...}} 和旧格式 {msg:{type:agent_message, message:...}}，兼容性设计体现前瞻性
#%% 使用 --dangerously-bypass-approvals-and-sandbox 和 --skip-git-repo-check 参数，适用于自动化场景但需注意安全边界
#%% _extract_json 首次尝试直接 json.loads，失败后回退至父类围栏提取逻辑，兼顾性能与兼容性
#%% ---------- [Imperfections]
#%% 入口定位逻辑中 candidate.exists() 仅检查文件存在性，未处理无执行权限或文件损坏的极端情况，可能在后续 subprocess.run 时失败并抛出不够明确的错误；建议在 ai2json.py 的 exec 方法中捕获 FileNotFoundError 或 PermissionError 并给出更友好提示（与 claude.py 存在相同问题）
#%% _parse_stdout 中两种格式检查存在顺序依赖：先检查新格式再检查旧格式；若未来新旧格式共存于同一事件流的不同事件中，可能导致只取到第一个匹配的格式而忽略后续；当前实现假设每次调用只返回一种格式的单一目标事件，该假设应记录在文档中
#%% ----------

import json
import shutil
from typing import Any
from pathlib import Path
from ..ai2json import ThisAI2JSON

# GPT-5 Codex CLI 适配器
class Codex2JSON(ThisAI2JSON):
    def ai(self) -> str:
        return "codex"

    def _get_args(self, system_prompt: str, user_prompt: str) -> tuple[list[str], str | None]:
        # 拼接系统与用户提示以避免命令行字符限制
        prompt = system_prompt + "\n" + user_prompt
        # 定位 Codex 可执行入口，优先尝试 node + codex.js 直接调用，回退至 codex 命令
        codex_entry = shutil.which("codex")
        node_entry = shutil.which("node")
        args_prefix: list[str]
        if codex_entry and node_entry:
            # 尝试直接使用 node 执行 codex.js 以避免 wrapper 脚本开销
            candidate = Path(codex_entry).resolve().parent / "node_modules" / "@openai" / "codex" / "bin" / "codex.js"
            if candidate.exists():
                args_prefix = [node_entry, str(candidate), "exec"]
            else:
                args_prefix = [codex_entry, "exec"]
        else:
            # 降级为裸字符串，依赖系统 PATH 解析
            args_prefix = ["codex", "exec"]
        # 构造命令行参数：跳过审批沙盒与 git 检查，强制 JSON 输出，从 stdin 读取提示
        args = args_prefix + [
            "--dangerously-bypass-approvals-and-sandbox",
            "--skip-git-repo-check",
            "--json",
            "-",
        ]
        return args, prompt

    def _parse_stdout(self, stdout: str) -> tuple[str | None, str | None]:
        # 逐行解析 JSON 事件流，兼容新旧两种格式：
        # 新格式: {"type":"item.completed","item":{"type":"agent_message","text":"..."}}
        # 旧格式: {"msg":{"type":"agent_message","message":"..."}}
        # 提取首个匹配的 agent_message 文本字段后立即返回
        for line in stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict):
                continue

            # 新格式：item.completed 事件包含 agent_message 类型的 item
            if event.get("type") == "item.completed":
                item = event.get("item")
                if isinstance(item, dict) and item.get("type") == "agent_message":
                    text = item.get("text")
                    if isinstance(text, str) and text.strip():
                        return text.strip(), None

            # 旧格式兼容：msg.type=agent_message 且 msg.message 非空
            msg = event.get("msg")
            if isinstance(msg, dict) and msg.get("type") == "agent_message":
                message = msg.get("message")
                if isinstance(message, str) and message.strip():
                    return message.strip(), None

        return None, "[ERR] _parse_stdout: no target message found"

    def _extract_json(self, payload: str) -> tuple[Any, str | None]:
        # 首次尝试直接解析 JSON，失败后回退至父类围栏提取逻辑
        payload = payload.strip()
        if not payload:
            return None, "[ERR] _extract_json: payload is empty"
        try:
            return json.loads(payload), None
        except json.JSONDecodeError:
            # 回退至父类实现（围栏提取）
            return super()._extract_json(payload)