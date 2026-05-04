"""Regex-driven, stateful lexer for the Plare framework.

A ``Lexer`` is configured with a dictionary that maps *state names* to ordered
lists of ``(pattern, handler)`` pairs.  At each position in the input the lexer
tries each pattern for the current state in order; the first match wins.

Handler types
-------------
* ``str`` — transition to a new state without emitting a token.
* ``type[Token]`` subclass — construct one token from the matched text and emit
  it, then stay in the current state.
* ``Callable[[str, T, int, int], Token | str | list[Token]]`` — a function
  receiving ``(matched_text, user_state, lineno, offset)`` that can emit a
  single token, a list of tokens, or return a string to transition states.

The optional ``state_factory`` argument is called once per ``lex()`` call to
produce a mutable *user state* object that is threaded through all callable
handlers.  If omitted, the user state is ``None``.
"""

from __future__ import annotations

import re
from typing import Callable, Generator

from plare.exception import LexingError
from plare.token import Token
from plare.utils import logger


class Lexer[T]:
    """Stateful lexer that tokenises a string according to named pattern states.

    Args:
        patterns: A dict mapping state name → ordered list of
            ``(regex_string, handler)`` pairs.  Patterns are compiled once at
            construction time.
        state_factory: Zero-argument callable that produces the initial user
            state object passed to callable handlers.  Defaults to
            ``lambda: None``.

    Example::

        lexer = Lexer({
            "start": [
                (r"\\d+", NUM),
                (r"\\+",  PLUS),
                (r" +",   "start"),  # skip whitespace by re-entering start
            ]
        })
        tokens = list(lexer.lex("start", "1 + 2"))
    """

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
        """Tokenise ``src`` starting in state ``var``.

        Scans ``src`` left-to-right.  At each position, the patterns for the
        current state are tried in order; the first match is consumed and its
        handler is invoked.  Unmatched input raises ``LexingError``.

        ``lineno`` and ``offset`` are tracked across newlines: ``lineno`` is
        1-based, ``offset`` resets to 0 at the start of each new line.

        Args:
            var: Name of the initial lexer state (must be a key in ``patterns``).
            src: Source string to tokenise.

        Yields:
            ``Token`` instances in source order.

        Raises:
            LexingError: When no pattern matches the next character.
        """
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
