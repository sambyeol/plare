class PlareException(Exception):
    pass


class LexingError(PlareException):
    pass


class ParserError(PlareException):
    pass


class ParsingError(PlareException):
    pass
