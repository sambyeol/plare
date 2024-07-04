from typing import Any

from plare.lexer import Token
from plare.parser import EOF, Parser


class PLUS(Token):
    pass


class NUM(Token):
    value: int

    def __init__(self, value: str, *, lineno: int, offset: int) -> None:
        super().__init__(value, lineno=lineno, offset=offset)
        self.value = int(value)

    def __hash__(self) -> int:
        return hash(self.value) + super().__hash__()

    def __eq__(self, other: Any) -> bool:
        return (
            isinstance(other, self.__class__)
            and self.value == other.value
            and super().__eq__(other)
        )


class Tree:
    pass


class Num(Tree):
    def __init__(self, value: NUM, /) -> None:
        self.value = value.value


def make_positive_integer_parser():
    return Parser(
        {
            "pgm": [
                (["exp"], None, [0]),
            ],
            "exp": [
                ([PLUS, "num"], None, [1]),
                (["num"], None, [0]),
            ],
            "num": [
                ([NUM], Num, [0]),
            ],
        }
    )


def test_parse_positive_integer_without_add():
    parser = make_positive_integer_parser()
    tree = parser.parse(
        "pgm", [NUM("1", lineno=1, offset=0), EOF("", lineno=1, offset=1)]
    )
    assert isinstance(tree, Num)
    assert tree.value == 1
