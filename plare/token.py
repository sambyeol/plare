from typing import Any, Literal

from plare.utils import logger

type assoc = Literal["left", "right"]


class Token:
    associative: assoc = "left"
    precedence: int = 0

    def __init__(self, value: str, *, lineno: int, offset: int) -> None:
        logger.debug(
            "Token created: %s(%s) @ (%s, %s)",
            self.__class__.__name__,
            repr(value),
            lineno,
            offset,
        )
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
