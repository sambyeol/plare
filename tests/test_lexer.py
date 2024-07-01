import pytest

from plare.exception import InvalidPattern
from plare.lexer import Pattern, Token


def test_token_attributes():
    token = Token("x", "ID", lineno=1, offset=0)
    assert token.value == "x"
    assert token.id == "ID"
    assert token.lineno == 1
    assert token.offset == 0


def test_pattern_creates_token_python_variable():
    ID = Pattern(r"[a-zA-Z_][a-zA-Z0-9_]*", "ID")
    assert ID.id == "ID"
    token = ID("x", lineno=1, offset=0)
    assert token.value == "x"
    assert token.id == "ID"
    assert token.lineno == 1
    assert token.offset == 0


def test_pattern_creates_token_integer():
    INT = Pattern(r"[0-9]+", "INT")
    assert INT.id == "INT"
    token = INT("42", lineno=1, offset=0)
    assert token.value == "42"
    assert token.id == "INT"
    assert token.lineno == 1
    assert token.offset == 0


def test_pattern_failed_when_pattern_does_not_match():
    INT = Pattern(r"[0-9]+", "INT")
    with pytest.raises(InvalidPattern):
        INT("x", lineno=1, offset=0)
