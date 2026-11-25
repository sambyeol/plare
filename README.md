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
from plare.parser import EOS, Parser
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


lexer: Lexer[None] = Lexer(
    {"start": [(r"\d+", NUM), (r"\+", PLUS), (r" +", "start"), (r"\Z", EOS)]}
)
parser: Parser[Exp] = Parser(
    {"exp": [(["exp", PLUS, "exp"], Add, [0, 2]), ([NUM], Const, [0])]}
)
result = parser.parse("exp", lexer.lex("start", "1 + 2"))
assert isinstance(result, Exp)
print(result.value)  # 3
```

Register `(r"\Z", EOS)` in each lexer state where input can end. When supplying tokens directly to `Parser.parse()`, include one `EOS` as the final token with the end-of-input position.

## Examples

- [`examples/calc/`](examples/calc/) — integer arithmetic with operator precedence
- [`examples/sum_of_list/`](examples/sum_of_list/) — list parsing with recursive grammar
