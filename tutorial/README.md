# Calculator with Plare

```calc.py``` offers very simple integer arithmetic calculation implemented with ```plare```.
To test the program first, run the following command.
```bash
$ python calc.py examples/ex02.calc
```
The program will parse the ```example/ex02.calc```, interprete, and show the answer as follows.
```
This is a tutorial integer calculation project with plare

== examples/ex02.calc ==
1 + 1 * 2
// answer: 3 //
========================
answer: 3
========================
```
Note that the program correctly parse the program considering the precedence of multiplication and addition.

## Define Language
To make a parser, you first have to define a language.
```plare``` offers ```Type``` class that helps you to define a new type.
The following is the language of the calculator, where ```n``` represents the integer.
```
num -> n
exp -> num
     | exp + exp
     | exp - exp
     | exp * exp
     | exp / exp
```
The following is the language of the calculator defined with ```plare```.
```python
from plare import build_lang
from plare import Type

num = Type('num', alias=int)
exp = Type('exp',
  Const=[num],
  Add=['exp', 'exp'],
  Sub=['exp', 'exp'],
  Mul=['exp', 'exp'],
  Div=['exp', 'exp'])
num, exp = build_lang(num, exp)
```
A new type ```num``` is alias with the python type ```int```, and ```exp``` consists of 5 constructors with the argument types of each constructor defined on the right.
If you have recursive (or mutually recursive) type definitions, just put the name of the type as a python string.
```build_lang``` will process the recursive (or mutually recursive) types.

## Define Lexer
Lexer will help tokenizing the given source code.
To make a lexer you only have to do is make tokens with ```Token``` class and corresponding python regular expressions.
```Lexer``` class will generate a lexer with the tokens and regular expressions defined previously.
```python
from plare import Lexer
from plare import Token

TOKENS = {
  Token('CONST', int): r'-?(0|[1-9][0-9]*)',
  Token('PLUS'): r'\+',
  Token('MINUS'): r'-',
  Token('STAR'): r'\*',
  Token('SLASH'): r'/',
  Token('LPAREN'): r'\(',
  Token('RPAREN'): r'\)',
}
IGNORES = {
  Token('WHITESPACE'): r'[ \t\n]+',
  Token('COMMENT'): r'//.*//',
}

lexer = Lexer(TOKENS, ignore=IGNORES)
```
Note that ```Lexer``` class gets python dictionaries of tokens and regular expressions, and will not pass the tokens matching to the ```ignore```.

## Define Parser
The parsing rule of the calculator is as follows.
The left-hand side of ```:``` is a variable and the right-hand side of ```->``` is a constructing rule for each matching case.
```
P: E -> $1
E: N -> exp.Const($1)
 | ( E ) -> $2
 | E + E -> exp.Add($1, $3)
 | E - E -> exp.Sub($1, $3)
 | E * E -> exp.Mul($1, $3)
 | E / E -> exp.Div($1, $3)
N: CONST -> num($1)
```
The same parsing rules defined with ```plare``` is as follows. Note that ```lexer```, which generated above, has a set of compiled tokens, and compiled tokens from ```lexer``` are used while defining parsing rules.
```python
from plare import build_grammar
from plare import Rule

TOKENS = lexer.TOKENS

P = Rule('P', 
  (['E'], None, ['$1']))
E = Rule('E',
  ([TOKENS.CONST], exp.Const, ['$1']),
  ([TOKENS.LPAREN, 'E', TOKENS.RPAREN], None, ['$2']),
  (['E', TOKENS.PLUS, 'E'], exp.Add, ['$1', '$3']),
  (['E', TOKENS.MINUS, 'E'], exp.Sub, ['$1', '$3']),
  (['E', TOKENS.STAR, 'E'], exp.Mul, ['$1', '$3']),
  (['E', TOKENS.SLASH, 'E'], exp.Div, ['$1', '$3']))
N = Rule('N',
  ([TOKENS.CONST], num, ['$1']))
P, E, N = build_grammar(P, E, N)
```
As in defining language above, recursive (or mutually recursive) rules will be proccessed by ```build_grammar``` function.
```Parser``` class will generate a parser based on ```lexer``` and parsing rules defined previously.
```python
from plare import Parser

parser = Parser(lexer, [P, E, N], P, precedence={TOKENS.STAR: 1, TOKENS.SLASH: 1})
```
The third argument of the ```Parser``` is identifying the starting variable, and ```precedence``` argument will let ```Parser``` know the precedence of the tokens. By default, all token have precedence of ```0```, and left associativity. If you want to make some of the tokens to have right associativity, just pass the list of tokens to a ```right_associativity``` argument.

## Parse Source
```parse``` method in ```parser``` will generate a parsed tree from the source code which is a python string.
``` python
src = '1 + 2 * 3 - 4' # read a source code here
tree = parser.parse(src)
```

## Interprete
Each node of the parsed tree have two variable: ```data```, which represents the type of the node, and ```chidren``` which is a list that contains its child nodes.
Following python code is an interpretation method for the calculator.
```python
def interprete(tree):
  if tree.data == 'Const':
    return tree.children[0]
  elif tree.data == 'Add':
    return interprete(tree.children[0]) + interprete(tree.children[1])
  elif tree.data == 'Sub':
    return interprete(ast.children[0]) - interprete(tree.children[1])
  elif tree.data == 'Mul':
    return interprete(tree.children[0]) * interprete(tree.children[1])
  else: # tree.data == 'Div'
    return interprete(tree.children[0]) // interprete(tree.children[1])

result = interprete(tree)
print('answer: {}'.format(result))
# answer: 3
```

## Run
This folder contains ```calc.py``` file which is a exemplary implemtation of calculator and ```examples``` folder which has a few example cases.
This python script takes one or more ```*.calc``` files and interprete the result.
Following command will show the interpretation results of 3 files: ```examples/ex01.calc```, ```examples/ex02.calc```, and ```examples/ex03.calc```.
```bash
$ python calc.py examples/ex01.calc examples/ex02.calc examples/ex03.calc
```
The output of the above command is as follows.
```
This is a tutorial integer calculation project with plare

== examples/ex01.calc ==
1 + 1
// answer: 2 //
========================
answer: 2
========================

== examples/ex02.calc ==
1 + 1 * 2
// answer: 3 //
========================
answer: 3
========================

== examples/ex03.calc ==
(1 + 1) * 2
// answer: 4 //
========================
answer: 4
========================
```
