from __future__ import annotations

from typing import Any

from plare.parser import EOF, Parser
from plare.token import Token


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


def make_positive_integer_parser() -> Parser[Tree]:
    return Parser[Tree](
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


def test_minimal_empty_rule_parser():
    parser = Parser({"pgm": [([], list[int], [])]})
    parsed = parser.parse("pgm", [EOF("", lineno=1, offset=0)])
    assert isinstance(parsed, list)
    assert len(parsed) == 0


class LBRACKET(Token):
    pass


class RBRACKET(Token):
    pass


class COMMA(Token):
    pass


class IntList:
    items: list[int]

    def __init__(self, item: int, tail: IntList) -> None:
        self.items = [item, *tail.items]


class EmptyIntList(IntList):
    def __init__(self) -> None:
        self.items = []


def make_list_parser() -> Parser[IntList]:
    return Parser[IntList](
        {
            "list": [
                ([LBRACKET, "items", RBRACKET], None, [1]),
            ],
            "items": [
                ([NUM, COMMA, "items"], IntList, [0, 1]),
                ([], EmptyIntList, []),
            ],
        }
    )


def test_parse_empty_intlist():
    parser = make_list_parser()
    tree = parser.parse(
        "list",
        [
            LBRACKET("[", lineno=1, offset=0),
            RBRACKET("]", lineno=1, offset=1),
            EOF("", lineno=1, offset=2),
        ],
    )
    assert isinstance(tree, IntList)
    assert len(tree.items) == 0
