from ..parser import TheParser

class RustParser(TheParser):
    def language(self) -> str:
        return 'rust'

    def extensions(self) -> list[str]:
        return ['.rs']


