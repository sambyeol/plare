"""Plare exception hierarchy.

All exceptions raised by the Plare lexer and parser are subclasses of
``PlareException``, so callers can catch them with a single except clause when
they do not need to distinguish between construction errors and runtime errors.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from plare.token import Token


class PlareException(Exception):
    """Base class for all Plare errors."""


class LexingError(PlareException):
    """Raised by ``Lexer.lex`` when no pattern matches the remaining input.

    Attributes:
        message: Human-readable description including the offending character.
        lineno: 1-based line number of the failure position.
        offset: 0-based column offset of the failure position.
    """

    def __init__(self, message: str, lineno: int, offset: int) -> None:
        super().__init__(message)
        self.message = message
        self.lineno = lineno
        self.offset = offset

    def __str__(self) -> str:
        return f"Line {self.lineno}, col {self.offset}: {self.message}"


class ParserError(PlareException):
    """Raised during ``Parser.__init__`` when the grammar is invalid.

    Typical causes: an unresolvable reduce/reduce conflict, or a Goto action
    placed where an action action is expected (internal consistency violation).
    """


class ParsingError(PlareException):
    """Raised by ``Parser.parse`` when the token stream does not match the grammar.

    Attributes:
        token: The offending token, or ``None`` when end-of-input is unexpected.
        lineno: 1-based line number of the failure position.
        offset: 0-based column offset of the failure position.
        expected: Terminal token classes that would have been valid at this point.
    """

    def __init__(
        self,
        message: str,
        token: Token | None,
        lineno: int,
        offset: int,
        expected: list[type[Token]],
    ) -> None:
        super().__init__(message)
        self.token = token
        self.lineno = lineno
        self.offset = offset
        self.expected = expected

    def __str__(self) -> str:
        expected_names = ", ".join(cls.__name__ for cls in self.expected)
        loc = f"Line {self.lineno}, col {self.offset}"
        return f"{loc}: {self.args[0]}; expected: {expected_names}"
