"""Tests for lexer and parser error reporting."""

from __future__ import annotations

from pathlib import Path

import pytest

from plare.exception import LexingError, ParserError, ParsingError
from plare.lexer import Lexer
from plare.parser import EOS, Parser
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
# ParserError — undefined nonterminal
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("use_cache", [False, True])
@pytest.mark.parametrize(
    "right", [["term"], [Num, "term"]], ids=["leading", "after-terminal"]
)
def test_parser_error_undefined_nonterminal(
    right: list[type[Token] | str], use_cache: bool, tmp_path: Path
) -> None:
    """Construction names the missing nonterminal and its referring rule."""
    cache_dir = tmp_path if use_cache else None

    with pytest.raises(ParserError) as exc_info:
        Parser[Expr]({"expr": [(right, None, [0])]}, cache_dir=cache_dir)

    message = str(exc_info.value)
    assert "'term'" in message
    assert "'expr'" in message
    if cache_dir is not None:
        assert not list(cache_dir.iterdir())


# ---------------------------------------------------------------------------
# ParsingError — unregistered entry point
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("use_cache", [False, True])
def test_unknown_start_rule(use_cache: bool, tmp_path: Path) -> None:
    """Both built and cached parsers identify the requested start rule."""
    cache_dir = tmp_path if use_cache else None
    if use_cache:
        Parser(GRAMMAR, cache_dir=cache_dir)
    parser = Parser(GRAMMAR, cache_dir=cache_dir)
    assert parser.cache_hit is use_cache

    with pytest.raises(ParsingError, match=r"Unknown start rule 'typo'") as exc_info:
        parser.parse("typo", [])

    error = exc_info.value
    assert error.token is None
    assert error.lineno == 0
    assert error.offset == 0
    assert error.expected == []

    tokens = [
        make_tok(kind, offset=offset) for offset, kind in enumerate((Num, Plus, Num))
    ]
    tokens.append(EOS("", lineno=1, offset=3))
    assert isinstance(parser.parse("expr", tokens), Expr)


# ---------------------------------------------------------------------------
# ParsingError — unexpected token
# ---------------------------------------------------------------------------


def test_parsing_error_unexpected_token_fields() -> None:
    """ParsingError carries the offending token, its position, and expected classes."""
    p: Parser[Expr] = Parser(GRAMMAR, cache_dir=None)
    wrong_tok = make_tok(Plus, lineno=3, offset=7)

    with pytest.raises(ParsingError) as exc_info:
        p.parse("expr", [wrong_tok, EOS("", lineno=3, offset=8)])

    e = exc_info.value
    assert e.token is wrong_tok
    assert e.lineno == 3
    assert e.offset == 7
    assert Num in e.expected


def test_parsing_error_unexpected_token_str() -> None:
    """str(ParsingError) starts with the 'Line X, col Y:' prefix."""
    p: Parser[Expr] = Parser(GRAMMAR, cache_dir=None)
    wrong_tok = make_tok(Plus, lineno=2, offset=5)

    with pytest.raises(ParsingError) as exc_info:
        p.parse("expr", [wrong_tok, EOS("", lineno=2, offset=6)])

    msg = str(exc_info.value)
    assert msg.startswith("Line 2, col 5:")
    assert "Num" in msg


# ---------------------------------------------------------------------------
# ParsingError — unexpected end of input
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("source", "position", "expected"),
    [
        ("\n17", (2, 2), Plus),
        ("\n17+", (2, 3), Num),
        ("\n17+  \n", (3, 0), Num),
        ("", (1, 0), Num),
    ],
)
def test_parsing_error_reports_position_of_unexpected_eos(
    source: str, position: tuple[int, int], expected: type[Token]
) -> None:
    """A lexer-supplied EOS reports the actual end of the source."""
    lexer: Lexer[None] = Lexer(
        {"start": [(r"\s+", "start"), (r"\d+", Num), (r"\+", Plus), (r"\Z", EOS)]}
    )
    p: Parser[Expr] = Parser(GRAMMAR, cache_dir=None)

    with pytest.raises(ParsingError, match="Unexpected end of input") as exc_info:
        p.parse("expr", lexer.lex("start", source))

    error = exc_info.value
    assert error.token is None
    assert (error.lineno, error.offset) == position
    assert expected in error.expected
    assert expected.__name__ in str(error)


@pytest.mark.parametrize(
    ("tokens", "position"),
    [
        ([], (1, 0)),
        ([make_tok(Num, lineno=2, offset=3)], (2, 3)),
    ],
    ids=["empty-stream", "complete-expression"],
)
def test_parsing_error_requires_explicit_eos(
    tokens: list[Token], position: tuple[int, int]
) -> None:
    """Exhaustion without EOS fails even after a complete expression."""
    p = Parser[Token]({"expr": [([Num], None, [0])]}, cache_dir=None)

    with pytest.raises(
        ParsingError, match="Token stream ended without EOS"
    ) as exc_info:
        p.parse("expr", tokens)

    error = exc_info.value
    assert error.token is None
    assert (error.lineno, error.offset) == position


@pytest.mark.parametrize("trailing_kind", [Num, EOS])
def test_parsing_error_rejects_tokens_after_eos(trailing_kind: type[Token]) -> None:
    """EOS must occur exactly once, at the end of the token stream."""
    p: Parser[Expr] = Parser(GRAMMAR, cache_dir=None)
    trailing = make_tok(trailing_kind, lineno=2, offset=7)
    tokens = [make_tok(kind) for kind in (Num, Plus, Num)]
    tokens.extend([EOS("", lineno=2, offset=3), trailing])

    with pytest.raises(ParsingError, match="Unexpected token after EOS") as exc_info:
        p.parse("expr", tokens)

    error = exc_info.value
    assert error.token is trailing
    assert (error.lineno, error.offset) == (2, 7)


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
