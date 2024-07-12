from __future__ import annotations

from argparse import ArgumentParser
from typing import Any

from plare.lexer import Lexer
from plare.parser import Parser
from plare.token import Token


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


class LBRACKET(Token):
    pass


class RBRACKET(Token):
    pass


class COMMA(Token):
    pass


class IntList:
    items: list[int]

    def __init__(self, item: NUM, tail: IntList) -> None:
        self.items = [item.value, *tail.items]


class SingleIntList(IntList):
    def __init__(self, item: NUM) -> None:
        self.items = [item.value]


class EmptyIntList(IntList):
    def __init__(self) -> None:
        self.items = []


def main() -> None:
    argparser = ArgumentParser()
    argparser.add_argument("input", type=str)
    args = argparser.parse_args()

    lexer = Lexer(
        {
            "start": [
                (r"[ \t\n]+", "start"),
                (r"\[", LBRACKET),
                (r"\]", RBRACKET),
                (r",", COMMA),
                (r"-?\d+", NUM),
            ]
        }
    )

    parser = Parser[IntList](
        {
            "list": [
                ([LBRACKET, "items", RBRACKET], None, [1]),
            ],
            "items": [
                ([NUM, COMMA, "items"], IntList, [0, 2]),
                ([NUM], SingleIntList, [0]),
                ([], EmptyIntList, []),
            ],
        }
    )

    lexbuf = lexer.lex("start", args.input)
    parsed = parser.parse("list", lexbuf)
    if isinstance(parsed, Token):  # Just for type checking
        raise Exception("Something went wrong")
    print(sum(parsed.items))


if __name__ == "__main__":
    main()
