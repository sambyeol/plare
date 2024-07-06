from argparse import ArgumentParser
from pathlib import Path

from plare.lexer import Lexer, Token
from plare.parser import Parser


class NUM(Token):
    def __init__(self, value: str, *, lineno: int, offset: int) -> None:
        super().__init__(value, lineno=lineno, offset=offset)
        self.value = int(value)


class PLUS(Token):
    pass


class MINUS(Token):
    pass


class STAR(Token):
    precedence = 1


class SLASH(Token):
    precedence = 1


class LPAREN(Token):
    pass


class RPAREN(Token):
    pass


class Tree:
    pass


class Const(Tree):
    __match_args__ = ("value",)

    def __init__(self, n: NUM, /) -> None:
        self.value = n.value

    def __str__(self) -> str:
        return str(self.value)


class Add(Tree):
    __match_args__ = ("left", "right")

    def __init__(self, left: Tree, right: Tree, /) -> None:
        self.left = left
        self.right = right

    def __str__(self) -> str:
        return f"({self.left} + {self.right})"


class Sub(Tree):
    __match_args__ = ("left", "right")

    def __init__(self, left: Tree, right: Tree, /) -> None:
        self.left = left
        self.right = right

    def __str__(self) -> str:
        return f"({self.left} - {self.right})"


class Mul(Tree):
    __match_args__ = ("left", "right")

    def __init__(self, left: Tree, right: Tree, /) -> None:
        self.left = left
        self.right = right

    def __str__(self) -> str:
        return f"({self.left} * {self.right})"


class Div(Tree):
    __match_args__ = ("left", "right")

    def __init__(self, left: Tree, right: Tree, /) -> None:
        self.left = left
        self.right = right

    def __str__(self) -> str:
        return f"({self.left} / {self.right})"


def calc(exp: Tree) -> int:
    match exp:
        case Const(value):
            return value
        case Add(left, right):
            return calc(left) + calc(right)
        case Sub(left, right):
            return calc(left) - calc(right)
        case Mul(left, right):
            return calc(left) * calc(right)
        case Div(left, right):
            return calc(left) // calc(right)
        case _:
            raise ValueError("Invalid expression")


def main():
    parser = ArgumentParser()
    parser.add_argument("src", type=str, help="source file with arithmetic expression")

    args = parser.parse_args()

    lexer = Lexer(
        {
            "start": [
                (r"//", "comment"),
                (r"[ \t\n]+", "start"),
                (r"-?(0|[1-9][0-9]*)", NUM),
                (r"\+", PLUS),
                (r"-", MINUS),
                (r"\*", STAR),
                (r"/", SLASH),
                (r"\(", LPAREN),
                (r"\)", RPAREN),
            ],
            "comment": [
                (r"//", "start"),
                (r".", "comment"),
            ],
        },
        lambda: None,
    )

    parser = Parser[Tree](
        {
            "exp": [
                (["exp", PLUS, "exp"], Add, [0, 2]),
                (["exp", MINUS, "exp"], Sub, [0, 2]),
                (["exp", STAR, "exp"], Mul, [0, 2]),
                (["exp", SLASH, "exp"], Div, [0, 2]),
                ([LPAREN, "exp", RPAREN], None, [1]),
                ([NUM], Const, [0]),
            ]
        }
    )

    print(f"== Source ({args.src}) ==")
    src = Path(args.src).read_text()
    src = parser.parse("exp", lexer.lex("start", src))
    print(src)
    print(f"== Result ({args.src}) ==")
    print(calc(src))


if __name__ == "__main__":
    main()
