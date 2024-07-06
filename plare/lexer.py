from __future__ import annotations

import re
from typing import Callable, Generator

from plare.exception import LexingError
from plare.parser import EOF
from plare.token import Token
from plare.utils import logger


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
        state_factory: Callable[[], T] = lambda: None,
    ) -> None:
        self.patterns = {
            token: [(re.compile(r), pattern) for r, pattern in patterns[token]]
            for token in patterns
        }
        self.state_factory = state_factory
        logger.info("Lexer created")

    def lex(self, var: str, src: str) -> Generator[Token]:
        state = self.state_factory()
        lineno = 1
        offset = 0

        while len(src) > 0:
            patterns = self.patterns[var]

            for regex, pattern in patterns:
                match = regex.match(src)
                if match is None:
                    continue
                matched = match.group(0)
                logger.debug(
                    "Pattern, matched: %s (from %s), %s",
                    regex,
                    var,
                    matched,
                )
                src = src[len(matched) :]
                match pattern:
                    case str():
                        var = pattern
                    case type():
                        yield pattern(matched, lineno=lineno, offset=offset)
                    case _:
                        token = pattern(matched, state, lineno, offset)
                        match token:
                            case Token():
                                yield token
                            case _:
                                var = token
                newlines = matched.count("\n")
                lineno += newlines
                if newlines > 0:
                    offset = 0
                offset = len(matched) - matched.rfind("\n")
                break
            else:
                raise LexingError(f"Unexpected character: {src[0]}", lineno, offset)
        yield EOF(src, lineno=lineno, offset=offset)
