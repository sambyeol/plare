"""Parser tests for the Plare SLR(1) parser.

Covers: ε-productions, left/right recursion, operator precedence,
left/right associativity, multiple entry points, shift/reduce default,
and two LALR(1)-only grammars (currently xfail).
"""

from __future__ import annotations

import pytest

from plare.exception import ParsingError
from plare.parser import Parser
from plare.token import Token

type GrammarRules[T] = (
    tuple[list[type[Token] | str], type[T] | None, list[int]]
    | tuple[list[type[Token] | str], type[T] | None, list[int], type[Token]]
)

# ---------------------------------------------------------------------------
# ε-productions
# ---------------------------------------------------------------------------


class ID_T(Token):
    pass


class SEMI_T(Token):
    pass


class LABEL_T(Token):
    pass


class Label:
    pass


class SomeLabel(Label):
    def __init__(self, lbl: LABEL_T) -> None:
        self.lbl = lbl


class NoLabel(Label):
    def __init__(self) -> None:
        pass


class Stmt:
    def __init__(self, name: ID_T, label: Label) -> None:
        self.name = name
        self.label = label


def test_epsilon_optional_suffix() -> None:
    """An optional suffix modelled as an ε-production reduces to the correct node.

    Grammar: stmt → ID SEMI opt_label, opt_label → LABEL | ε.
    Verifies that omitting the optional token produces NoLabel, and including it
    produces SomeLabel, without any parser construction error.
    """
    grammar: dict[str, list[GrammarRules[Stmt | Label]]] = {
        "stmt": [([ID_T, SEMI_T, "opt_label"], Stmt, [0, 2])],
        "opt_label": [
            ([LABEL_T], SomeLabel, [0]),
            ([], NoLabel, []),
        ],
    }
    p = Parser(grammar)

    result_no = p.parse(
        "stmt",
        [
            ID_T("x", lineno=1, offset=0),
            SEMI_T(";", lineno=1, offset=1),
        ],
    )
    assert isinstance(result_no, Stmt)
    assert isinstance(result_no.label, NoLabel)

    result_yes = p.parse(
        "stmt",
        [
            ID_T("x", lineno=1, offset=0),
            SEMI_T(";", lineno=1, offset=1),
            LABEL_T("l", lineno=1, offset=2),
        ],
    )
    assert isinstance(result_yes, Stmt)
    assert isinstance(result_yes.label, SomeLabel)


# ---------------------------------------------------------------------------
# Left recursion
# ---------------------------------------------------------------------------


class NUM2(Token):
    def __init__(self, value: str, *, lineno: int, offset: int) -> None:
        super().__init__(value, lineno=lineno, offset=offset)
        self.value = int(value)


class PLUS2(Token):
    pass


class Expr2:
    pass


class Num2(Expr2):
    def __init__(self, n: NUM2) -> None:
        self.value = n.value


class Add2(Expr2):
    def __init__(self, l: Expr2, r: Expr2) -> None:
        self.l = l
        self.r = r


def test_left_recursive_addition_chain() -> None:
    """A left-recursive grammar builds a left-leaning parse tree.

    Grammar: expr → expr PLUS num | num.
    Parsing 1 + 2 + 3 must yield Add(Add(Num(1), Num(2)), Num(3)), confirming
    that repeated left recursion does not overflow the stack and that the spine
    leans left.
    """
    grammar: dict[str, list[GrammarRules[Expr2 | Num2 | Add2]]] = {
        "expr": [
            (["expr", PLUS2, "num"], Add2, [0, 2]),
            (["num"], None, [0]),
        ],
        "num": [([NUM2], Num2, [0])],
    }
    p = Parser(grammar)

    result = p.parse(
        "expr",
        [
            NUM2("1", lineno=1, offset=0),
            PLUS2("+", lineno=1, offset=1),
            NUM2("2", lineno=1, offset=2),
            PLUS2("+", lineno=1, offset=3),
            NUM2("3", lineno=1, offset=4),
        ],
    )
    assert isinstance(result, Add2)
    assert isinstance(result.l, Add2), "left recursion must produce a left-leaning tree"
    assert isinstance(result.l.l, Num2)
    assert result.l.l.value == 1
    assert isinstance(result.l.r, Num2)
    assert result.l.r.value == 2
    assert isinstance(result.r, Num2)
    assert result.r.value == 3


# ---------------------------------------------------------------------------
# Right recursion
# ---------------------------------------------------------------------------


class NUM3(Token):
    def __init__(self, value: str, *, lineno: int, offset: int) -> None:
        super().__init__(value, lineno=lineno, offset=offset)
        self.value = int(value)


class CONS3(Token):
    pass


class Expr3:
    pass


class Num3(Expr3):
    def __init__(self, n: NUM3) -> None:
        self.value = n.value


class Cons3(Expr3):
    def __init__(self, head: Expr3, tail: Expr3) -> None:
        self.head = head
        self.tail = tail


def test_right_recursive_cons_list() -> None:
    """A right-recursive grammar builds a right-leaning parse tree.

    Grammar: list → num CONS list | num.
    Parsing 1 :: 2 :: 3 must yield Cons(Num(1), Cons(Num(2), Num(3))), confirming
    that repeated right recursion terminates and that the spine leans right.
    """
    grammar: dict[str, list[GrammarRules[Expr3 | Num3 | Cons3]]] = {
        "list": [
            (["num", CONS3, "list"], Cons3, [0, 2]),
            (["num"], None, [0]),
        ],
        "num": [([NUM3], Num3, [0])],
    }
    p = Parser(grammar)

    result = p.parse(
        "list",
        [
            NUM3("1", lineno=1, offset=0),
            CONS3("::", lineno=1, offset=1),
            NUM3("2", lineno=1, offset=3),
            CONS3("::", lineno=1, offset=4),
            NUM3("3", lineno=1, offset=6),
        ],
    )
    assert isinstance(result, Cons3)
    assert isinstance(result.head, Num3)
    assert result.head.value == 1
    assert isinstance(
        result.tail, Cons3
    ), "right recursion must produce a right-leaning tree"
    assert isinstance(result.tail.head, Num3)
    assert result.tail.head.value == 2
    assert isinstance(result.tail.tail, Num3)
    assert result.tail.tail.value == 3


# ---------------------------------------------------------------------------
# Operator precedence
# ---------------------------------------------------------------------------


class NUM4(Token):
    def __init__(self, value: str, *, lineno: int, offset: int) -> None:
        super().__init__(value, lineno=lineno, offset=offset)
        self.value = int(value)


class PLUS4(Token):
    precedence = 1
    associative = "left"


class STAR4(Token):
    precedence = 2
    associative = "left"


class Expr4:
    pass


class Num4(Expr4):
    def __init__(self, n: NUM4) -> None:
        self.value = n.value


class Add4(Expr4):
    def __init__(self, l: Expr4, r: Expr4) -> None:
        self.l = l
        self.r = r


class Mul4(Expr4):
    def __init__(self, l: Expr4, r: Expr4) -> None:
        self.l = l
        self.r = r


def test_operator_precedence_mul_over_add() -> None:
    """Higher-precedence operator binds tighter in an ambiguous grammar.

    STAR4 (precedence=2) beats PLUS4 (precedence=1) in a shift/reduce conflict.
    Parsing 1 + 2 * 3 must yield Add(Num(1), Mul(Num(2), Num(3))), with '+' at
    the root and '*' deeper in the tree.
    """
    p = Parser(
        {
            "expr": [
                (["expr", PLUS4, "expr"], Add4, [0, 2]),
                (["expr", STAR4, "expr"], Mul4, [0, 2]),
                ([NUM4], Num4, [0]),
            ]
        }
    )

    # 1 + 2 * 3  →  Add4(Num4(1), Mul4(Num4(2), Num4(3)))
    result = p.parse(
        "expr",
        [
            NUM4("1", lineno=1, offset=0),
            PLUS4("+", lineno=1, offset=1),
            NUM4("2", lineno=1, offset=2),
            STAR4("*", lineno=1, offset=3),
            NUM4("3", lineno=1, offset=4),
        ],
    )
    assert isinstance(result, Add4), "'+' should be root because '*' binds tighter"
    assert isinstance(result.l, Num4)
    assert result.l.value == 1
    assert isinstance(result.r, Mul4)
    assert isinstance(result.r.l, Num4)
    assert result.r.l.value == 2
    assert isinstance(result.r.r, Num4)
    assert result.r.r.value == 3


# ---------------------------------------------------------------------------
# Left associativity
# ---------------------------------------------------------------------------


class NUM5(Token):
    def __init__(self, value: str, *, lineno: int, offset: int) -> None:
        super().__init__(value, lineno=lineno, offset=offset)
        self.value = int(value)


class MINUS5(Token):
    precedence = 1
    associative = "left"


class Expr5:
    pass


class Num5(Expr5):
    def __init__(self, n: NUM5) -> None:
        self.value = n.value


class Sub5(Expr5):
    def __init__(self, l: Expr5, r: Expr5) -> None:
        self.l = l
        self.r = r


def test_left_associative_subtraction() -> None:
    """Left-associative operator resolves shift/reduce conflict toward the left spine.

    MINUS5 carries associative="left". Parsing 1 - 2 - 3 must yield
    Sub(Sub(Num(1), Num(2)), Num(3)) — the parser must reduce before shifting
    the second '-', not shift first.
    """
    p = Parser(
        {
            "expr": [
                (["expr", MINUS5, "expr"], Sub5, [0, 2]),
                ([NUM5], Num5, [0]),
            ]
        }
    )

    # 1 - 2 - 3  →  Sub5(Sub5(Num5(1), Num5(2)), Num5(3))
    result = p.parse(
        "expr",
        [
            NUM5("1", lineno=1, offset=0),
            MINUS5("-", lineno=1, offset=1),
            NUM5("2", lineno=1, offset=2),
            MINUS5("-", lineno=1, offset=3),
            NUM5("3", lineno=1, offset=4),
        ],
    )
    assert isinstance(result, Sub5)
    assert isinstance(result.l, Sub5), "left-associative: left child must also be Sub5"
    assert isinstance(result.l.l, Num5)
    assert result.l.l.value == 1
    assert isinstance(result.l.r, Num5)
    assert result.l.r.value == 2
    assert isinstance(result.r, Num5)
    assert result.r.value == 3


# ---------------------------------------------------------------------------
# Right associativity
# ---------------------------------------------------------------------------


class NUM6(Token):
    def __init__(self, value: str, *, lineno: int, offset: int) -> None:
        super().__init__(value, lineno=lineno, offset=offset)
        self.value = int(value)


class POW6(Token):
    precedence = 2
    associative = "right"


class Expr6:
    pass


class Num6(Expr6):
    def __init__(self, n: NUM6) -> None:
        self.value = n.value


class Pow6(Expr6):
    def __init__(self, l: Expr6, r: Expr6) -> None:
        self.l = l
        self.r = r


def test_right_associative_exponentiation() -> None:
    """Right-associative operator resolves shift/reduce conflict toward the right spine.

    POW6 carries associative="right". Parsing 2 ^ 3 ^ 4 must yield
    Pow(Num(2), Pow(Num(3), Num(4))) — the parser must shift before reducing,
    grouping to the right.
    """
    p = Parser(
        {
            "expr": [
                (["expr", POW6, "expr"], Pow6, [0, 2]),
                ([NUM6], Num6, [0]),
            ]
        }
    )

    # 2 ^ 3 ^ 4  →  Pow6(Num6(2), Pow6(Num6(3), Num6(4)))
    result = p.parse(
        "expr",
        [
            NUM6("2", lineno=1, offset=0),
            POW6("^", lineno=1, offset=1),
            NUM6("3", lineno=1, offset=2),
            POW6("^", lineno=1, offset=3),
            NUM6("4", lineno=1, offset=4),
        ],
    )
    assert isinstance(result, Pow6)
    assert isinstance(result.l, Num6)
    assert result.l.value == 2
    assert isinstance(
        result.r, Pow6
    ), "right-associative: right child must also be Pow6"
    assert isinstance(result.r.l, Num6)
    assert result.r.l.value == 3
    assert isinstance(result.r.r, Num6)
    assert result.r.r.value == 4


# ---------------------------------------------------------------------------
# Multiple entry points
# ---------------------------------------------------------------------------


class WORD7(Token):
    def __init__(self, value: str, *, lineno: int, offset: int) -> None:
        super().__init__(value, lineno=lineno, offset=offset)
        self.value = value


class NUM7(Token):
    def __init__(self, value: str, *, lineno: int, offset: int) -> None:
        super().__init__(value, lineno=lineno, offset=offset)
        self.value = int(value)


class StrVal:
    def __init__(self, w: WORD7) -> None:
        self.value = w.value


class IntVal:
    def __init__(self, n: NUM7) -> None:
        self.value = n.value


def test_multiple_entry_points() -> None:
    """A single Parser instance supports multiple independent start symbols.

    Grammar has two top-level keys: "str_expr" and "int_expr". Verifies that
    each entry point accepts only its own token type and raises ParsingError
    when fed a token that belongs to the other entry point.
    """
    grammar: dict[str, list[GrammarRules[StrVal | IntVal]]] = {
        "str_expr": [([WORD7], StrVal, [0])],
        "int_expr": [([NUM7], IntVal, [0])],
    }
    p = Parser(grammar)

    str_result = p.parse("str_expr", [WORD7("hello", lineno=1, offset=0)])
    assert isinstance(str_result, StrVal)
    assert str_result.value == "hello"

    int_result = p.parse("int_expr", [NUM7("42", lineno=1, offset=0)])
    assert isinstance(int_result, IntVal)
    assert int_result.value == 42

    with pytest.raises(ParsingError):
        p.parse("str_expr", [NUM7("42", lineno=1, offset=0)])


# ---------------------------------------------------------------------------
# Shift/reduce default (prefer shift when no precedence)
# ---------------------------------------------------------------------------


class NUM8(Token):
    def __init__(self, value: str, *, lineno: int, offset: int) -> None:
        super().__init__(value, lineno=lineno, offset=offset)
        self.value = int(value)


class PLUS8(Token):
    pass


class Expr8:
    pass


class Num8(Expr8):
    def __init__(self, n: NUM8) -> None:
        self.value = n.value


class Add8(Expr8):
    def __init__(self, l: Expr8, r: Expr8) -> None:
        self.l = l
        self.r = r


def test_shift_reduce_resolution_prefers_shift() -> None:
    """Without explicit precedence, a shift/reduce conflict is silently resolved by shifting.

    Grammar: expr → expr PLUS expr | NUM, with no precedence on PLUS.
    The parser must construct without raising and parse a simple binary expression.
    This test documents the default conflict-resolution behaviour as a regression
    baseline — it does not assert tree shape for chains, since the choice between
    left- and right-leaning is an implementation artifact when precedence is absent.
    """
    p = Parser(
        {
            "expr": [
                (["expr", PLUS8, "expr"], Add8, [0, 2]),
                ([NUM8], Num8, [0]),
            ]
        }
    )

    result = p.parse(
        "expr",
        [
            NUM8("1", lineno=1, offset=0),
            PLUS8("+", lineno=1, offset=1),
            NUM8("2", lineno=1, offset=2),
        ],
    )
    assert isinstance(result, Add8)
    assert isinstance(result.l, Num8)
    assert result.l.value == 1
    assert isinstance(result.r, Num8)
    assert result.r.value == 2


# ---------------------------------------------------------------------------
# LALR(1)-resolvable grammars — FOLLOW-set inflation creates a spurious R/R
# conflict in SLR(1) that LALR(1) per-item lookaheads cleanly resolve.
#
# Two non-terminals (A_nt/B_nt, X_nt/Y_nt) share the same single-token body
# and land in the same LR(0) reduce state.  One of them also appears in an
# *unrelated* production that inflates its FOLLOW set so that it overlaps the
# other's FOLLOW set — but only in states where the two items do NOT coexist.
#
# Key distinction from the Aho/Sethi/Ullman (LR(1)-only) grammar:
#   In the Aho grammar both non-terminals appear symmetrically in four
#   productions, so every LR(1) state that holds {A_nt → C •, B_nt → C •}
#   comes in two mirror images whose lookaheads cross-contaminate when merged
#   in LALR(1), creating a new R/R conflict not present in LR(1).
#
#   Here, the extra production that inflates FOLLOW(A_nt) produces a *separate*
#   LR(0) state (core {A_nt → E •} only, no B_nt) that is never merged with
#   the conflict state (core {A_nt → E •, B_nt → E •}).  LALR(1) lookaheads
#   in the conflict state remain {B8x} vs {C8x, D8x} — disjoint — so no
#   new conflict is introduced by merging.
# ---------------------------------------------------------------------------


class A8x(Token):
    pass


class B8x(Token):
    pass


class C8x(Token):
    pass


class D8x(Token):
    pass


class E8x(Token):
    pass


class Node8x:
    def __init__(self, *args: object) -> None:
        pass


def test_lalr1_rr_conflict_follow_inflation_variant_1() -> None:
    """FOLLOW-set inflation creates a spurious SLR(1) R/R conflict.

    Grammar:
      start → A8x A_nt B8x | A8x B_nt C8x | A8x B_nt D8x | A_nt C8x
      A_nt  → E8x
      B_nt  → E8x

    The state reached after [A8x, E8x] contains {A_nt → E8x •, B_nt → E8x •}.
    FOLLOW(A_nt) = {B8x, C8x}  (from "A8x A_nt B8x" and "A_nt C8x")
    FOLLOW(B_nt) = {C8x, D8x}  (from "A8x B_nt C8x" and "A8x B_nt D8x")
    Intersection {C8x} creates a spurious SLR(1) R/R conflict; definition order
    picks A_nt.  Parsing [A8x, E8x, C8x] therefore fails: SLR(1) reduces E8x
    to A_nt, then rejects C8x (expected B8x).

    LALR(1) per-item lookaheads in that state are {B8x} for A_nt and
    {C8x, D8x} for B_nt — disjoint — so C8x correctly triggers B_nt and the
    parse succeeds.  The inflation token C8x only appears as a lookahead in a
    separate LR(0) state (core {A_nt → E8x •} alone), which is never merged
    with the conflict state, so LALR(1) is sufficient.
    """
    p = Parser(
        {
            "start": [
                ([A8x, "A_nt", B8x], Node8x, [0, 1, 2]),
                ([A8x, "B_nt", C8x], Node8x, [0, 1, 2]),
                ([A8x, "B_nt", D8x], Node8x, [0, 1, 2]),
                (["A_nt", C8x], Node8x, [0, 1]),
            ],
            "A_nt": [([E8x], None, [0])],
            "B_nt": [([E8x], None, [0])],
        }
    )
    result = p.parse(
        "start",
        [
            A8x("a", lineno=1, offset=0),
            E8x("e", lineno=1, offset=1),
            C8x("c", lineno=1, offset=2),
        ],
    )
    assert isinstance(result, Node8x)


class P8y(Token):
    pass


class Q8y(Token):
    pass


class R8y(Token):
    pass


class S8y(Token):
    pass


class T8y(Token):
    pass


class Node8y:
    def __init__(self, *args: object) -> None:
        pass


def test_lalr1_rr_conflict_follow_inflation_variant_2() -> None:
    """Isomorphic variant confirming the result is independent of token naming.

    Grammar:
      start2 → P8y X_nt Q8y | P8y Y_nt R8y | P8y Y_nt S8y | X_nt R8y
      X_nt  → T8y
      Y_nt  → T8y

    FOLLOW(X_nt) = {Q8y, R8y}  (from "P8y X_nt Q8y" and "X_nt R8y")
    FOLLOW(Y_nt) = {R8y, S8y}  (from "P8y Y_nt R8y" and "P8y Y_nt S8y")
    Intersection {R8y}: spurious SLR(1) R/R; X_nt wins by definition order.
    Parsing [P8y, T8y, R8y] fails: SLR(1) reduces T8y to X_nt, then rejects
    R8y (expected Q8y).
    LALR(1) per-item lookaheads after [P8y, T8y]: X_nt → {Q8y}, Y_nt →
    {R8y, S8y} — disjoint — so R8y correctly triggers Y_nt.
    """
    p = Parser(
        {
            "start2": [
                ([P8y, "X_nt", Q8y], Node8y, [0, 1, 2]),
                ([P8y, "Y_nt", R8y], Node8y, [0, 1, 2]),
                ([P8y, "Y_nt", S8y], Node8y, [0, 1, 2]),
                (["X_nt", R8y], Node8y, [0, 1]),
            ],
            "X_nt": [([T8y], None, [0])],
            "Y_nt": [([T8y], None, [0])],
        }
    )
    result = p.parse(
        "start2",
        [
            P8y("p", lineno=1, offset=0),
            T8y("t", lineno=1, offset=1),
            R8y("r", lineno=1, offset=2),
        ],
    )
    assert isinstance(result, Node8y)
