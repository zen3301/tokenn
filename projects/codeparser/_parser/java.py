from ..parser import TheParser

class JavaParser(TheParser):
    def language(self) -> str:
        return 'java'

    def extensions(self) -> list[str]:
        return ['.java']


