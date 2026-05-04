"""Plare exception hierarchy.

All exceptions raised by the Plare lexer and parser are subclasses of
``PlareException``, so callers can catch them with a single except clause when
they do not need to distinguish between construction errors and runtime errors.
"""


class PlareException(Exception):
    """Base class for all Plare errors."""


class LexingError(PlareException):
    """Raised by ``Lexer.lex`` when no pattern matches the remaining input.

    Args:
        message: Human-readable description including the offending character.
        lineno: 1-based line number of the failure position.
        offset: 0-based column offset of the failure position.
    """


class ParserError(PlareException):
    """Raised during ``Parser.__init__`` when the grammar is invalid.

    Typical causes: an unresolvable reduce/reduce conflict, or a Goto action
    placed where an action action is expected (internal consistency violation).
    """


class ParsingError(PlareException):
    """Raised by ``Parser.parse`` when the token stream does not match the grammar.

    Typical causes: an unexpected token class, or premature end of input.
    """
