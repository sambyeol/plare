from plare.lexer import Token


def test_token_attributes():
    token = Token("x", "ID", lineno=1, offset=0)
    assert token.value == "x"
    assert token.id == "ID"
    assert token.lineno == 1
    assert token.offset == 0
