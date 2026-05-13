"""Integration tests: full Expr DSL with lexer + parser end-to-end.

The Expr language supports:
  - Integer literals and named variables
  - Arithmetic: +, -, *, /, ** (right-associative exponentiation)
  - Unary negation (- expr)
  - Boolean operators: and, or, not
  - Comparisons: <, >, ==
  - Conditional: if expr then expr else expr
  - Let binding: let id = expr in expr

Operator precedence (lowest to highest):
  or  (1)  left
  and (2)  left
  not (3)  right (prefix)
  <,>,==   (4)  left
  +,-      (5)  left
  *,/,     (6)  left
  -expr    (6)  right  (unary, via prec_token UMINUS — same as *,/ so -3*2=(-3)*2)
  **       (7)  right  (above UMINUS, so -2**2 = -(2**2) = -4)

These tests exercise: precedence resolution, associativity, right-associativity,
operator precedence override (prec_token), lexer state, keyword dispatch,
and error reporting.
"""

from __future__ import annotations

import pytest

from plare.exception import LexingError, ParsingError
from plare.lexer import Lexer
from plare.parser import Parser
from plare.token import Token

# ---------------------------------------------------------------------------
# Token definitions
# ---------------------------------------------------------------------------


class NUM(Token):
    def __init__(self, value: str, *, lineno: int, offset: int) -> None:
        super().__init__(value, lineno=lineno, offset=offset)
        self.value = int(value)


class ID(Token):
    def __init__(self, value: str, *, lineno: int, offset: int) -> None:
        super().__init__(value, lineno=lineno, offset=offset)
        self.name = value


# Arithmetic operators
class PLUS(Token):
    precedence = 5
    associative = "left"


class MINUS(Token):
    precedence = 5
    associative = "left"


class STAR(Token):
    precedence = 6
    associative = "left"


class SLASH(Token):
    precedence = 6
    associative = "left"


class POW(Token):
    precedence = 7
    associative = "right"


# Phantom token used only as a prec_token for unary minus (precedence=6).
# Being equal to STAR/SLASH (also 6, left-assoc) means -3*2 reduces the unary
# minus first (equal-prec + left-assoc → reduce).  Being below POW (7) means
# -2**2 shifts ** first, giving -(2**2) = -4.
class UMINUS(Token):
    precedence = 6
    associative = "right"


# Comparison operators
class LT(Token):
    precedence = 4
    associative = "left"


class GT(Token):
    precedence = 4
    associative = "left"


class EQEQ(Token):
    precedence = 4
    associative = "left"


# Boolean operators
class OR(Token):
    precedence = 1
    associative = "left"


class AND(Token):
    precedence = 2
    associative = "left"


class NOT(Token):
    precedence = 3
    associative = "right"


# Delimiters / keywords (all default precedence 0)
class LPAREN(Token):
    pass


class RPAREN(Token):
    pass


class EQ(Token):
    pass  # assignment = in let binding


class LET(Token):
    pass


class IN(Token):
    pass


class IF(Token):
    pass


class THEN(Token):
    pass


class ELSE(Token):
    pass


# ---------------------------------------------------------------------------
# AST nodes
# ---------------------------------------------------------------------------


class Expr:
    pass


class Num(Expr):
    def __init__(self, tok: NUM) -> None:
        self.value: int = tok.value


class Var(Expr):
    def __init__(self, tok: ID) -> None:
        self.name: str = tok.name


class Add(Expr):
    def __init__(self, l: Expr, r: Expr) -> None:
        self.l, self.r = l, r


class Sub(Expr):
    def __init__(self, l: Expr, r: Expr) -> None:
        self.l, self.r = l, r


class Mul(Expr):
    def __init__(self, l: Expr, r: Expr) -> None:
        self.l, self.r = l, r


class Div(Expr):
    def __init__(self, l: Expr, r: Expr) -> None:
        self.l, self.r = l, r


class Pow(Expr):
    def __init__(self, l: Expr, r: Expr) -> None:
        self.l, self.r = l, r


class Neg(Expr):
    def __init__(self, operand: Expr) -> None:
        self.operand = operand


class CmpLt(Expr):
    def __init__(self, l: Expr, r: Expr) -> None:
        self.l, self.r = l, r


class CmpGt(Expr):
    def __init__(self, l: Expr, r: Expr) -> None:
        self.l, self.r = l, r


class CmpEq(Expr):
    def __init__(self, l: Expr, r: Expr) -> None:
        self.l, self.r = l, r


class BoolAnd(Expr):
    def __init__(self, l: Expr, r: Expr) -> None:
        self.l, self.r = l, r


class BoolOr(Expr):
    def __init__(self, l: Expr, r: Expr) -> None:
        self.l, self.r = l, r


class BoolNot(Expr):
    def __init__(self, operand: Expr) -> None:
        self.operand = operand


class IfExpr(Expr):
    def __init__(self, cond: Expr, then_: Expr, else_: Expr) -> None:
        self.cond = cond
        self.then_ = then_
        self.else_ = else_


class LetExpr(Expr):
    def __init__(self, name_tok: ID, defn: Expr, body: Expr) -> None:
        self.name = name_tok.name
        self.defn = defn
        self.body = body


# ---------------------------------------------------------------------------
# Evaluator — all values are integers (booleans represented as 0 / 1)
# ---------------------------------------------------------------------------


def eval_expr(node: Expr, env: dict[str, int] | None = None) -> int:
    if env is None:
        env = {}
    match node:
        case Num():
            return node.value
        case Var():
            return env[node.name]
        case Add():
            return eval_expr(node.l, env) + eval_expr(node.r, env)
        case Sub():
            return eval_expr(node.l, env) - eval_expr(node.r, env)
        case Mul():
            return eval_expr(node.l, env) * eval_expr(node.r, env)
        case Div():
            return eval_expr(node.l, env) // eval_expr(node.r, env)
        case Pow():
            return eval_expr(node.l, env) ** eval_expr(node.r, env)
        case Neg():
            return -eval_expr(node.operand, env)
        case CmpLt():
            return int(eval_expr(node.l, env) < eval_expr(node.r, env))
        case CmpGt():
            return int(eval_expr(node.l, env) > eval_expr(node.r, env))
        case CmpEq():
            return int(eval_expr(node.l, env) == eval_expr(node.r, env))
        case BoolAnd():
            return int(bool(eval_expr(node.l, env)) and bool(eval_expr(node.r, env)))
        case BoolOr():
            return int(bool(eval_expr(node.l, env)) or bool(eval_expr(node.r, env)))
        case BoolNot():
            return int(not eval_expr(node.operand, env))
        case IfExpr():
            if eval_expr(node.cond, env):
                return eval_expr(node.then_, env)
            return eval_expr(node.else_, env)
        case LetExpr():
            val = eval_expr(node.defn, env)
            return eval_expr(node.body, {**env, node.name: val})
        case _:
            raise ValueError(f"Unhandled node type: {type(node)}")


# ---------------------------------------------------------------------------
# Lexer
# ---------------------------------------------------------------------------

_KEYWORDS: dict[str, type[Token]] = {
    "let": LET,
    "in": IN,
    "if": IF,
    "then": THEN,
    "else": ELSE,
    "and": AND,
    "or": OR,
    "not": NOT,
}


def _lex_word(matched: str, state: None, lineno: int, offset: int) -> Token:
    cls = _KEYWORDS.get(matched, ID)
    return cls(matched, lineno=lineno, offset=offset)


expr_lexer: Lexer[None] = Lexer(
    {
        "start": [
            (r"[ \t\n]+", "start"),
            (r"\d+", NUM),
            (r"\*\*", POW),  # ** before *
            (r"\*", STAR),
            (r"==", EQEQ),  # == before =
            (r"=", EQ),
            (r"\+", PLUS),
            (r"-", MINUS),
            (r"/", SLASH),
            (r"<", LT),
            (r">", GT),
            (r"\(", LPAREN),
            (r"\)", RPAREN),
            (r"[a-zA-Z_]\w*", _lex_word),
        ]
    }
)

# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

expr_parser: Parser[Expr] = Parser(
    {
        "expr": [
            # Atoms
            ([NUM], Num, [0]),
            ([ID], Var, [0]),
            ([LPAREN, "expr", RPAREN], None, [1]),
            # Arithmetic (binary)
            (["expr", PLUS, "expr"], Add, [0, 2]),
            (["expr", MINUS, "expr"], Sub, [0, 2]),
            (["expr", STAR, "expr"], Mul, [0, 2]),
            (["expr", SLASH, "expr"], Div, [0, 2]),
            (["expr", POW, "expr"], Pow, [0, 2]),
            # Unary negation — UMINUS as prec_token gives it precedence 6,
            # which is below POW=7, so -2**2 shifts ** first → -(2**2)=-4.
            ([MINUS, "expr"], Neg, [1], UMINUS),
            # Boolean
            (["expr", AND, "expr"], BoolAnd, [0, 2]),
            (["expr", OR, "expr"], BoolOr, [0, 2]),
            ([NOT, "expr"], BoolNot, [1]),
            # Comparisons
            (["expr", LT, "expr"], CmpLt, [0, 2]),
            (["expr", GT, "expr"], CmpGt, [0, 2]),
            (["expr", EQEQ, "expr"], CmpEq, [0, 2]),
            # Control flow (precedence 0 — body extends as far right as possible)
            ([IF, "expr", THEN, "expr", ELSE, "expr"], IfExpr, [1, 3, 5]),
            ([LET, ID, EQ, "expr", IN, "expr"], LetExpr, [1, 3, 5]),
        ]
    }
)

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def parse_eval(src: str, env: dict[str, int] | None = None) -> int:
    result = expr_parser.parse("expr", expr_lexer.lex("start", src))
    assert isinstance(result, Expr)
    return eval_expr(result, env)


# ---------------------------------------------------------------------------
# Section 1: Arithmetic — precedence and associativity
# ---------------------------------------------------------------------------


def test_literal() -> None:
    """A bare integer literal evaluates to its value."""
    assert parse_eval("42") == 42


def test_addition() -> None:
    """Simple addition."""
    assert parse_eval("3 + 4") == 7


def test_multiplication_precedence_over_addition() -> None:
    """1 + 2 * 3 == 7: multiplication binds tighter than addition."""
    assert parse_eval("1 + 2 * 3") == 7


def test_left_associativity_subtraction() -> None:
    """10 - 3 - 2 == 5: subtraction is left-associative → (10-3)-2."""
    assert parse_eval("10 - 3 - 2") == 5


def test_left_associativity_division() -> None:
    """12 / 4 / 3 == 1: division is left-associative → (12/4)/3."""
    assert parse_eval("12 / 4 / 3") == 1


def test_right_associativity_power() -> None:
    """2 ** 3 ** 2 == 512: exponentiation is right-associative → 2**(3**2)=2**9."""
    assert parse_eval("2 ** 3 ** 2") == 512


def test_power_not_right_assoc_without_nesting() -> None:
    """2 ** 3 == 8: single exponentiation still works."""
    assert parse_eval("2 ** 3") == 8


def test_parentheses_override_precedence() -> None:
    """(1 + 2) * 3 == 9: parentheses override the default * > + priority."""
    assert parse_eval("(1 + 2) * 3") == 9


def test_mixed_precedence_levels() -> None:
    """1 + 2 * 3 - 4 / 2 == 5: several levels in one expression."""
    assert parse_eval("1 + 2 * 3 - 4 / 2") == 5


# ---------------------------------------------------------------------------
# Section 2: Unary negation
# ---------------------------------------------------------------------------


def test_unary_negation_simple() -> None:
    """-5 evaluates to -5."""
    assert parse_eval("-5") == -5


def test_unary_negation_with_addition() -> None:
    """-5 + 3 == -2: unary minus is tighter than addition."""
    assert parse_eval("-5 + 3") == -2


def test_unary_negation_lower_than_power() -> None:
    """-2 ** 2 == -4: power binds tighter than unary minus → -(2**2)."""
    assert parse_eval("-2 ** 2") == -4


def test_unary_negation_higher_than_mul() -> None:
    """-3 * 2 == -6: unary minus binds tighter than multiplication → (-3)*2."""
    assert parse_eval("-3 * 2") == -6


def test_double_unary_negation() -> None:
    """--5 == 5: two consecutive unary minuses cancel."""
    assert parse_eval("--5") == 5


# ---------------------------------------------------------------------------
# Section 3: Comparisons
# ---------------------------------------------------------------------------


def test_comparison_lt_true() -> None:
    """1 < 2 evaluates to 1 (true)."""
    assert parse_eval("1 < 2") == 1


def test_comparison_lt_false() -> None:
    """2 < 1 evaluates to 0 (false)."""
    assert parse_eval("2 < 1") == 0


def test_comparison_gt() -> None:
    """3 > 2 evaluates to 1."""
    assert parse_eval("3 > 2") == 1


def test_comparison_eq_true() -> None:
    """4 == 4 evaluates to 1."""
    assert parse_eval("4 == 4") == 1


def test_comparison_eq_false() -> None:
    """4 == 5 evaluates to 0."""
    assert parse_eval("4 == 5") == 0


def test_comparison_binds_looser_than_arithmetic() -> None:
    """1 + 1 < 3 == 1: arithmetic is evaluated before comparison."""
    assert parse_eval("1 + 1 < 3") == 1


# ---------------------------------------------------------------------------
# Section 4: Boolean operators
# ---------------------------------------------------------------------------


def test_bool_and_truthy() -> None:
    """1 and 1 evaluates to 1."""
    assert parse_eval("1 and 1") == 1


def test_bool_and_falsy() -> None:
    """1 and 0 evaluates to 0."""
    assert parse_eval("1 and 0") == 0


def test_bool_or_truthy() -> None:
    """0 or 1 evaluates to 1."""
    assert parse_eval("0 or 1") == 1


def test_bool_or_both_falsy() -> None:
    """0 or 0 evaluates to 0."""
    assert parse_eval("0 or 0") == 0


def test_bool_not_true() -> None:
    """not 1 evaluates to 0."""
    assert parse_eval("not 1") == 0


def test_bool_not_false() -> None:
    """not 0 evaluates to 1."""
    assert parse_eval("not 0") == 1


def test_not_lower_than_comparison() -> None:
    """not 1 < 2 == 0: comparison binds tighter than not → not(1<2)=not(1)=0."""
    assert parse_eval("not 1 < 2") == 0


def test_not_higher_than_and() -> None:
    """not 0 and 0 == 0: not binds tighter than and → (not 0) and 0 = 1 and 0 = 0."""
    assert parse_eval("not 0 and 0") == 0


def test_not_higher_than_or() -> None:
    """not 0 or 0 == 1: not binds tighter than or → (not 0) or 0 = 1 or 0 = 1."""
    assert parse_eval("not 0 or 0") == 1


def test_and_higher_than_or() -> None:
    """1 or 0 and 0 == 1: and binds tighter than or → 1 or (0 and 0) = 1 or 0 = 1."""
    assert parse_eval("1 or 0 and 0") == 1


def test_combined_boolean_and_comparison() -> None:
    """(1 < 2) and (3 > 2) == 1: both comparisons true."""
    assert parse_eval("1 < 2 and 3 > 2") == 1


# ---------------------------------------------------------------------------
# Section 5: Let bindings
# ---------------------------------------------------------------------------


def test_let_simple() -> None:
    """let x = 5 in x + 1 evaluates to 6."""
    assert parse_eval("let x = 5 in x + 1") == 6


def test_let_body_extends_right() -> None:
    """let x = 3 in x * 2 + 1 == 7: body grabs entire right-hand expression."""
    assert parse_eval("let x = 3 in x * 2 + 1") == 7


def test_let_shadows_outer() -> None:
    """Nested let shadows the outer binding: let x=5 in let x=3 in x == 3."""
    assert parse_eval("let x = 5 in let x = 3 in x") == 3


def test_let_uses_outer_in_defn() -> None:
    """Inner let can reference outer binding in its definition."""
    assert parse_eval("let x = 4 in let y = x * 2 in y + 1") == 9


def test_let_with_power() -> None:
    """let x = 2 in x ** 3 + 1 == 9: correct precedence inside let body."""
    assert parse_eval("let x = 2 in x ** 3 + 1") == 9


# ---------------------------------------------------------------------------
# Section 6: Conditional expressions
# ---------------------------------------------------------------------------


def test_if_true_branch() -> None:
    """if 1 then 10 else 20 evaluates to 10 (condition is truthy)."""
    assert parse_eval("if 1 then 10 else 20") == 10


def test_if_false_branch() -> None:
    """if 0 then 10 else 20 evaluates to 20 (condition is falsy)."""
    assert parse_eval("if 0 then 10 else 20") == 20


def test_if_with_comparison_condition() -> None:
    """if 3 > 2 then 10 else 20 == 10: condition is a comparison expression."""
    assert parse_eval("if 3 > 2 then 10 else 20") == 10


def test_if_else_body_extends_right() -> None:
    """else branch grabs the full expression: if 1 then 1 else 2 + 3 == 1."""
    assert parse_eval("if 1 then 1 else 2 + 3") == 1


def test_if_else_extends_into_arithmetic() -> None:
    """if 0 then 1 else 2 + 3 == 5: else body is 2+3, not just 2."""
    assert parse_eval("if 0 then 1 else 2 + 3") == 5


def test_if_nested_in_let() -> None:
    """let x=3 in if x > 2 then x * 2 else x + 1 == 6."""
    assert parse_eval("let x = 3 in if x > 2 then x * 2 else x + 1") == 6


# ---------------------------------------------------------------------------
# Section 7: Complex / combined expressions
# ---------------------------------------------------------------------------


def test_complex_arithmetic() -> None:
    """2 ** 10 == 1024."""
    assert parse_eval("2 ** 10") == 1024


def test_complex_nested_let() -> None:
    """let a=2 in let b=3 in a**b + b**a == 8+9 == 17."""
    assert parse_eval("let a = 2 in let b = 3 in a ** b + b ** a") == 17


def test_complex_boolean_expression() -> None:
    """(1 < 2) and not (3 == 4) == 1: both sub-expressions are true."""
    assert parse_eval("1 < 2 and not 3 == 4") == 1


def test_variable_in_comparison() -> None:
    """Variables work inside comparisons inside let."""
    assert parse_eval("let n = 5 in n > 3") == 1


# ---------------------------------------------------------------------------
# Section 8: Error cases
# ---------------------------------------------------------------------------


def test_lexing_error_on_unknown_char() -> None:
    """An unrecognised character raises LexingError."""
    with pytest.raises(LexingError):
        parse_eval("1 + @")


def test_parsing_error_on_double_operator() -> None:
    """Two consecutive operators raise ParsingError."""
    with pytest.raises(ParsingError):
        parse_eval("1 + * 2")


def test_parsing_error_on_unclosed_paren() -> None:
    """An unclosed parenthesis raises ParsingError."""
    with pytest.raises(ParsingError):
        parse_eval("(1 + 2")


def test_parsing_error_on_empty_input() -> None:
    """An empty token stream (no expression) raises ParsingError."""
    with pytest.raises(ParsingError):
        parse_eval("")


def test_lexing_error_lineno() -> None:
    """LexingError on the second line carries lineno=2."""
    with pytest.raises(LexingError) as exc_info:
        parse_eval("1 + 2\n@ + 3")
    assert exc_info.value.lineno == 2


def test_parsing_error_contains_expected_tokens() -> None:
    """ParsingError exposes the set of expected token types."""
    with pytest.raises(ParsingError) as exc_info:
        parse_eval("1 +")
    assert len(exc_info.value.expected) > 0
