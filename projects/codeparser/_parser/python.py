from ..parser import TheParser

class PythonParser(TheParser):
    def language(self) -> str:
        return 'python'

    def extensions(self) -> list[str]:
        return ['.py']

    def _block_comment_prefix(self) -> str:
        return '"""'

    def _block_comment_suffix(self) -> str:
        return '"""'

    def _line_comment_prefix(self) -> str:
        return '#'
