import re
from plare.exception import InvalidPattern


class Token:
    __slots__ = ("value", "id", "lineno", "offset")

    value: str
    id: str
    lineno: int
    offset: int

    def __init__(
        self,
        value: str,
        id: str,
        *,
        lineno: int,
        offset: int,
    ) -> None:
        self.value = value
        self.id = id
        self.lineno = lineno
        self.offset = offset

    def __hash__(self) -> int:
        return hash(self.value)

    def __eq__(self, other: Any) -> bool:
        return (
            isinstance(other, Token)
            and self.id == other.id
            and self.value == other.value
            and self.lineno == other.lineno
            and self.offset == other.offset
        )


class Pattern:
    __slots__ = ("regex", "id")

    regex: re.Pattern[str]
    id: str

    def __init__(self, regex: str, id: str) -> None:
        self.regex = re.compile(regex)
        self.id = id

    def __call__(self, value: str, *, lineno: int, offset: int) -> Token:
        if self.regex.fullmatch(value) is None:
            raise InvalidPattern(f"Pattern {self.id} does not match: {value}")
        return Token(value, self.id, lineno=lineno, offset=offset)

    def __hash__(self) -> int:
        return hash(self.id)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Pattern) and self.id == other.id

    def __repr__(self) -> str:
        return self.id

    def __str__(self) -> str:
        return repr(self)
