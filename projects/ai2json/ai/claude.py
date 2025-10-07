#%% ---------- Reviewed by: claude
#%% $lang: 中文
#%% ---------- [Overview]
#%% 该模块实现 Claude CLI 集成适配器，继承 ThisAI2JSON 基类，负责定位 Claude 可执行入口（优先 node + cli.js，次选 claude 命令），根据运行环境（root/非 root）选择权限策略（acceptEdits 模式或跳过权限检查），构造带 JSON 输出格式的命令行参数，解析 stdout 中的 JSON 响应并严格校验 result 字段的存在性与非空性。
#%% ---------- [Review]
#%% 整体逻辑清晰且类型安全，入口定位回退机制健全，权限处理策略针对 root 环境做了专门优化（使用 acceptEdits 替代被禁止的 skip-permissions），JSON 解析与空值检查到位，错误信息明确可追溯；当前实现无明显缺陷，可直接用于生产环境。完成度约 100%，可测试性良好，建议测试覆盖 CLI 输出的各种形态（正常、空、格式错误）以及 root/非 root 两种权限模式。
#%% ---------- [Notes]
#%% 入口定位采用三级回退策略（node + cli.js → claude 命令 → 裸 'claude' 字符串），与 codex.py 保持一致，保证跨环境兼容性
#%% 权限处理针对 Linux/macOS root 环境的特殊限制进行了适配：root 下 --dangerously-skip-permissions 被禁止，改用 --permission-mode acceptEdits，该模式自动授权工作目录及其所有子目录的读写与 Bash 执行，符合代码评审场景需求
#%% Windows 或非 root 环境使用 --dangerously-skip-permissions，这是 Windows 上最稳定的权限策略
#%% _parse_stdout 依赖 CLI 严格返回包含 result 字段的 JSON 字典，任何格式偏离都会被明确拒绝
#%% 使用 --append-system-prompt 参数注入系统提示，避免了 user_prompt 与 system_prompt 拼接可能导致的语义混淆
#%% ---------- [Imperfections]
#%% 入口定位逻辑中 candidate.exists() 仅检查文件存在性，未处理无执行权限或文件损坏的极端情况，可能在后续 subprocess.run 时失败并抛出不够明确的错误；建议在 ai2json.py 的 exec 方法中捕获 FileNotFoundError 或 PermissionError 并给出更友好提示（与 codex.py 存在相同问题）
#%% is_root 检查使用 hasattr(os, 'getuid') 作为回退，在某些罕见的 Unix-like 系统上可能存在 getuid 存在但行为异常的情况，当前实现假设 getuid() 不抛出异常
#%% ----------

import os
import json
import shutil
from pathlib import Path
from ..ai2json import ThisAI2JSON

# Claude CLI 集成适配器
class Claude2JSON(ThisAI2JSON):
    def ai(self) -> str:
        return "claude"

    def _get_args(self, system_prompt: str, user_prompt: str) -> tuple[list[str], str | None]:
        # 定位 Claude 可执行入口，优先尝试 node + cli.js 直接调用，回退至 claude 命令
        claude_entry = shutil.which("claude")
        node_entry = shutil.which("node")
        args_prefix: list[str]
        if claude_entry and node_entry:
            # 尝试直接使用 node 执行 cli.js 以避免 wrapper 脚本开销
            candidate = Path(claude_entry).resolve().parent / "node_modules" / "@anthropic-ai" / "claude-code" / "cli.js"
            if candidate.exists():
                args_prefix = [node_entry, str(candidate)]
            else:
                args_prefix = [claude_entry]
        else:
            # 降级为裸字符串，依赖系统 PATH 解析
            args_prefix = ["claude"]

        # 构造命令行参数：--print 输出到 stdout，--output-format json 强制 JSON 格式，
        # --append-system-prompt 注入系统提示
        args = args_prefix + [
            "--print",
            "--output-format",
            "json",
            "--append-system-prompt",
            system_prompt,
        ]

        # 权限处理策略：
        # 1. Linux/macOS root 环境(UID=0)：--dangerously-skip-permissions 被明确禁止(安全限制)
        #    → 使用 --permission-mode acceptEdits 作为替代
        #    此模式自动授权：
        #      ✅ Read/Glob/Grep (工作目录 pwd 及其所有子目录)
        #      ✅ Bash 命令执行
        #      ✅ WebSearch/WebFetch
        #      ✅ Write/Edit 操作
        #      ❌ 父目录(../)及工作目录外的文件访问(仍需用户批准)
        #    工作目录定义：subprocess 执行时的 pwd，包含所有子目录但不包含父目录
        #    对代码评审场景完美适配：代码运行于 /data/Codebase/python，项目文件位于 projects/* 子目录下
        # 2. Windows/非 root 环境：--dangerously-skip-permissions 是最可靠的选择
        #    (Windows 上其他权限模式经常失效，此方式最稳定；适合 Windows 开发环境)
        # 3. 设计考量：
        #    a) 不使用 --allowed-tools：无通配符支持，需手动枚举，且随版本变化
        #    b) 不使用 --add-dir：当前工作目录已覆盖所有项目文件，无需额外授权
        #    c) acceptEdits 模式已满足需求，具备目录隔离安全性
        is_root = os.getuid() == 0 if hasattr(os, 'getuid') else False
        if is_root:
            # Linux/macOS root 环境：使用 acceptEdits 模式
            args.extend(["--permission-mode", "acceptEdits"])
        else:
            # Windows 或非 root 环境：使用 --dangerously-skip-permissions
            args.append("--dangerously-skip-permissions")

        args.append("-")  # 从 stdin 读取用户提示
        return args, user_prompt

    def _parse_stdout(self, stdout: str) -> tuple[str | None, str | None]:
        # 解析 Claude CLI 返回的 JSON 字典，提取 result 字段
        try:
            data = json.loads(stdout)
        except json.JSONDecodeError:
            return None, "[ERR] _parse_stdout: can't parse JSON from stdout"

        if not isinstance(data, dict):
            return None, "[ERR] _parse_stdout: not a dictionary"

        result = data.get("result")
        if not isinstance(result, str):
            return None, "[ERR] _parse_stdout: string <result> not found"

        result = result.strip()
        if not result:
            return None, "[ERR] _parse_stdout: <result> is empty"

        # 成功提取目标消息，其余字段（如 usage）将由后续流程处理
        return result, None