"""Tests for structured LexingError and ParsingError fields."""

from __future__ import annotations

import pytest

from plare.exception import LexingError, ParsingError
from plare.lexer import Lexer
from plare.parser import Parser
from plare.token import Token

type GrammarEntry[T] = (
    tuple[list[type[Token] | str], type[T] | None, list[int]]
    | tuple[list[type[Token] | str], type[T] | None, list[int], type[Token]]
)


# ---------------------------------------------------------------------------
# Token classes for the test grammar: Num "+" Num
# ---------------------------------------------------------------------------


class Num(Token):
    pass


class Plus(Token):
    pass


class Expr:
    def __init__(self, left: Num, right: Num) -> None:
        self.left = left
        self.right = right


# Grammar: expr → Num Plus Num
GRAMMAR: dict[str, list[GrammarEntry[Expr]]] = {
    "expr": [
        ([Num, Plus, Num], Expr, [0, 2]),
    ],
}


def make_tok(cls: type[Token], *, lineno: int = 1, offset: int = 0) -> Token:
    return cls("x", lineno=lineno, offset=offset)


# ---------------------------------------------------------------------------
# ParsingError — unexpected token
# ---------------------------------------------------------------------------


def test_parsing_error_unexpected_token_fields() -> None:
    """ParsingError carries the offending token, its position, and expected classes."""
    p: Parser[Expr] = Parser(GRAMMAR)
    wrong_tok = make_tok(Plus, lineno=3, offset=7)

    with pytest.raises(ParsingError) as exc_info:
        p.parse("expr", [wrong_tok])

    e = exc_info.value
    assert e.token is wrong_tok
    assert e.lineno == 3
    assert e.offset == 7
    assert Num in e.expected


def test_parsing_error_unexpected_token_str() -> None:
    """str(ParsingError) starts with the 'Line X, col Y:' prefix."""
    p: Parser[Expr] = Parser(GRAMMAR)
    wrong_tok = make_tok(Plus, lineno=2, offset=5)

    with pytest.raises(ParsingError) as exc_info:
        p.parse("expr", [wrong_tok])

    msg = str(exc_info.value)
    assert msg.startswith("Line 2, col 5:")
    assert "Num" in msg


# ---------------------------------------------------------------------------
# ParsingError — unexpected end of input
# ---------------------------------------------------------------------------


def test_parsing_error_truncated_input_expected_nonempty() -> None:
    """When input is too short, ParsingError.expected is non-empty."""
    p: Parser[Expr] = Parser(GRAMMAR)
    num_tok = make_tok(Num, lineno=1, offset=0)

    with pytest.raises(ParsingError) as exc_info:
        p.parse("expr", [num_tok])

    e = exc_info.value
    assert len(e.expected) > 0
    assert Plus in e.expected


def test_parsing_error_truncated_input_str() -> None:
    """str(ParsingError) for truncated input contains the expected class name."""
    p: Parser[Expr] = Parser(GRAMMAR)
    num_tok = make_tok(Num, lineno=1, offset=0)

    with pytest.raises(ParsingError) as exc_info:
        p.parse("expr", [num_tok])

    msg = str(exc_info.value)
    assert "Line " in msg
    assert "Plus" in msg


# ---------------------------------------------------------------------------
# LexingError — unrecognised character
# ---------------------------------------------------------------------------


def test_lexing_error_fields() -> None:
    """LexingError carries lineno, offset, and a readable message."""
    lexer: Lexer[None] = Lexer({"start": [("[0-9]+", Num)]})

    with pytest.raises(LexingError) as exc_info:
        list(lexer.lex("start", "123!456"))

    e = exc_info.value
    assert e.lineno >= 1
    assert e.offset >= 0
    assert "!" in e.message


def test_lexing_error_str_format() -> None:
    """str(LexingError) starts with 'Line X, col Y:'."""
    lexer: Lexer[None] = Lexer({"start": [("[0-9]+", Num)]})

    with pytest.raises(LexingError) as exc_info:
        list(lexer.lex("start", "!"))

    msg = str(exc_info.value)
    assert msg.startswith("Line 1, col 0:")
