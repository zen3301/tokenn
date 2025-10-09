from ..parser import TheParser

class CParser(TheParser):
    def language(self) -> str:
        return 'c'

    def extensions(self) -> list[str]:
        return ['.c', '.h']


