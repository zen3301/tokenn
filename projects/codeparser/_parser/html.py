from ..parser import TheParser

class HtmlParser(TheParser):
    def language(self) -> str:
        return 'html'

    def extensions(self) -> list[str]:
        return ['.html', '.htm']

    def _block_comment_prefix(self) -> str:
        return '<!--'

    def _block_comment_suffix(self) -> str:
        return '-->'

    def _line_comment_prefix(self) -> str:
        return ''
