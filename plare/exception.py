class PlareException(Exception):
    pass


class LexingError(PlareException):
    pass


class ParserError(PlareException):
    pass


class ShiftReduceConflict(ParserError):
    pass


class ReduceReduceConflict(ParserError):
    pass


class ParsingError(PlareException):
    pass
