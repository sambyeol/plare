from __future__ import annotations

from typing import Any, Callable


class Token:
    def __init__(self, *, lineno: int, offset: int) -> None:
        self.lineno = lineno
        self.offset = offset

    def __hash__(self) -> int:
        return hash(self.lineno) + hash(self.offset)

    def __eq__(self, other: Any) -> bool:
        return (
            isinstance(other, self.__class__)
            and self.lineno == other.lineno
            and self.offset == other.offset
        )


class EOF(Token):
    pass


class EPSILON(Token):
    pass


class LexingState:
    pass


type Pattern = Callable[[str, LexingState, list[str], int, int], Token | str]
