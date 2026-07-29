from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from typing import Any

import pytest

import plare.parser as parser_module
from plare.parser import Parser
from plare.token import Token


class NUM_C(Token):
    def __init__(self, value: str, *, lineno: int, offset: int) -> None:
        super().__init__(value, lineno=lineno, offset=offset)
        self.value = int(value)


class PLUS_C(Token):
    precedence = 1
    associative = "left"


class PREC_C(Token):
    precedence = 1


class NumC:
    def __init__(self, token: NUM_C) -> None:
        self.value = token.value


class AddC:
    def __init__(self, left: Any, right: Any) -> None:
        self.left = left
        self.right = right


def expression_grammar() -> dict[
    str,
    list[tuple[list[type[Token] | str], type[Any] | None, list[int]]],
]:
    return {
        "expr": [
            (["expr", PLUS_C, "expr"], AddC, [0, 2]),
            ([NUM_C], NumC, [0]),
        ]
    }


def expression_tokens() -> list[Token]:
    return [
        NUM_C("1", lineno=1, offset=0),
        PLUS_C("+", lineno=1, offset=1),
        NUM_C("2", lineno=1, offset=2),
        PLUS_C("+", lineno=1, offset=3),
        NUM_C("3", lineno=1, offset=4),
    ]


def assert_expression_result(result: object, *, left_associative: bool) -> None:
    assert isinstance(result, AddC)
    branch = result.left if left_associative else result.right
    assert isinstance(branch, AddC)


def fail_if_table_is_built(*args: object, **kwargs: object) -> None:
    raise AssertionError("parse table should have been loaded from cache")


def test_cache_miss_writes_file_and_hit_skips_table_build(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache_path = tmp_path / "nested" / "expression.json"

    first = Parser(expression_grammar(), cache_path=str(cache_path))

    assert first.cache_hit is False
    assert cache_path.is_file()
    assert_expression_result(
        first.parse("expr", expression_tokens()), left_associative=True
    )

    monkeypatch.setattr(
        parser_module, "compute_lalr1_lookaheads", fail_if_table_is_built
    )
    second = Parser(expression_grammar(), cache_path=cache_path)

    assert second.cache_hit is True
    assert second.entry_state == first.entry_state
    assert_expression_result(
        second.parse("expr", expression_tokens()), left_associative=True
    )


def test_cache_rebinds_current_local_semantic_action(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class First:
        def __init__(self, left: NUM_C, right: NUM_C) -> None:
            self.values = (left.value, right.value)

    class Second:
        def __init__(self, right: NUM_C, left: NUM_C) -> None:
            self.values = (right.value, left.value)

    cache_path = tmp_path / "local-action.json"
    Parser(
        {"value": [([NUM_C, PLUS_C, NUM_C], First, [0, 2])]},
        cache_path=cache_path,
    )
    monkeypatch.setattr(
        parser_module, "compute_lalr1_lookaheads", fail_if_table_is_built
    )

    cached = Parser(
        {"value": [([NUM_C, PLUS_C, NUM_C], Second, [2, 0])]},
        cache_path=cache_path,
    )
    result = cached.parse(
        "value",
        [
            NUM_C("4", lineno=1, offset=0),
            PLUS_C("+", lineno=1, offset=1),
            NUM_C("7", lineno=1, offset=2),
        ],
    )

    assert cached.cache_hit is True
    assert isinstance(result, Second)
    assert result.values == (7, 4)


def test_cache_preserves_non_alphabetical_entry_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    grammar = {
        "z_value": [([NUM_C], NumC, [0])],
        "a_value": [([NUM_C], NumC, [0])],
    }
    cache_path = tmp_path / "entry-order.json"
    first = Parser(grammar, cache_path=cache_path)
    monkeypatch.setattr(
        parser_module, "compute_lalr1_lookaheads", fail_if_table_is_built
    )

    cached = Parser(grammar, cache_path=cache_path)

    assert cached.cache_hit is True
    assert (
        list(cached.entry_state)
        == list(first.entry_state)
        == [
            "z_value",
            "a_value",
        ]
    )


def test_token_conflict_metadata_change_invalidates_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache_path = tmp_path / "associativity.json"
    first = Parser(expression_grammar(), cache_path=cache_path)
    assert_expression_result(
        first.parse("expr", expression_tokens()), left_associative=True
    )

    monkeypatch.setattr(PLUS_C, "associative", "right")
    second = Parser(expression_grammar(), cache_path=cache_path)

    assert second.cache_hit is False
    assert_expression_result(
        second.parse("expr", expression_tokens()), left_associative=False
    )


def test_grammar_structure_change_invalidates_cache(tmp_path: Path) -> None:
    cache_path = tmp_path / "grammar.json"
    Parser({"value": [([NUM_C], NumC, [0])]}, cache_path=cache_path)

    changed = Parser(
        {"value": [([PLUS_C, NUM_C], NumC, [1])]},
        cache_path=cache_path,
    )
    result = changed.parse(
        "value",
        [
            PLUS_C("+", lineno=1, offset=0),
            NUM_C("9", lineno=1, offset=1),
        ],
    )

    assert changed.cache_hit is False
    assert isinstance(result, NumC)
    assert result.value == 9


def test_prec_token_change_invalidates_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache_path = tmp_path / "prec.json"
    grammar = {"value": [([NUM_C], NumC, [0], PREC_C)]}
    Parser(grammar, cache_path=cache_path)

    monkeypatch.setattr(PREC_C, "precedence", 2)
    changed = Parser(grammar, cache_path=cache_path)

    assert changed.cache_hit is False


@pytest.mark.parametrize("contents", ["", "{", "[]", '{"version": 1}'])
def test_corrupt_cache_is_rebuilt(
    contents: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache_path = tmp_path / "corrupt.json"
    cache_path.write_text(contents, encoding="utf-8")

    rebuilt = Parser(expression_grammar(), cache_path=cache_path)

    assert rebuilt.cache_hit is False
    assert_expression_result(
        rebuilt.parse("expr", expression_tokens()), left_associative=True
    )

    monkeypatch.setattr(
        parser_module, "compute_lalr1_lookaheads", fail_if_table_is_built
    )
    cached = Parser(expression_grammar(), cache_path=cache_path)
    assert cached.cache_hit is True


def test_deeply_nested_cache_is_rebuilt(tmp_path: Path) -> None:
    cache_path = tmp_path / "deeply-nested.json"
    cache_path.write_text("[" * 10_000 + "]" * 10_000, encoding="utf-8")

    rebuilt = Parser(expression_grammar(), cache_path=cache_path)

    assert rebuilt.cache_hit is False
    assert_expression_result(
        rebuilt.parse("expr", expression_tokens()), left_associative=True
    )


def test_cache_io_failure_does_not_break_parser(tmp_path: Path) -> None:
    cache_path = tmp_path / "cache-is-a-directory"
    cache_path.mkdir()

    parser = Parser(expression_grammar(), cache_path=cache_path)

    assert parser.cache_hit is False
    assert_expression_result(
        parser.parse("expr", expression_tokens()), left_associative=True
    )
    assert not list(tmp_path.glob(f".{cache_path.name}.*.tmp"))


def test_concurrent_cache_initialization_is_atomic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache_path = tmp_path / "concurrent" / "expression.json"
    barrier = Barrier(4)

    def construct_and_parse(_: int) -> object:
        barrier.wait()
        parser = Parser(expression_grammar(), cache_path=cache_path)
        return parser.parse("expr", expression_tokens())

    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(construct_and_parse, range(8)))

    for result in results:
        assert_expression_result(result, left_associative=True)

    monkeypatch.setattr(
        parser_module, "compute_lalr1_lookaheads", fail_if_table_is_built
    )
    cached = Parser(expression_grammar(), cache_path=cache_path)
    assert cached.cache_hit is True
