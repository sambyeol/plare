from __future__ import annotations

import re
from typing import Any, Callable, Generator

from plare.exception import LexingError
from plare.utils import logger


class Token:
    def __init__(self, value: str, *, lineno: int, offset: int) -> None:
        logger.debug(
            "Token created: %s(%s) @ (%s, %s)",
            self.__class__.__name__,
            value,
            lineno,
            offset,
        )
        self.lineno = lineno
        self.offset = offset

    def __hash__(self) -> int:
        return hash(self.lineno) + hash(self.offset)

    def __eq__(self, other: Any) -> bool:
        return (
            isinstance(other, self.__class__)
            and self.lineno == other.lineno
            and self.offset == other.offset
        )


class EOF(Token):
    pass


class EPSILON(Token):
    pass


class Lexer[T]:
    def __init__(
        self,
        patterns: dict[
            str,
            list[
                tuple[
                    str, Callable[[str, T, int, int], Token | str] | type[Token] | str
                ]
            ],
        ],
        state_factory: Callable[[], T],
    ) -> None:
        self.patterns = {
            token: [(re.compile(r), pattern) for r, pattern in patterns[token]]
            for token in patterns
        }
        self.state_factory = state_factory

    def lex(self, src: str, entry: str) -> Generator[Token]:
        state = self.state_factory()
        lineno = 1
        offset = 0

        while len(src) > 0:
            patterns = self.patterns[entry]

            for regex, pattern in patterns:
                match = regex.match(src)
                if match is None:
                    continue
                matched = match.group(0)
                logger.debug(
                    "Pattern, matched: %s (from %s), %s",
                    regex,
                    entry,
                    matched,
                )
                src = src[len(matched) :]
                match pattern:
                    case str():
                        entry = pattern
                    case type():
                        yield pattern(matched, lineno=lineno, offset=offset)
                    case _:
                        token = pattern(matched, state, lineno, offset)
                        match token:
                            case Token():
                                yield token
                            case _:
                                entry = token
                newlines = matched.count("\n")
                lineno += newlines
                if newlines > 0:
                    offset = 0
                offset = len(matched) - matched.rfind("\n")
                break
            else:
                raise LexingError(f"Unexpected character: {src[0]}", lineno, offset)
        yield EOF(src, lineno=lineno, offset=offset)
