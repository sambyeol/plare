from types import NoneType
from typing import Any

import pytest

from plare.exception import LexingError
from plare.lexer import Lexer
from plare.token import Token


class PLUS(Token):
    pass


class NUM(Token):
    value: int

    def __init__(self, value: str, *, lineno: int, offset: int) -> None:
        super().__init__(value, lineno=lineno, offset=offset)
        self.value = int(value)

    def __hash__(self) -> int:
        return hash(self.value) + super().__hash__()

    def __eq__(self, other: Any) -> bool:
        return (
            isinstance(other, self.__class__)
            and self.value == other.value
            and super().__eq__(other)
        )


class ID(Token):
    value: str

    def __init__(self, value: str, *, lineno: int, offset: int) -> None:
        super().__init__(value, lineno=lineno, offset=offset)
        self.value = value

    def __hash__(self) -> int:
        return hash(self.value) + super().__hash__()

    def __eq__(self, other: Any) -> bool:
        return (
            isinstance(other, self.__class__)
            and self.value == other.value
            and super().__eq__(other)
        )


def test_token_attributes():
    token = ID("x", lineno=1, offset=0)
    assert token.value == "x"
    assert token.lineno == 1
    assert token.offset == 0


def make_positive_integer_lexer():
    return Lexer(
        {
            "start": [
                (r"\+", PLUS),
                (r"", "digit"),
            ],
            "digit": [
                (r"\d+", NUM),
            ],
        },
        NoneType,
    )


def test_lex_positive_integer():
    lexer = make_positive_integer_lexer()
    tokens = list(lexer.lex("start", "+123"))
    assert len(tokens) == 2
    assert isinstance(tokens[0], PLUS)
    assert tokens[0].lineno == 1
    assert tokens[0].offset == 0
    assert isinstance(tokens[1], NUM)
    assert tokens[1].value == 123
    assert tokens[1].lineno == 1
    assert tokens[1].offset == 1


def test_lex_positive_integer_fail_on_tailing_plus():
    lexer = make_positive_integer_lexer()
    with pytest.raises(LexingError):
        list(lexer.lex("start", "+123+"))


class SPACE(Token):
    pass


def test_lex_multiple_tokens_for_single_match():
    lexer = Lexer(
        {
            "start": [
                (
                    r"[ \t\n]+",
                    lambda matched, state, lineno, offset: [
                        SPACE(c, lineno=lineno, offset=offset + i)
                        for i, c in enumerate(matched)
                    ],
                ),
            ]
        }
    )
    tokens = list(lexer.lex("start", " \t\n"))
    assert len(tokens) == 3
    assert isinstance(tokens[0], SPACE)
    assert tokens[0].lineno == 1
    assert tokens[0].offset == 0
    assert isinstance(tokens[1], SPACE)
    assert tokens[1].lineno == 1
    assert tokens[1].offset == 1
    assert isinstance(tokens[2], SPACE)
    assert tokens[2].lineno == 1
    assert tokens[2].offset == 2


class EOF(Token):
    pass


def test_lex_end_of_file():
    lexer = Lexer(
        {
            "start": [
                (r"\d+", NUM),
                (r"$", EOF),
            ]
        }
    )
    tokens = list(lexer.lex("start", "123"))
    assert len(tokens) == 2
    assert isinstance(tokens[0], NUM)
    assert tokens[0].value == 123
    assert tokens[0].lineno == 1
    assert tokens[0].offset == 0
    assert isinstance(tokens[1], EOF)
    assert tokens[1].lineno == 1
    assert tokens[1].offset == 3
