"""Base token class for the Plare lexer/parser framework.

Every token class used in a grammar must subclass ``Token``.  Token *classes*
(not instances) serve as grammar symbols inside ``Parser``; the parser never
compares token instances directly — it dispatches on ``type(token)``.
"""

from typing import Any, Literal

from plare.utils import logger

type assoc = Literal["left", "right"]
"""Associativity direction for operator-precedence conflict resolution.

``"left"``  — left-associative: ``a + b + c`` parses as ``(a + b) + c``.
``"right"`` — right-associative: ``a = b = c`` parses as ``a = (b = c)``.
"""


class Token:
    """Base class for all tokens produced by ``Lexer`` and consumed by ``Parser``.

    Subclass ``Token`` to define the terminal symbols of your grammar.

    Class-level attributes (set on subclasses, not instances):

    Attributes:
        precedence: Operator precedence level.  ``0`` means no precedence is
            assigned.  Positive values are used for conventional precedence
            (higher wins); negative values are also accepted by the conflict
            resolver.  Used during shift/reduce and reduce/reduce conflict
            resolution in ``Parser.__init__``.
        associative: Tie-breaker when two operators share the same precedence.
            Defaults to ``"left"``.

    Instance attributes (set in ``__init__``):

    Attributes:
        lineno: 1-based source line number of the token's first character.
        offset: 0-based column offset of the token's first character.

    Hash and equality contract:
        Two ``Token`` instances are considered equal when they are of the same
        class *and* share the same ``(lineno, offset)`` position.  This is an
        identity-by-source-position contract — it is intentional and does *not*
        compare token values.  The parser itself only cares about token *classes*,
        not instances, so this contract is used only in tests and edge-case
        bookkeeping, not in the core parse loop.  The hash incorporates the token
        class, so instances of different subclasses at the same source position
        have different hashes.
    """

    associative: assoc = "right"
    precedence: int = 0

    def __init__(self, value: str, *, lineno: int, offset: int) -> None:
        logger.debug(
            "Token created: %s(%s) @ (%s, %s)",
            self.__class__.__name__,
            repr(value),
            lineno,
            offset,
        )
        self.lineno = lineno
        self.offset = offset

    def __hash__(self) -> int:
        return hash((type(self), self.lineno, self.offset))

    def __eq__(self, other: Any) -> bool:
        return (
            isinstance(other, self.__class__)
            and self.lineno == other.lineno
            and self.offset == other.offset
        )
