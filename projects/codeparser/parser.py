#%% ---------- Reviewed by: claude
#%% $lang: 中文
#%% ---------- [Overview]
#%% 该文件实现了基于 tree-sitter 的通用代码解析器基类 TheParser，提供语言无关的语法树序列化（转为哈希化 JSON）、注释插入/提取操作，为各语言子类复用核心解析逻辑和注释处理接口。
#%% ---------- [Review]
#%% 代码逻辑严谨，语义与注释隔离策略清晰，接口设计完备覆盖解析与注释操作的核心路径。递归解析策略恰当，隐私保护（SHA256 哈希）和语义区分度（token 指纹+位置）兼顾。整体结构稳定，完成度高，可测试性良好，无阻塞性缺陷。注释管理对换行符的统一处理（转为 '\n' 并移除末尾换行）已在多处明确声明，调用方责任边界清晰。
#%% ---------- [Notes]
#%% parse() 通过 SHA256 哈希叶节点和捕获非命名 token 指纹+位置，确保语义区分度同时保护隐私；注释节点在递归时已跳过，满足「仅改注释时输出不变」的要求
#%% comment()/insert_comment()/extract_comments() 统一将换行符改为 '\n' 并移除末尾换行，调用方需自行恢复原格式；已在多处注释中明确说明
#%% block_comment()/line_comment() 在不支持对应注释类型时会回退到另一种类型（通过 force 参数控制），为跨语言兼容性提供灵活性
#%% extract_comments() 仅提取整行注释且带指定标签，刻意跳过行末内联注释和块注释，与 comment() 生成的内联注释形成正交设计
#%% _parse() 中的 node_to_dict() 递归深度受 Python 默认栈限制（约 1000 层），注释已明确说明不考虑极端嵌套输入
#%% ---------- [Imperfections]
#%% comment() 中 line < 0 或 line >= n 时抛出 ValueError，但 insert_comment() 中 line 超出范围时会被 clamp 到 [0, n]，两者边界处理不一致可能导致调用方混淆
#%% block_comment() 中当 suffix 出现在 comment 内容中时抛出异常，但提示「用户可用例如 '* /' 避开」，这要求调用方自行处理转义，缺乏内建转义逻辑可能在批量处理时引入脆弱性
#%% _extract_line_comment() 假定带标签注释从第 0 列开始以跳过内联注释,但未显式校验前导空格,如果源码缩进不规范(例如行首有空格但仍为整行注释)可能误判
#%% ----------

import json
import hashlib
from typing import Any
from tree_sitter import Parser as TSParser  # type: ignore
from tree_sitter_languages import get_language  # type: ignore
from .index import Parser # ParserFactory 在函数内部执行此导入以避免循环依赖

# 仅供语言特定子类内部使用，不属于公开 API
# 不要过度设计！例如极端的语法树深度，不必保留 Windows 的换行格式，可统一重组为 '\n'
# 需要 Python 3.10+
class TheParser(Parser):
    def __init__(self):
        # 使用 tree-sitter 初始化解析器
        # 子类必须让 language() 返回 tree_sitter_languages 的键，例如 'typescript'
        self._parser = TSParser()
        self._parser.set_language(get_language(self.language()))

    def parse(self, source: str) -> str:
        # 关键要求：
        # - 不同的源码语义必须产生不同的输出字符串
        # - 仅改动注释时应生成完全相同的输出字符串
        tree = self._parse(source)
        return json.dumps(tree, ensure_ascii=False, sort_keys=True, separators=(',', ':'))

    def _parse(self, source: str) -> Any:
        # 如有需要可由具体语言覆盖
        source_bytes = source.encode('utf-8')
        tree = self._parser.parse(source_bytes)
        root = tree.root_node

        def node_to_dict(node) -> dict[str, Any]:
            # 注意：此处不需考虑极端嵌套输入（递归深度超过 Python 递归上限约 1000 层）
            result: dict[str, Any] = {
                'type': node.type,
                'named': bool(node.is_named),
            }

            # 为命名叶子节点（标识符、数值、字符串等）提供隐私友好的哈希指纹
            has_named_child = any(c.is_named for c in node.children)
            if node.is_named and not has_named_child:
                start, end = node.start_byte, node.end_byte
                if end > start:
                    s = source_bytes[start:end]
                    result['value_meta'] = {
                        'length': end - start,
                        'value_hash': hashlib.sha256(s).hexdigest()[:32], # 128位哈希已足够可靠
                    }

            if node.child_count:
                children = []
                token_hashes: list[str] = []
                token_positions: list[int] = []
                named_index = 0
                for child in node.children:
                    if child.is_named:
                        if 'comment' in child.type.lower():
                            continue
                        children.append(node_to_dict(child))
                        named_index += 1
                    else:
                        # 跳过未命名的注释 token，确保注释改动不影响输出
                        if 'comment' in child.type.lower():
                            continue
                        # 捕获运算符/标点等非命名 token 的指纹，并记录其相对位置（位于第几个命名子节点之前）
                        start, end = child.start_byte, child.end_byte
                        if end > start:
                            token_hashes.append(hashlib.sha256(source_bytes[start:end]).hexdigest()[:32])
                            token_positions.append(named_index)
                if children:
                    result['children'] = children
                if token_hashes:
                    result['tokens'] = token_hashes
                    result['token_positions'] = token_positions
            return result

        # 注意：不得直接嵌入源码文本
        return {
            'language': self.language(),
            'version': 1,
            'tree': node_to_dict(root),
        }

    def comment(self, source: str, line: int, comment: str, tag = '') -> str:
        # 将注释追加到指定行末尾；line < 0 表示自末尾反向计数
        lines = source.splitlines()
        n = len(lines)
        if line < 0:
            line += n
        if line < 0 or line >= n:
            raise ValueError(f"Line {line} is out of range")
        comment = self.line_comment(comment, tag)
        if comment is None:
            raise ValueError("Line comment is not supported")
        lines[line] += ' ' + comment
        return '\n'.join(lines) # 注意：统一改用 '\n' 并移除末尾换行，调用方需自行处理

    def insert_comment(self, source: str, line: int, comment: str, tag = '', block = False) -> str:
        # 在给定行插入注释；line < 0 自末尾反向计数
        comment = self.block_comment(comment, tag) if block else self.line_comment(comment, tag)
        if comment is None:
            raise ValueError("Comment is not supported")
        lines = source.splitlines()
        n = len(lines)
        if line < 0:
            line += n
        line = max(0, min(line, n))  # 允许在末尾插入
        lines.insert(line, comment)
        return '\n'.join(lines) # 注意：统一改用 '\n' 并移除末尾换行，调用方需自行处理

    def block_comment(self, comment: str, tag = '', force = False) -> str | None:
        # 如有需要可由具体语言覆盖
        prefix = self._block_comment_prefix()
        if prefix == '':
            return None if force else self.line_comment(comment, tag, True)
        suffix = self._block_comment_suffix()
        if suffix in comment: # 不要在此处转义，用户可用例如 '* /' 避开
            raise ValueError(f"Block comment suffix '{suffix}' found in comment")
        space = '\n' if '\n' in comment else ' '
        return prefix + tag + space + comment + space + suffix

    def line_comment(self, comment: str, tag = '', force = False) -> str | None:
        # 如有需要可由具体语言覆盖
        prefix = self._line_comment_prefix()
        if prefix == '':
            return None if force else self.block_comment(comment, tag, True)
        lines = comment.split('\n')
        for i, line in enumerate(lines):
            if line.strip() != '':
                line = prefix + tag + ' ' + line
            lines[i] = line
        return '\n'.join(lines)

    def extract_comments(self, source: str, tag: str, first = 0, last = -1) -> tuple[list[str], str]:
        # 提取源码中带标签的注释；仅支持整行行注释，忽略块注释。此方法独立于此前的注释插入，不保证 round-trip
        lines = source.splitlines()
        n = len(lines)
        if last < 0:
            last += n
        elif last >= n:
            last = n - 1
        if last < first:
            return [], source

        next = last + 1
        comments = []
        kept: list[str] = []
        kept.extend(lines[0:first])
        for i in range(first, next):
            line = lines[i]
            # 有意跳过行尾内联注释，仅捕获整行注释
            comment = self._extract_line_comment(line.strip(), tag)
            if comment is None:
                kept.append(line)
            else:
                comments.append(comment)
        kept.extend(lines[next:])
        return comments, '\n'.join(kept) # 注意：统一改用 '\n' 并移除末尾换行，调用方需自行处理

    def _extract_line_comment(self, line: str, tag: str) -> str | None:
        # 仅匹配整行注释（从第 0 列开始）；由 block_comment() 生成的多行内容保持不变
        # 需要前导空格的标签应自行包含空格（例如 ' Author:')
        line = line.strip()
        # 假定带标签的注释从第 0 列开始，以刻意跳过 comment() 追加的内联注释
        prefix = self._line_comment_prefix()
        if prefix != '': # 行注释示例：// Author: Elon Musk
            prefix += tag
            if line.startswith(prefix):
                return line[len(prefix):].strip() # 返回 'Elon Musk'
            return None

        prefix = self._block_comment_prefix()
        if prefix != '': # 仅处理单行块注释，例如 /* Author: Elon Musk */
            prefix += tag
            suffix = self._block_comment_suffix()
            if line.startswith(prefix) and line.endswith(suffix):
                return line[len(prefix):-len(suffix)].strip() # 返回 'Elon Musk'
            return None
        return None

    def _block_comment_prefix(self) -> str:
        # 如有需要可由具体语言覆盖
        return '/*'

    def _block_comment_suffix(self) -> str:
        # 如有需要可由具体语言覆盖
        return '*/'

    def _line_comment_prefix(self) -> str:
        # 如有需要可由具体语言覆盖
        return '//'