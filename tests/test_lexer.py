from typing import Any

from plare.lexer import LexingState, Token


class PLUS(Token):
    pass


class NUM(Token):
    value: int

    def __init__(self, value: str, *, lineno: int, offset: int) -> None:
        super().__init__(lineno=lineno, offset=offset)
        self.value = int(value)

    def __hash__(self) -> int:
        return hash(self.value) + super().__hash__()

    def __eq__(self, other: Any):
        return (
            isinstance(other, self.__class__)
            and self.value == other.value
            and super().__eq__(other)
        )


class ID(Token):
    value: str

    def __init__(self, value: str, *, lineno: int, offset: int) -> None:
        super().__init__(lineno=lineno, offset=offset)
        self.value = value

    def __hash__(self) -> int:
        return hash(self.value) + super().__hash__()

    def __eq__(self, other: Any):
        return (
            isinstance(other, self.__class__)
            and self.value == other.value
            and super().__eq__(other)
        )


def test_token_attributes():
    token = ID("x", lineno=1, offset=0)
    assert token.value == "x"
    assert token.lineno == 1
    assert token.offset == 0


def PLUSPattern(
    matched: str,
    state: LexingState,
    entries: list[str],
    lineno: int,
    offset: int,
) -> PLUS:
    return PLUS(lineno=lineno, offset=offset)


def NUMPattern(
    matched: str,
    state: LexingState,
    entries: list[str],
    lineno: int,
    offset: int,
) -> NUM:
    return NUM(matched, lineno=lineno, offset=offset)


def test_pattern_creates_token_python_variable():
    token = PLUSPattern("+", LexingState(), [], 1, 0)
    assert isinstance(token, PLUS)
    assert token.lineno == 1
    assert token.offset == 0


def test_pattern_creates_token_integer():
    token = NUMPattern("123", LexingState(), [], 1, 0)
    assert isinstance(token, NUM)
    assert token.value == 123
    assert token.lineno == 1
    assert token.offset == 0
