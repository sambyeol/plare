class PlareException(Exception):
    pass


class LexingError(PlareException):
    pass


class ParserError(PlareException):
    pass


class ShiftReduceConflict(ParserError):
    pass


class ReduceReduceConflict(ParserError):
    def __init__(self, left: str, precedence: int) -> None:
        self.left = left
        self.precedence = precedence


class ParsingError(PlareException):
    pass
