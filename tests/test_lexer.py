from types import NoneType
from typing import Any

import pytest

from plare.exception import LexingError
from plare.lexer import Lexer
from plare.parser import EOF, Token


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
    assert len(tokens) == 3
    assert isinstance(tokens[0], PLUS)
    assert tokens[0].lineno == 1
    assert tokens[0].offset == 0
    assert isinstance(tokens[1], NUM)
    assert tokens[1].value == 123
    assert tokens[1].lineno == 1
    assert tokens[1].offset == 1
    assert isinstance(tokens[2], EOF)


def test_lex_positive_integer_fail_on_tailing_plus():
    lexer = make_positive_integer_lexer()
    with pytest.raises(LexingError):
        list(lexer.lex("start", "+123+"))
