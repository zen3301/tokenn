from ..parser import TheParser

class TypescriptParser(TheParser):
    def language(self) -> str:
        return 'typescript'

    def extensions(self) -> list[str]:
        return ['.ts', '.js']
