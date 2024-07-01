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
