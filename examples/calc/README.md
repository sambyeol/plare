# Calculator with Plare

`calc.py` offers very simple integer arithmetic calculation implemented with `plare`.
To test the program first, run the following command.
```bash
$ python calc.py data/ex02.calc
```
The program will parse the `data/ex02.calc`, interprete, and show the answer as follows.
```
== Source (data/ex02.calc) ==
(1 + (1 * 2))
== Result (data/ex02.calc) ==
3
```
Note that the program correctly parse the program considering the precedence of multiplication and addition.

## Defining Language
To make a parser, first thing to do is defining a language.
The following is the language of the calculator, where `N` represents an integer:
```
exp -> N
     | exp + exp
     | exp - exp
     | exp * exp
     | exp / exp
```

A node in AST must initialized with `Token` objects, which will be explained in the lexer section, or other node objects.
For example, `Const` node gets a `NUM` object, where `NUM` is a subclass of `Token`:
```python
class Const(Exp):
    def __init__(self, n: NUM) -> None:
          self.value = n.value
```
On the other hand, `Add` node gets 2 `Exp` objects:
```python
class Add:
    def __init__(self, left: Exp, right: Exp) -> None:
        self.left = left
        self.right = right
```


## Defining Lexer
A lexer will tokenize the given source string.
To make a lexer you only have to do is make tokens that inherits`Token` class.
For example, `+` can be defined as follows:
```python
from plare.token import Token

class PLUS(Token):
    pass
```

Token stores the line number (`lineno`) and the offset (`offset`) by default.
You can store more information inside the token by overriding `__init__` function which gets a matching string as an argument.
For example, you can make a number token, which stores the integer value of matching string as follows:
```python
class NUM(Token):
    def __init__(self, value: str, *, lineno: int, offset: int) -> None:
        super().__init__(value, lineno=lineno, offset=offset) # To make default attributs
        self.value = int(value)
```

Now, you can define a lexer based on regular expressions to match and the tokens you defined.
A lexing rule is a tuple of a regular expression and a token to create.
For example, the following rule will create a `PLUS` token when it matches `+`:
```python
{
    "start": [
        (r"\+", PLUS),
        ...
    ]
}
```
You can switch to other lexing rules, by assigning a string instead of a `Token`.
The following code will switchin to `"comment"` mode when the string starts with `//`:
```python
{
    "start": [
        (r"//", "comment"),
        ...
    ],
    "comment": [
        (r"//", "start"),
        (r".", "comment"),
    ]
}
```
After defining lexing rules, you can make a lexer with `Lexer`, like:
```python
from plare.lexer import Lexer

lexer = Lexer({ ... })
```

The `lex` method in the lexer gets a start rule set and string to parse and will returns a generator of `Token`s sequentially.
For example, you can start to parse `"1 + 2"` from `"start"` as follows:
```python
lexed = lexer.lex("start", "1 + 2")
```


## Defining Parser
A parser convert a sequence of tokens into a desired form of tree based on a context free grammar (CFG).
The CFG for the calculator is as follows:
```
exp -> NUM                -> Const($$)
     | exp PLUS exp       -> Add($0, $2)
     | exp MINUS exp      -> Sub($0, $2)
     | exp STAR exp       -> Mul($0, $2)
     | exp SLASH exp      -> Div($0, $2)
     | LPAREN exp RPAREN  -> $1
```
A parsing rule is a tuple of a grammar pattern, a class to create and indices of arguments to use.
For example, the following rule will create an `Add` object based on 1st and 3rd matched sub trees (0-indexed):
```python
{
    "exp": [
        (["exp", PLUS, "exp"], Add, [0, 2]),
        ...
    ]
}
```

You can bypass the creation of object with `None`.
Note that if you use `None`, the number of arguments to use must be 1.
For example, you can pass the 2nd subtree like following:
```python
{
    "exp": [
        ([LPAREN, "exp", RPAREN], None, [1]),
        ...
    ]
}
```

After defining grannar, you can make a parser with `Parser`, like:
```python
from plare.parser import Parser

parser = Parser({ ... })
```

The `parse` method in the parser gets a start non-terminal symbol and an iterable sequence of `Token` and returns a parsed tree.
For example, you can parse `"1 + 2"` into `exp`, using `lexer` defined above, like:
```python
parsed = parser.parse("exp", lexer.lex("start", "1 + 2"))
```

## Resolving conflicts
You can resolve conflicts between shift and reduce actions based on "precedence" and "associative".
The precedence and associative can be defined as class variable when defining tokens.
By default, all token have precedence of `0` and and `"left"` associative.
In this example, `STAR` and `DIV` have higher precedence, which means `1 + 2 * 3` will be parsed into `(1 + (2 * 3))`, not `((1 + 2) * 3)`.

## Interprete
This part has nothing to do with Plare.
You can see the implementation in `calc.py`.
