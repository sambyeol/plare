"""Tests for the 4-tuple prec_token grammar extension (yacc-style %prec).

Verifies that a production's effective precedence can be overridden by
supplying a prec_token as the 4th element of a grammar tuple, and that
this override changes conflict resolution relative to the 3-tuple form.
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
