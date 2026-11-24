# Plare

A lexer/parser framework for Python 3.12+.
Plare lets you define a tokeniser and an LALR(1) parser using plain Python
classes and dictionaries — no code generation, no external grammar files.

## Features

- **Stateful lexer** — regex-driven, named states let you switch tokenisation
  modes mid-stream (e.g., to skip comments)
- **LALR(1) parser** — efficient shift/reduce parser with automatic conflict
  detection
- **Persistent parse-table cache** — automatically skip repeated LALR table construction
- **Operator precedence** — resolve shift/reduce conflicts by setting
  `precedence` and `associative` class variables on token classes
- **No build step** — install and import

## Installation

```bash
pip install plare
```

## Quick Example

```python
from plare.lexer import Lexer
from plare.parser import Parser
from plare.token import Token


class NUM(Token):
    def __init__(self, value: str, *, lineno: int, offset: int) -> None:
        super().__init__(value, lineno=lineno, offset=offset)
        self.value = int(value)


class PLUS(Token):
    pass


class Exp:
    value: int


class Const(Exp):
    def __init__(self, number: NUM) -> None:
        self.value = number.value


class Add(Exp):
    def __init__(self, left: Exp, right: Exp) -> None:
        self.value = left.value + right.value


lexer: Lexer[None] = Lexer({"start": [(r"\d+", NUM), (r"\+", PLUS), (r" +", "start")]})
parser: Parser[Exp] = Parser(
    {"exp": [(["exp", PLUS, "exp"], Add, [0, 2]), ([NUM], Const, [0])]}
)
result = parser.parse("exp", lexer.lex("start", "1 + 2"))
assert isinstance(result, Exp)
print(result.value)  # 3
```

## Upgrading from 1.6.0

- **Parser and conflicts.** Plare 2.0 uses LALR(1) lookaheads to choose reductions. When two reductions conflict at equal precedence, the production defined first wins.
- **Operator precedence and associativity.** Tokens default to right associativity. Set `associative = "left"` on operator token classes that need left grouping. A production defaults to the precedence of its rightmost terminal with nonzero precedence, or `0` if there is none. Supply a token class as the fourth item in `(rhs, action_type, arg_indices, prec_token)` to set the production's precedence explicitly.
- **Removed helpers.** `Rule.calc_first()`, `Rule.calc_follow()`, and `compute_follow_sets()` were removed. Use `compute_first_sets(rules)` to compute FIRST sets. `Table.resolve_conflict()` replaces `Table.force_update()`.
- **Error fields.** `LexingError` exposes `message`, `lineno`, and `offset`. `ParsingError` exposes `lineno`, `offset`, `token`, and `expected`.
- **Parse-table cache.** By default, `Parser` caches tables in `.plare/` under the current working directory. Pass a `cache_dir` path to change the directory or `cache_dir=None` to disable caching.

### Known limitations

- Start rules that share an LALR state can reject valid inputs when they need different reductions for the same lookahead. [#55](https://github.com/sambyeol/plare/issues/55)
- For duplicate productions, the parser can select the first definition even when a later one has higher explicit precedence. [#56](https://github.com/sambyeol/plare/issues/56)
- Unexpected end of input can report line `0` and expose the internal `EOS` token. [#57](https://github.com/sambyeol/plare/issues/57)
- An undefined nonterminal or unknown start rule can raise `KeyError`. [#58](https://github.com/sambyeol/plare/issues/58)

## Examples

- [`examples/calc/`](examples/calc/) — integer arithmetic with operator precedence
- [`examples/sum_of_list/`](examples/sum_of_list/) — list parsing with recursive grammar
