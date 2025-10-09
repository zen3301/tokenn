from ..parser import TheParser

class GoParser(TheParser):
    def language(self) -> str:
        return 'go'

    def extensions(self) -> list[str]:
        return ['.go']


