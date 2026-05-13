"""Comprehensive grammar and logic tests for the Plare lexer/parser framework.

Covers: arithmetic calculator with value evaluation, default S/R associativity,
dangling else (xfail), three-level precedence with %prec, comma-separated list
grammar, function call grammar, deep nesting, lexer multiline tracking, error
cases, and top-level epsilon productions.
"""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from plare.exception import ParsingError
from plare.lexer import Lexer
from plare.parser import Parser
from plare.token import Token

type GrammarDict[T] = dict[
    str,
    list[
        tuple[Sequence[type[Token] | str], type[T] | None, list[int]]
        | tuple[Sequence[type[Token] | str], type[T] | None, list[int], type[Token]]
    ],
]

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


CALC_GRAMMAR: GrammarDict[ExprC] = {
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

calc_parser = Parser(CALC_GRAMMAR)


def num(v: int, o: int = 0) -> NUM_C:
    return NUM_C(str(v), lineno=1, offset=o)


def test_calc_single_addition() -> None:
    """1 + 2 evaluates to 3 and produces an AddC node."""
    result = calc_parser.parse(
        "expr",
        [num(1, 0), PLUS_C("+", lineno=1, offset=1), num(2, 2)],
    )
    assert isinstance(result, AddC)
    assert isinstance(result.l, NumC) and result.l.value == 1
    assert isinstance(result.r, NumC) and result.r.value == 2
    assert eval_c(result) == 3


def test_calc_precedence_mul_over_add() -> None:
    """1 + 2 * 3: STAR (prec=2) beats PLUS (prec=1), so root is AddC, right child is MulC."""
    result = calc_parser.parse(
        "expr",
        [
            num(1, 0),
            PLUS_C("+", lineno=1, offset=1),
            num(2, 2),
            STAR_C("*", lineno=1, offset=3),
            num(3, 4),
        ],
    )
    assert isinstance(result, AddC), "'+' must be root because '*' binds tighter"
    assert isinstance(result.r, MulC)
    assert eval_c(result) == 7


def test_calc_left_assoc_subtraction_chain() -> None:
    """10 - 3 - 2: left-associativity produces SubC(SubC(10, 3), 2) = 5, not 9."""
    result = calc_parser.parse(
        "expr",
        [
            num(10, 0),
            MINUS_C("-", lineno=1, offset=2),
            num(3, 3),
            MINUS_C("-", lineno=1, offset=4),
            num(2, 5),
        ],
    )
    assert isinstance(result, SubC)
    assert isinstance(
        result.l, SubC
    ), "left-assoc: outer sub must have inner sub as left child"
    assert eval_c(result) == 5


def test_calc_integer_division() -> None:
    """7 / 2 produces DivC and floor-divides to 3."""
    result = calc_parser.parse(
        "expr",
        [num(7, 0), SLASH_C("/", lineno=1, offset=1), num(2, 2)],
    )
    assert isinstance(result, DivC)
    assert eval_c(result) == 3


def test_calc_parentheses_override_precedence() -> None:
    """2 * (3 + 4): parentheses force add before multiply despite STAR having higher prec."""
    result = calc_parser.parse(
        "expr",
        [
            num(2, 0),
            STAR_C("*", lineno=1, offset=1),
            LPAREN_C("(", lineno=1, offset=2),
            num(3, 3),
            PLUS_C("+", lineno=1, offset=4),
            num(4, 5),
            RPAREN_C(")", lineno=1, offset=6),
        ],
    )
    assert isinstance(result, MulC), "root must be Mul"
    assert isinstance(result.r, AddC), "right child must be Add (grouped by parens)"
    assert eval_c(result) == 14


def test_calc_mixed_left_assoc_same_precedence() -> None:
    """1 - 2 + 3: MINUS and PLUS share prec=1 with left-assoc; result is (1-2)+3 = 2."""
    result = calc_parser.parse(
        "expr",
        [
            num(1, 0),
            MINUS_C("-", lineno=1, offset=1),
            num(2, 2),
            PLUS_C("+", lineno=1, offset=3),
            num(3, 4),
        ],
    )
    assert isinstance(result, AddC), "outer op must be Add"
    assert isinstance(result.l, SubC), "left child must be Sub (left-assoc)"
    assert eval_c(result) == 2


# ---------------------------------------------------------------------------
# Section 2: Explicit left-assoc declaration causes reduce to win in S/R conflict
# ---------------------------------------------------------------------------


class NUM_SR(Token):
    def __init__(self, value: str, *, lineno: int, offset: int) -> None:
        super().__init__(value, lineno=lineno, offset=offset)
        self.value = int(value)


class PLUS_SR(Token):
    associative = "left"


class NumSR:
    def __init__(self, tok: NUM_SR) -> None:
        self.value = tok.value


class AddSR:
    def __init__(self, l: object, r: object) -> None:
        self.l = l
        self.r = r


def test_default_sr_conflict_is_left_associative() -> None:
    """With explicit associative="left", S/R conflict resolves to reduce (left-associative).

    When both item.precedence and symbol.precedence are 0, the parser condition:
        item.precedence == symbol.precedence and symbol.associative == "left"
    is True, so reduce wins.

    This means 1 + 2 + 3 produces a LEFT-leaning tree AddSR(AddSR(1, 2), 3),
    not a right-leaning one.
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
    assert isinstance(
        result.l, AddSR
    ), "default S/R resolution must produce a left-leaning tree"
    assert isinstance(result.l.l, NumSR) and result.l.l.value == 1
    assert isinstance(result.l.r, NumSR) and result.l.r.value == 2
    assert isinstance(result.r, NumSR) and result.r.value == 3


# ---------------------------------------------------------------------------
# Section 3: Dangling else (xfail)
# ---------------------------------------------------------------------------


class IF_D(Token):
    pass


class THEN_D(Token):
    pass


class ELSE_D(Token):
    pass


class BASE_D(Token):
    def __init__(self, value: str, *, lineno: int, offset: int) -> None:
        super().__init__(value, lineno=lineno, offset=offset)
        self.value = value


class StmtD:
    pass


class BaseStmtD(StmtD):
    def __init__(self, tok: BASE_D) -> None:
        self.value = tok.value


class IfThenD(StmtD):
    def __init__(self, cond: BASE_D, then: StmtD) -> None:
        self.cond = cond.value
        self.then = then


class IfThenElseD(StmtD):
    def __init__(self, cond: BASE_D, then: StmtD, else_: StmtD) -> None:
        self.cond = cond.value
        self.then = then
        self.else_ = else_


def test_dangling_else_inner_if_gets_else() -> None:
    """The dangling-else problem: 'if c1 then if c2 then s1 else s2'.

    Language convention (C, Java): else binds to the nearest (inner) if.
    Expected parse: IfThenD(c1, IfThenElseD(c2, s1, s2)).

    Plare's default S/R resolution: when the parser has reduced 'if c2 then s1'
    to a stmt and sees ELSE as lookahead, both production precedence and token
    precedence are 0, and associative='left' → reduce wins → the inner if becomes
    IfThenD (no else) and the outer if absorbs the else clause.
    Actual parse: IfThenElseD(c1, IfThenD(c2, s1), s2).
    """
    p = Parser(
        {
            "stmt": [
                (
                    [IF_D, BASE_D, THEN_D, "stmt", ELSE_D, "stmt"],
                    IfThenElseD,
                    [1, 3, 5],
                ),
                ([IF_D, BASE_D, THEN_D, "stmt"], IfThenD, [1, 3]),
                ([BASE_D], BaseStmtD, [0]),
            ]
        }
    )
    tokens = [
        IF_D("if", lineno=1, offset=0),
        BASE_D("c1", lineno=1, offset=3),
        THEN_D("then", lineno=1, offset=6),
        IF_D("if", lineno=1, offset=11),
        BASE_D("c2", lineno=1, offset=14),
        THEN_D("then", lineno=1, offset=17),
        BASE_D("s1", lineno=1, offset=22),
        ELSE_D("else", lineno=1, offset=25),
        BASE_D("s2", lineno=1, offset=30),
    ]
    result = p.parse("stmt", tokens)
    # inner if should absorb the else
    assert isinstance(result, IfThenD), "outer if should have no else"
    assert isinstance(result.then, IfThenElseD), "inner if should get the else clause"
    assert result.then.cond == "c2"


# ---------------------------------------------------------------------------
# Section 4: Three-level precedence with %prec (unary minus)
# ---------------------------------------------------------------------------


class NUM_UP(Token):
    def __init__(self, value: str, *, lineno: int, offset: int) -> None:
        super().__init__(value, lineno=lineno, offset=offset)
        self.value = int(value)


class PLUS_UP(Token):
    precedence = 1
    associative = "left"


class STAR_UP(Token):
    precedence = 2
    associative = "left"


class MINUS_UP(Token):
    """Unary minus prefix token (no binary minus in this grammar)."""

    pass


class UMINUS_UP(Token):
    """Pseudo-token used only as a prec_token override; never emitted by any lexer."""

    precedence = 3
    associative = "right"


class ExprUP:
    pass


class NumUP(ExprUP):
    def __init__(self, tok: NUM_UP) -> None:
        self.value = tok.value


class NegUP(ExprUP):
    def __init__(self, operand: ExprUP) -> None:
        self.operand = operand


class AddUP(ExprUP):
    def __init__(self, l: ExprUP, r: ExprUP) -> None:
        self.l = l
        self.r = r


class MulUP(ExprUP):
    def __init__(self, l: ExprUP, r: ExprUP) -> None:
        self.l = l
        self.r = r


unary_parser = Parser(
    {
        "expr": [
            ([NUM_UP], NumUP, [0]),
            (["expr", PLUS_UP, "expr"], AddUP, [0, 2]),
            (["expr", STAR_UP, "expr"], MulUP, [0, 2]),
            ([MINUS_UP, "expr"], NegUP, [1], UMINUS_UP),  # prec override → 3
        ]
    }
)


def test_three_level_unary_tighter_than_mul() -> None:
    """-2 * 3: unary minus (prec=3 via %prec) beats STAR (prec=2) → Mul(Neg(2), 3).

    Without the prec_token override the unary-minus production would inherit
    prec=0 (MINUS_UP has no precedence), which is lower than STAR's 2, making
    the parser shift STAR and produce Neg(Mul(2, 3)) instead.
    """
    result = unary_parser.parse(
        "expr",
        [
            MINUS_UP("-", lineno=1, offset=0),
            NUM_UP("2", lineno=1, offset=1),
            STAR_UP("*", lineno=1, offset=2),
            NUM_UP("3", lineno=1, offset=3),
        ],
    )
    assert isinstance(result, MulUP), "root must be Mul"
    assert isinstance(result.l, NegUP), "left child must be Neg (unary binds tightest)"
    assert isinstance(result.l.operand, NumUP) and result.l.operand.value == 2
    assert isinstance(result.r, NumUP) and result.r.value == 3


def test_three_level_unary_with_add() -> None:
    """2 + -3: unary minus (prec=3) on right operand is reduced before add (prec=1)."""
    result = unary_parser.parse(
        "expr",
        [
            NUM_UP("2", lineno=1, offset=0),
            PLUS_UP("+", lineno=1, offset=1),
            MINUS_UP("-", lineno=1, offset=2),
            NUM_UP("3", lineno=1, offset=3),
        ],
    )
    assert isinstance(result, AddUP), "root must be Add"
    assert isinstance(result.l, NumUP) and result.l.value == 2
    assert isinstance(result.r, NegUP), "right child must be Neg"
    assert isinstance(result.r.operand, NumUP) and result.r.operand.value == 3


# ---------------------------------------------------------------------------
# Section 5: Comma-separated list grammar
# ---------------------------------------------------------------------------


class LBRACKET_L(Token):
    pass


class RBRACKET_L(Token):
    pass


class COMMA_L(Token):
    pass


class NUM_L(Token):
    def __init__(self, value: str, *, lineno: int, offset: int) -> None:
        super().__init__(value, lineno=lineno, offset=offset)
        self.value = int(value)


class ItemsL:
    items: list[int]


class SingleItemL(ItemsL):
    def __init__(self, head: NUM_L) -> None:
        self.items = [head.value]


class ConsItemsL(ItemsL):
    def __init__(self, head: NUM_L, tail: ItemsL) -> None:
        self.items = [head.value] + tail.items


class ListL:
    def __init__(self, items_node: ItemsL) -> None:
        self.items = items_node.items


class EmptyListL:
    def __init__(self) -> None:
        self.items: list[int] = []


LIST_GRAMMAR: GrammarDict[ListL | EmptyListL | ConsItemsL | SingleItemL] = {
    "list": [
        ([LBRACKET_L, "items", RBRACKET_L], ListL, [1]),
        ([LBRACKET_L, RBRACKET_L], EmptyListL, []),
    ],
    "items": [
        ([NUM_L, COMMA_L, "items"], ConsItemsL, [0, 2]),
        ([NUM_L], SingleItemL, [0]),
    ],
}
list_parser = Parser(LIST_GRAMMAR)


def num_l(v: int, o: int = 0) -> NUM_L:
    return NUM_L(str(v), lineno=1, offset=o)


def test_list_empty() -> None:
    """[] produces EmptyListL with items == []."""
    result = list_parser.parse(
        "list",
        [LBRACKET_L("[", lineno=1, offset=0), RBRACKET_L("]", lineno=1, offset=1)],
    )
    assert isinstance(result, EmptyListL)
    assert result.items == []


def test_list_single_element() -> None:
    """[42] produces ListL with items == [42]."""
    result = list_parser.parse(
        "list",
        [
            LBRACKET_L("[", lineno=1, offset=0),
            num_l(42, 1),
            RBRACKET_L("]", lineno=1, offset=3),
        ],
    )
    assert isinstance(result, ListL)
    assert result.items == [42]


def test_list_three_elements() -> None:
    """[1, 2, 3] produces ListL with items == [1, 2, 3]."""
    result = list_parser.parse(
        "list",
        [
            LBRACKET_L("[", lineno=1, offset=0),
            num_l(1, 1),
            COMMA_L(",", lineno=1, offset=2),
            num_l(2, 4),
            COMMA_L(",", lineno=1, offset=5),
            num_l(3, 7),
            RBRACKET_L("]", lineno=1, offset=8),
        ],
    )
    assert isinstance(result, ListL)
    assert result.items == [1, 2, 3]


# ---------------------------------------------------------------------------
# Section 6: Function call grammar
# ---------------------------------------------------------------------------


class ID_F(Token):
    def __init__(self, value: str, *, lineno: int, offset: int) -> None:
        super().__init__(value, lineno=lineno, offset=offset)
        self.value = value


class LPAREN_F(Token):
    pass


class RPAREN_F(Token):
    pass


class COMMA_F(Token):
    pass


class NUM_F(Token):
    def __init__(self, value: str, *, lineno: int, offset: int) -> None:
        super().__init__(value, lineno=lineno, offset=offset)
        self.value = int(value)


class ArgsF:
    items: list[int]


class SingleArgF(ArgsF):
    def __init__(self, head: NUM_F) -> None:
        self.items = [head.value]


class ConsArgsF(ArgsF):
    def __init__(self, head: NUM_F, tail: ArgsF) -> None:
        self.items = [head.value] + tail.items


class CallF:
    def __init__(self, name: ID_F, args: ArgsF) -> None:
        self.name = name.value
        self.args = args.items


class NoArgCallF:
    def __init__(self, name: ID_F) -> None:
        self.name = name.value
        self.args: list[int] = []


CALL_GRAMMAR: GrammarDict[CallF | NoArgCallF | ConsArgsF | SingleArgF] = {
    "call": [
        ([ID_F, LPAREN_F, "args", RPAREN_F], CallF, [0, 2]),
        ([ID_F, LPAREN_F, RPAREN_F], NoArgCallF, [0]),
    ],
    "args": [
        ([NUM_F, COMMA_F, "args"], ConsArgsF, [0, 2]),
        ([NUM_F], SingleArgF, [0]),
    ],
}
call_parser = Parser(CALL_GRAMMAR)


def num_f(v: int, o: int = 0) -> NUM_F:
    return NUM_F(str(v), lineno=1, offset=o)


def test_call_no_args() -> None:
    """f() produces NoArgCallF with name='f' and args==[]."""
    result = call_parser.parse(
        "call",
        [
            ID_F("f", lineno=1, offset=0),
            LPAREN_F("(", lineno=1, offset=1),
            RPAREN_F(")", lineno=1, offset=2),
        ],
    )
    assert isinstance(result, NoArgCallF)
    assert result.name == "f"
    assert result.args == []


def test_call_one_arg() -> None:
    """f(1) produces CallF with name='f' and args==[1]."""
    result = call_parser.parse(
        "call",
        [
            ID_F("f", lineno=1, offset=0),
            LPAREN_F("(", lineno=1, offset=1),
            num_f(1, 2),
            RPAREN_F(")", lineno=1, offset=3),
        ],
    )
    assert isinstance(result, CallF)
    assert result.name == "f"
    assert result.args == [1]


def test_call_three_args() -> None:
    """f(1, 2, 3) produces CallF with name='f' and args==[1, 2, 3]."""
    result = call_parser.parse(
        "call",
        [
            ID_F("f", lineno=1, offset=0),
            LPAREN_F("(", lineno=1, offset=1),
            num_f(1, 2),
            COMMA_F(",", lineno=1, offset=3),
            num_f(2, 5),
            COMMA_F(",", lineno=1, offset=6),
            num_f(3, 8),
            RPAREN_F(")", lineno=1, offset=9),
        ],
    )
    assert isinstance(result, CallF)
    assert result.name == "f"
    assert result.args == [1, 2, 3]


# ---------------------------------------------------------------------------
# Section 7: Deeply nested parentheses
# ---------------------------------------------------------------------------


def test_deeply_nested_parentheses() -> None:
    """((…(1)…)) with 100 nesting levels parses correctly without stack overflow.

    The LR stack is an explicit Python list (not recursive function calls),
    so it handles arbitrarily deep nesting without hitting Python's recursion limit.
    """
    depth = 100
    tokens = [LPAREN_C("(", lineno=1, offset=i) for i in range(depth)]
    tokens += [NUM_C("1", lineno=1, offset=depth)]
    tokens += [RPAREN_C(")", lineno=1, offset=depth + 1 + i) for i in range(depth)]
    result = calc_parser.parse("expr", tokens)
    assert isinstance(result, ExprC)
    assert eval_c(result) == 1


# ---------------------------------------------------------------------------
# Section 8: Lexer integration — multiline position tracking
# ---------------------------------------------------------------------------


def test_lexer_multiline_position_tracking() -> None:
    """Tokens on different lines get the correct lineno and offset=0.

    Source '1\\n+\\n2': each token is on its own line.
    The lexer resets offset to 0 at each newline.
    Whitespace (including '\\n') is consumed by the "start" state re-entry pattern
    and lineno is incremented per newline encountered.
    """
    tokens = list(CALC_LEXER.lex("start", "1\n+\n2"))
    assert len(tokens) == 3

    num1, plus, num2 = tokens
    assert isinstance(num1, NUM_C) and num1.value == 1
    assert num1.lineno == 1 and num1.offset == 0

    assert isinstance(plus, PLUS_C)
    assert plus.lineno == 2 and plus.offset == 0

    assert isinstance(num2, NUM_C) and num2.value == 2
    assert num2.lineno == 3 and num2.offset == 0

    result = calc_parser.parse("expr", tokens)
    assert isinstance(result, ExprC)
    assert eval_c(result) == 3


# ---------------------------------------------------------------------------
# Section 9: Error cases
# ---------------------------------------------------------------------------


def test_error_unclosed_paren() -> None:
    """(1 + 2 with no closing paren raises ParsingError at end-of-input."""
    with pytest.raises(ParsingError):
        calc_parser.parse(
            "expr",
            [
                LPAREN_C("(", lineno=1, offset=0),
                num(1, 1),
                PLUS_C("+", lineno=1, offset=2),
                num(2, 3),
                # RPAREN_C missing
            ],
        )


def test_error_trailing_tokens() -> None:
    """1 + 2 followed by an extra token raises ParsingError.

    After the parser reduces to the top-level expr and sees EOS, it accepts.
    But if extra tokens precede EOS, the accept state has no action for them.
    """
    with pytest.raises(ParsingError):
        calc_parser.parse(
            "expr",
            [
                num(1, 0),
                PLUS_C("+", lineno=1, offset=1),
                num(2, 2),
                num(3, 3),  # extra token — parser cannot accept with this pending
            ],
        )


# ---------------------------------------------------------------------------
# Section 10: Top-level epsilon production
# ---------------------------------------------------------------------------


class STMT_E(Token):
    def __init__(self, value: str, *, lineno: int, offset: int) -> None:
        super().__init__(value, lineno=lineno, offset=offset)
        self.value = value


class StmtsE:
    items: list[STMT_E]


class EmptyStmtsE(StmtsE):
    def __init__(self) -> None:
        self.items = []


class NonEmptyStmtsE(StmtsE):
    def __init__(self, stmt: STMT_E, tail: StmtsE) -> None:
        self.items = [stmt] + tail.items


class ProgramE:
    def __init__(self, stmts: StmtsE) -> None:
        self.stmts = stmts.items


PROGRAM_GRAMMAR: GrammarDict[ProgramE | NonEmptyStmtsE | EmptyStmtsE] = {
    "program": [
        (["stmts"], ProgramE, [0]),
    ],
    "stmts": [
        ([STMT_E, "stmts"], NonEmptyStmtsE, [0, 1]),
        ([], EmptyStmtsE, []),
    ],
}
program_parser = Parser(PROGRAM_GRAMMAR)


def test_empty_program() -> None:
    """An empty token stream produces ProgramE with stmts == []."""
    result = program_parser.parse("program", [])
    assert isinstance(result, ProgramE)
    assert result.stmts == []


def test_single_statement_program() -> None:
    """One STMT_E token produces ProgramE with len(stmts) == 1."""
    result = program_parser.parse(
        "program",
        [STMT_E("x", lineno=1, offset=0)],
    )
    assert isinstance(result, ProgramE)
    assert len(result.stmts) == 1
    assert isinstance(result.stmts[0], STMT_E)


def test_three_statement_program() -> None:
    """Three STMT_E tokens produce ProgramE with len(stmts) == 3 in order."""
    result = program_parser.parse(
        "program",
        [
            STMT_E("a", lineno=1, offset=0),
            STMT_E("b", lineno=1, offset=2),
            STMT_E("c", lineno=1, offset=4),
        ],
    )
    assert isinstance(result, ProgramE)
    assert len(result.stmts) == 3
    assert [s.value for s in result.stmts] == ["a", "b", "c"]
