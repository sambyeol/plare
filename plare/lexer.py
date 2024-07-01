from __future__ import annotations

import re
from typing import Any, Callable, Generator

from plare.exception import LexingError


class Token:
    def __init__(self, value: str, *, lineno: int, offset: int) -> None:
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


class LexingState:
    pass


type Pattern = Callable[[str, LexingState, int, int], Token | str] | type[Token] | str


class Lexer:
    def __init__(
        self, patterns: dict[str, list[tuple[str, Pattern]]], state: LexingState
    ) -> None:
        self.patterns = {
            token: [(re.compile(r), pattern) for r, pattern in patterns[token]]
            for token in patterns
        }
        self.state = state

    def lex(self, src: str, entry: str) -> Generator[Token, None, None]:
        lineno = 1
        offset = 0

        while len(src) > 0:
            patterns = self.patterns[entry]

            for regex, pattern in patterns:
                match = regex.match(src)
                if match is not None:
                    matched = match.group(0)
                    src = src[len(matched) :]
                    match pattern:
                        case str():
                            entry = pattern
                        case type():
                            yield pattern(matched, lineno=lineno, offset=offset)
                        case _:
                            token = pattern(matched, self.state, lineno, offset)
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
