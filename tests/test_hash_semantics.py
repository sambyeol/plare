"""Tests for Item, State, and Token hash and equality contracts."""

from __future__ import annotations

from plare.parser import IDMaker, Item, State
from plare.token import Token


class TokA(Token):
    def __init__(self, value: str, *, lineno: int, offset: int) -> None:
        self.lineno = lineno
        self.offset = offset


class TokB(Token):
    def __init__(self, value: str, *, lineno: int, offset: int) -> None:
        self.lineno = lineno
        self.offset = offset


def make_item(left: str, right: list[type[Token] | str], loc: int = 0) -> Item[object]:
    return Item(left, right, IDMaker(0), 0, loc)


def test_item_equal_data_hash_equal() -> None:
    a = make_item("E", [TokA, "T"], loc=1)
    b = make_item("E", [TokA, "T"], loc=1)

    assert a == b
    assert hash(a) == hash(b)


def test_item_different_right_order_hash_different() -> None:
    a = make_item("E", [TokA, TokB])
    b = make_item("E", [TokB, TokA])

    assert a != b
    assert hash(a) != hash(b)


def test_state_equal_items_hash_equal() -> None:
    item_a = make_item("E", [TokA], loc=0)
    item_b = make_item("E", [TokA], loc=0)

    s1 = State(0, {item_a})
    s2 = State(1, {item_b})

    assert s1 == s2
    assert hash(s1) == hash(s2)


def test_token_hash_includes_class() -> None:
    a = TokA("x", lineno=1, offset=0)
    b = TokB("x", lineno=1, offset=0)

    assert a != b
    assert hash(a) != hash(b)


def test_token_same_class_same_position_equal() -> None:
    a = TokA("x", lineno=3, offset=5)
    b = TokA("y", lineno=3, offset=5)

    assert a == b
    assert hash(a) == hash(b)
