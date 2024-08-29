from __future__ import annotations

import re
from typing import Callable, Generator

from plare.exception import LexingError
from plare.token import Token
from plare.utils import logger


class Lexer[T]:
    def __init__(
        self,
        patterns: dict[
            str,
            list[
                tuple[
                    str,
                    Callable[[str, T, int, int], Token | str | list[Token]]
                    | type[Token]
                    | str,
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
        ended = False

        while not ended:
            if len(src) == 0:
                ended = True

            patterns = self.patterns[var]

            for regex, pattern in patterns:
                match = regex.match(src)
                if match is None:
                    continue
                matched = match.group(0)
                logger.debug(
                    "Pattern matched: %s (from %s), %s", regex, var, repr(matched)
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
                            case list():
                                yield from token
                            case _:
                                var = token
                matched_lines = matched.split("\n")
                n_matched_new_lines = len(matched_lines) - 1
                lineno += n_matched_new_lines
                if n_matched_new_lines > 0:
                    offset = 0
                last_matched_line = matched_lines[-1]
                offset += len(last_matched_line)
                break
            else:
                if len(src) == 0:
                    continue
                raise LexingError(f"Unexpected character: {src[0]}", lineno, offset)
