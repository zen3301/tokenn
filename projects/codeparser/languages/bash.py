from ..parser import TheParser

class BashParser(TheParser):
    def language(self) -> str:
        return 'bash'

    def extensions(self) -> list[str]:
        return ['.sh', '.bash']

    def _block_comment_prefix(self) -> str:
        return ''

    def _block_comment_suffix(self) -> str:
        return ''

    def _line_comment_prefix(self) -> str:
        return '#'
