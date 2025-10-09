from ..parser import TheParser

class CSharpParser(TheParser):
    def language(self) -> str:
        return 'c_sharp'

    def extensions(self) -> list[str]:
        return ['.cs']


