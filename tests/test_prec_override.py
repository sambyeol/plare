"""Tests for yacc-style conflict resolution: prec_token override and R/R definition order.

Covers two orthogonal features:
- 4-tuple prec_token (yacc %prec): override the effective precedence of a production.
- R/R definition order: when two productions compete with equal precedence, the
  earlier-defined production wins silently instead of raising ParserError.
"""

from __future__ import annotations

import pytest

from plare.parser import Parser
from plare.token import Token

# ---------------------------------------------------------------------------
# Token definitions
# ---------------------------------------------------------------------------


class NUM(Token):
    """Integer literal — stores the numeric value for AST construction."""

    def __init__(self, value: str, *, lineno: int, offset: int) -> None:
        self.value = int(value)
        self.lineno = lineno
        self.offset = offset


class MINUS(Token):
    """Binary/unary minus — precedence 1, left-associative."""

    precedence = 1
    associative = "left"


class STAR(Token):
    """Multiplication — precedence 2, left-associative."""

    precedence = 2
    associative = "left"


class UMINUS(Token):
    """Pseudo-token used exclusively as a prec_token override for unary minus.

    Never emitted by any lexer.  Its higher precedence ensures that a unary-
    minus production overrides the rightmost-terminal scan precedence.
    """

    precedence = 3
    associative = "right"


# ---------------------------------------------------------------------------
# AST nodes
# ---------------------------------------------------------------------------


class Expr:
    pass


class Num(Expr):
    def __init__(self, tok: NUM) -> None:
        self.value = tok.value


class Neg(Expr):
    def __init__(self, operand: Expr) -> None:
        self.operand = operand


class Mul(Expr):
    def __init__(self, left: Expr, right: Expr) -> None:
        self.left = left
        self.right = right


# ---------------------------------------------------------------------------
# Parser factories
# ---------------------------------------------------------------------------


def parser_with_prec_override() -> Parser[Expr]:
    """Grammar with unary-minus production using UMINUS (prec=3) as prec_token."""
    return Parser(
        {
            "expr": [
                ([NUM], Num, [0]),
                (["expr", STAR, "expr"], Mul, [0, 2]),
                ([MINUS, "expr"], Neg, [1], UMINUS),
            ]
        }
    )


def parser_without_prec_override() -> Parser[Expr]:
    """Same grammar but unary minus derives precedence from MINUS (prec=1)."""
    return Parser(
        {
            "expr": [
                ([NUM], Num, [0]),
                (["expr", STAR, "expr"], Mul, [0, 2]),
                ([MINUS, "expr"], Neg, [1]),
            ]
        }
    )


def token_stream() -> list[Token]:
    """Token stream for the expression  -3 * 4."""
    return [
        MINUS("-", lineno=1, offset=0),
        NUM("3", lineno=1, offset=1),
        STAR("*", lineno=1, offset=2),
        NUM("4", lineno=1, offset=3),
    ]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_prec_override_unary_minus_binds_tighter_than_mul() -> None:
    """prec_token=UMINUS (prec=3) makes unary minus bind tighter than STAR (prec=2).

    Input: -3 * 4

    With override: the unary-minus production has effective prec=3, which
    beats the STAR lookahead prec=2, so the parser reduces MINUS expr to
    Neg(3) first, then multiplies: Mul(Neg(3), 4).

    Without override: the unary-minus production inherits MINUS.prec=1, which
    is lower than STAR.prec=2, so the parser shifts STAR and reduces the
    multiplication first: Neg(Mul(3, 4)).
    """
    result_with = parser_with_prec_override().parse("expr", token_stream())
    assert isinstance(
        result_with, Mul
    ), f"expected Mul, got {type(result_with).__name__}"
    assert isinstance(
        result_with.left, Neg
    ), f"expected left child Neg, got {type(result_with.left).__name__}"
    assert isinstance(result_with.left.operand, Num)
    assert result_with.left.operand.value == 3
    assert isinstance(result_with.right, Num)
    assert result_with.right.value == 4

    result_without = parser_without_prec_override().parse("expr", token_stream())
    assert isinstance(
        result_without, Neg
    ), f"expected Neg, got {type(result_without).__name__}"
    assert isinstance(result_without.operand, Mul)


# ---------------------------------------------------------------------------
# R/R definition order
# ---------------------------------------------------------------------------


class Lit(Token):
    """Single literal token with no precedence."""


class FirstResult:
    def __init__(self, tok: Lit) -> None:
        self.tok = tok


class SecondResult:
    def __init__(self, tok: Lit) -> None:
        self.tok = tok


def test_rr_equal_precedence_first_defined_wins() -> None:
    """Earlier-defined production wins on equal-precedence R/R conflict.

    Two non-terminals (first_val, second_val) both reduce from a single Lit
    token with zero precedence, producing an R/R conflict in the merged LR(0)
    state.  The grammar entry non-terminal can use either.

    Without definition-order tie-breaking, Parser construction would raise
    ParserError.  With it, first_val (defined earlier, lower definition_index)
    wins, so the reduction always produces FirstResult.
    """
    grammar: dict = {
        "result": [
            (["first_val"], FirstResult, [0]),
            (["second_val"], SecondResult, [0]),
        ],
        "first_val": [([Lit], None, [0])],
        "second_val": [([Lit], None, [0])],
    }
    parser = Parser(grammar)
    result = parser.parse("result", [Lit("x", lineno=1, offset=0)])
    assert isinstance(
        result, FirstResult
    ), f"expected FirstResult (first-defined), got {type(result).__name__}"
