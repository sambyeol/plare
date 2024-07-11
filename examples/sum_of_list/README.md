# Sum of list with Plare

`sum.py` offers a simple sum of list implemented with `plare`.
To test the program first, run the following command.
```bash
$ python sum.py "[1, 2, 3, 4, 5]"
```
The program will parse the input, interprete, and show the answer as follows.
```
15
```

## Defining Language
To make a parser, first thing to do is defining a language.
The following is the language of the sum of list, where `N` represents an integer:
```
list -> N::list
      | [N]
      | [] 
```

A node in AST must initialized with `Token` objects or other node objects.
That is, You need to define 3 different type of list, which are initialized with different arguments, to support the arbitrary length of list: `IntList`, `SingleIntList`, and `EmptyIntList`.

## Defining Lexer
A lexer will tokenize the given source string.
To make a lexer you only have to do is make tokens that inherits`Token` class.
In this example, you only need to define 4 tokens: `COMMA`, `LBRACKET`, `RBRACKET`, and `NUM`.

## Defining Parser
A parser will parse the tokens and build an AST.
The CFG for the list is as follows:
```
list  -> LBRACKET items RBRACKET -> $1
items -> N COMMA items           -> IntList($0, $2)
       | N                       -> SingleIntList($0)
       |                         -> EmptyIntList()     
```

## Implementation
You can find implementation of the above example in `sum.py`.
