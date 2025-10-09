from ..parser import TheParser

class CppParser(TheParser):
    def language(self) -> str:
        return 'cpp'

    def extensions(self) -> list[str]:
        return ['.cpp', '.cc', '.cxx', '.hpp', '.hh', '.hxx']


