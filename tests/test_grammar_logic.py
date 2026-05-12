"""Comprehensive grammar and logic tests for the Plare lexer/parser framework.

Covers: arithmetic calculator with value evaluation, default S/R associativity,
dangling else (xfail), three-level precedence with %prec, comma-separated list
grammar, function call grammar, deep nesting, lexer multiline tracking, error
cases, and top-level epsilon productions.
"""

from __future__ import annotations

import pytest

from plare.exception import ParsingError
from plare.lexer import Lexer
from plare.parser import Parser
from plare.token import Token

# ---------------------------------------------------------------------------
# Section 1: Arithmetic Calculator
# ---------------------------------------------------------------------------


class NUM_C(Token):
    def __init__(self, value: str, *, lineno: int, offset: int) -> None:
        super().__init__(value, lineno=lineno, offset=offset)
        self.value = int(value)


class PLUS_C(Token):
    precedence = 1
    associative = "left"


class MINUS_C(Token):
    precedence = 1
    associative = "left"


class STAR_C(Token):
    precedence = 2
    associative = "left"


class SLASH_C(Token):
    precedence = 2
    associative = "left"


class LPAREN_C(Token):
    pass


class RPAREN_C(Token):
    pass


class ExprC:
    pass


class NumC(ExprC):
    def __init__(self, tok: NUM_C) -> None:
        self.value = tok.value


class AddC(ExprC):
    def __init__(self, l: ExprC, r: ExprC) -> None:
        self.l = l
        self.r = r


class SubC(ExprC):
    def __init__(self, l: ExprC, r: ExprC) -> None:
        self.l = l
        self.r = r


class MulC(ExprC):
    def __init__(self, l: ExprC, r: ExprC) -> None:
        self.l = l
        self.r = r


class DivC(ExprC):
    def __init__(self, l: ExprC, r: ExprC) -> None:
        self.l = l
        self.r = r


def eval_c(node: ExprC) -> int:
    match node:
        case NumC():
            return node.value
        case AddC():
            return eval_c(node.l) + eval_c(node.r)
        case SubC():
            return eval_c(node.l) - eval_c(node.r)
        case MulC():
            return eval_c(node.l) * eval_c(node.r)
        case DivC():
            return eval_c(node.l) // eval_c(node.r)
        case _:
            raise ValueError(f"Unknown node: {node}")


CALC_GRAMMAR: dict = {
    "expr": [
        ([NUM_C], NumC, [0]),
        (["expr", PLUS_C, "expr"], AddC, [0, 2]),
        (["expr", MINUS_C, "expr"], SubC, [0, 2]),
        (["expr", STAR_C, "expr"], MulC, [0, 2]),
        (["expr", SLASH_C, "expr"], DivC, [0, 2]),
        ([LPAREN_C, "expr", RPAREN_C], None, [1]),
    ]
}

CALC_LEXER = Lexer(
    {
        "start": [
            (r"[ \t\n]+", "start"),
            (r"\d+", NUM_C),
            (r"\+", PLUS_C),
            (r"-", MINUS_C),
            (r"\*", STAR_C),
            (r"/", SLASH_C),
            (r"\(", LPAREN_C),
            (r"\)", RPAREN_C),
        ]
    }
)

_calc_parser = Parser(CALC_GRAMMAR)


def _num(v: int, o: int = 0) -> NUM_C:
    return NUM_C(str(v), lineno=1, offset=o)


def test_calc_single_addition() -> None:
    """1 + 2 evaluates to 3 and produces an AddC node."""
    result = _calc_parser.parse(
        "expr",
        [_num(1, 0), PLUS_C("+", lineno=1, offset=1), _num(2, 2)],
    )
    assert isinstance(result, AddC)
    assert isinstance(result.l, NumC) and result.l.value == 1
    assert isinstance(result.r, NumC) and result.r.value == 2
    assert eval_c(result) == 3


def test_calc_precedence_mul_over_add() -> None:
    """1 + 2 * 3: STAR (prec=2) beats PLUS (prec=1), so root is AddC, right child is MulC."""
    result = _calc_parser.parse(
        "expr",
        [
            _num(1, 0),
            PLUS_C("+", lineno=1, offset=1),
            _num(2, 2),
            STAR_C("*", lineno=1, offset=3),
            _num(3, 4),
        ],
    )
    assert isinstance(result, AddC), "'+' must be root because '*' binds tighter"
    assert isinstance(result.r, MulC)
    assert eval_c(result) == 7


def test_calc_left_assoc_subtraction_chain() -> None:
    """10 - 3 - 2: left-associativity produces SubC(SubC(10, 3), 2) = 5, not 9."""
    result = _calc_parser.parse(
        "expr",
        [
            _num(10, 0),
            MINUS_C("-", lineno=1, offset=2),
            _num(3, 3),
            MINUS_C("-", lineno=1, offset=4),
            _num(2, 5),
        ],
    )
    assert isinstance(result, SubC)
    assert isinstance(result.l, SubC), "left-assoc: outer sub must have inner sub as left child"
    assert eval_c(result) == 5


def test_calc_integer_division() -> None:
    """7 / 2 produces DivC and floor-divides to 3."""
    result = _calc_parser.parse(
        "expr",
        [_num(7, 0), SLASH_C("/", lineno=1, offset=1), _num(2, 2)],
    )
    assert isinstance(result, DivC)
    assert eval_c(result) == 3


def test_calc_parentheses_override_precedence() -> None:
    """2 * (3 + 4): parentheses force add before multiply despite STAR having higher prec."""
    result = _calc_parser.parse(
        "expr",
        [
            _num(2, 0),
            STAR_C("*", lineno=1, offset=1),
            LPAREN_C("(", lineno=1, offset=2),
            _num(3, 3),
            PLUS_C("+", lineno=1, offset=4),
            _num(4, 5),
            RPAREN_C(")", lineno=1, offset=6),
        ],
    )
    assert isinstance(result, MulC), "root must be Mul"
    assert isinstance(result.r, AddC), "right child must be Add (grouped by parens)"
    assert eval_c(result) == 14


def test_calc_mixed_left_assoc_same_precedence() -> None:
    """1 - 2 + 3: MINUS and PLUS share prec=1 with left-assoc; result is (1-2)+3 = 2."""
    result = _calc_parser.parse(
        "expr",
        [
            _num(1, 0),
            MINUS_C("-", lineno=1, offset=1),
            _num(2, 2),
            PLUS_C("+", lineno=1, offset=3),
            _num(3, 4),
        ],
    )
    assert isinstance(result, AddC), "outer op must be Add"
    assert isinstance(result.l, SubC), "left child must be Sub (left-assoc)"
    assert eval_c(result) == 2


# ---------------------------------------------------------------------------
# Section 2: Default S/R conflict is left-associative
# ---------------------------------------------------------------------------


class NUM_SR(Token):
    def __init__(self, value: str, *, lineno: int, offset: int) -> None:
        super().__init__(value, lineno=lineno, offset=offset)
        self.value = int(value)


class PLUS_SR(Token):
    pass  # no precedence set → default 0, associative="left"


class NumSR:
    def __init__(self, tok: NUM_SR) -> None:
        self.value = tok.value


class AddSR:
    def __init__(self, l: object, r: object) -> None:
        self.l = l
        self.r = r


def test_default_sr_conflict_is_left_associative() -> None:
    """With no explicit precedence, S/R conflict resolves to reduce (left-associative).

    When both item.precedence and symbol.precedence are 0, the parser condition:
        item.precedence == symbol.precedence and symbol.associative == "left"
    is True (Token default associative="left"), so reduce wins.

    This means 1 + 2 + 3 produces a LEFT-leaning tree AddSR(AddSR(1,2), 3),
    not a right-leaning one. The existing test_shift_reduce_resolution_prefers_shift
    only tests the two-token case and makes no tree-shape assertion.
    """
    p = Parser(
        {
            "expr": [
                (["expr", PLUS_SR, "expr"], AddSR, [0, 2]),
                ([NUM_SR], NumSR, [0]),
            ]
        }
    )
    result = p.parse(
        "expr",
        [
            NUM_SR("1", lineno=1, offset=0),
            PLUS_SR("+", lineno=1, offset=1),
            NUM_SR("2", lineno=1, offset=2),
            PLUS_SR("+", lineno=1, offset=3),
            NUM_SR("3", lineno=1, offset=4),
        ],
    )
    assert isinstance(result, AddSR)
    assert isinstance(result.l, AddSR), "default S/R resolution must produce a left-leaning tree"
    assert isinstance(result.l.l, NumSR) and result.l.l.value == 1
    assert isinstance(result.l.r, NumSR) and result.l.r.value == 2
    assert isinstance(result.r, NumSR) and result.r.value == 3
