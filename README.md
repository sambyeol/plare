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

lexer = Lexer({"start": [(r"\d+", NUM), (r"\+", PLUS), (r" +", "start")]})
parser = Parser({"exp": [(["exp", PLUS, "exp"], Add, [0, 2]), ([NUM], Const, [0])]})
```

## Parse-table cache

Plare automatically caches generated LALR tables in `<project_root>/.plare`, treating the current working directory as the project root. Each grammar uses its own fingerprinted JSON file, and compatible tables are reused across process runs:

```python
parser = Parser(grammar)
```

Pass `cache_dir=None` to disable caching or provide another directory with `cache_dir="path/to/cache"`.

Plare creates missing cache directories and writes each table atomically. Grammar structure, rule order, token precedence or associativity, `%prec`, and the Plare version automatically determine cache compatibility; corrupt or unreadable cache files are ignored and rebuilt. Semantic action classes and argument lists are always taken from the current grammar rather than the cached file.

## Examples

- [`examples/calc/`](examples/calc/) — integer arithmetic with operator precedence
- [`examples/sum_of_list/`](examples/sum_of_list/) — list parsing with recursive grammar
