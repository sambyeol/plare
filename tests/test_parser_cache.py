from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from typing import Any

import pytest

import plare
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


def only_cache_file(cache_dir: Path) -> Path:
    cache_files = sorted(cache_dir.glob("*.json"))
    assert len(cache_files) == 1
    return cache_files[0]


def test_cache_version_follows_plare_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache_dir = tmp_path / "version"
    Parser(expression_grammar(), cache_dir=cache_dir)
    cache_file = only_cache_file(cache_dir)
    payload = json.loads(cache_file.read_text(encoding="utf-8"))

    assert "PARSER_TABLE_CACHE_VERSION" not in vars(parser_module)
    assert payload["version"] == plare.__version__

    monkeypatch.setattr(plare, "__version__", "999.0.0")
    rebuilt = Parser(expression_grammar(), cache_dir=cache_dir)
    rewritten = json.loads(cache_file.read_text(encoding="utf-8"))

    assert rebuilt.cache_hit is False
    assert only_cache_file(cache_dir) == cache_file
    assert rewritten["version"] == "999.0.0"


def test_default_cache_directory_is_project_root_plare(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    first = Parser(expression_grammar())

    cache_dir = tmp_path / ".plare"
    assert first.cache_hit is False
    assert only_cache_file(cache_dir).is_file()

    monkeypatch.setattr(
        parser_module, "compute_lalr1_lookaheads", fail_if_table_is_built
    )
    cached = Parser(expression_grammar())

    assert cached.cache_hit is True


def test_default_cache_keeps_multiple_grammars(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    first_grammar = {"value": [([NUM_C], NumC, [0])]}
    second_grammar = {
        "value": [([PLUS_C, NUM_C], NumC, [1])],
    }

    Parser(first_grammar)
    Parser(second_grammar)

    cache_dir = tmp_path / ".plare"
    assert len(list(cache_dir.glob("*.json"))) == 2

    monkeypatch.setattr(
        parser_module, "compute_lalr1_lookaheads", fail_if_table_is_built
    )
    assert Parser(first_grammar).cache_hit is True
    assert Parser(second_grammar).cache_hit is True


def test_cache_directory_none_disables_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    parser = Parser(expression_grammar(), cache_dir=None)

    assert parser.cache_hit is False
    assert not (tmp_path / ".plare").exists()


def test_parser_module_has_no_private_top_level_names() -> None:
    private_names = sorted(
        name
        for name in vars(parser_module)
        if name.startswith("_") and not name.startswith("__")
    )
    assert private_names == []


def test_cache_miss_writes_file_and_hit_skips_table_build(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache_dir = tmp_path / "nested" / "cache"

    first = Parser(expression_grammar(), cache_dir=str(cache_dir))

    assert first.cache_hit is False
    assert only_cache_file(cache_dir).is_file()
    assert_expression_result(
        first.parse("expr", expression_tokens()), left_associative=True
    )

    monkeypatch.setattr(
        parser_module, "compute_lalr1_lookaheads", fail_if_table_is_built
    )
    second = Parser(expression_grammar(), cache_dir=cache_dir)

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

    cache_dir = tmp_path / "local-action"
    Parser(
        {"value": [([NUM_C, PLUS_C, NUM_C], First, [0, 2])]},
        cache_dir=cache_dir,
    )
    monkeypatch.setattr(
        parser_module, "compute_lalr1_lookaheads", fail_if_table_is_built
    )

    cached = Parser(
        {"value": [([NUM_C, PLUS_C, NUM_C], Second, [2, 0])]},
        cache_dir=cache_dir,
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
    cache_dir = tmp_path / "entry-order"
    first = Parser(grammar, cache_dir=cache_dir)
    monkeypatch.setattr(
        parser_module, "compute_lalr1_lookaheads", fail_if_table_is_built
    )

    cached = Parser(grammar, cache_dir=cache_dir)

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
    cache_dir = tmp_path / "associativity"
    first = Parser(expression_grammar(), cache_dir=cache_dir)
    assert_expression_result(
        first.parse("expr", expression_tokens()), left_associative=True
    )

    monkeypatch.setattr(PLUS_C, "associative", "right")
    second = Parser(expression_grammar(), cache_dir=cache_dir)

    assert second.cache_hit is False
    assert len(list(cache_dir.glob("*.json"))) == 2
    assert_expression_result(
        second.parse("expr", expression_tokens()), left_associative=False
    )


def test_grammar_structure_change_invalidates_cache(tmp_path: Path) -> None:
    cache_dir = tmp_path / "grammar"
    Parser({"value": [([NUM_C], NumC, [0])]}, cache_dir=cache_dir)

    changed = Parser(
        {"value": [([PLUS_C, NUM_C], NumC, [1])]},
        cache_dir=cache_dir,
    )
    result = changed.parse(
        "value",
        [
            PLUS_C("+", lineno=1, offset=0),
            NUM_C("9", lineno=1, offset=1),
        ],
    )

    assert changed.cache_hit is False
    assert len(list(cache_dir.glob("*.json"))) == 2
    assert isinstance(result, NumC)
    assert result.value == 9


def test_prec_token_change_invalidates_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache_dir = tmp_path / "prec"
    grammar = {"value": [([NUM_C], NumC, [0], PREC_C)]}
    Parser(grammar, cache_dir=cache_dir)

    monkeypatch.setattr(PREC_C, "precedence", 2)
    changed = Parser(grammar, cache_dir=cache_dir)

    assert changed.cache_hit is False
    assert len(list(cache_dir.glob("*.json"))) == 2


@pytest.mark.parametrize("contents", ["", "{", "[]", '{"version": 1}'])
def test_corrupt_cache_is_rebuilt(
    contents: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache_dir = tmp_path / "corrupt"
    Parser(expression_grammar(), cache_dir=cache_dir)
    cache_file = only_cache_file(cache_dir)
    cache_file.write_text(contents, encoding="utf-8")

    rebuilt = Parser(expression_grammar(), cache_dir=cache_dir)

    assert rebuilt.cache_hit is False
    assert_expression_result(
        rebuilt.parse("expr", expression_tokens()), left_associative=True
    )

    monkeypatch.setattr(
        parser_module, "compute_lalr1_lookaheads", fail_if_table_is_built
    )
    cached = Parser(expression_grammar(), cache_dir=cache_dir)
    assert cached.cache_hit is True


def test_deeply_nested_cache_is_rebuilt(tmp_path: Path) -> None:
    cache_dir = tmp_path / "deeply-nested"
    Parser(expression_grammar(), cache_dir=cache_dir)
    cache_file = only_cache_file(cache_dir)
    cache_file.write_text("[" * 10_000 + "]" * 10_000, encoding="utf-8")

    rebuilt = Parser(expression_grammar(), cache_dir=cache_dir)

    assert rebuilt.cache_hit is False
    assert_expression_result(
        rebuilt.parse("expr", expression_tokens()), left_associative=True
    )


def test_cache_io_failure_does_not_break_parser(tmp_path: Path) -> None:
    cache_dir = tmp_path / "cache-is-a-file"
    cache_dir.write_text("not a directory", encoding="utf-8")

    parser = Parser(expression_grammar(), cache_dir=cache_dir)

    assert parser.cache_hit is False
    assert_expression_result(
        parser.parse("expr", expression_tokens()), left_associative=True
    )
    assert cache_dir.is_file()


def test_concurrent_cache_initialization_is_atomic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache_dir = tmp_path / "concurrent"
    barrier = Barrier(4)

    def construct_and_parse(task_index: int) -> object:
        barrier.wait()
        parser = Parser(expression_grammar(), cache_dir=cache_dir)
        return parser.parse("expr", expression_tokens())

    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(construct_and_parse, range(8)))

    for result in results:
        assert_expression_result(result, left_associative=True)

    monkeypatch.setattr(
        parser_module, "compute_lalr1_lookaheads", fail_if_table_is_built
    )
    cached = Parser(expression_grammar(), cache_dir=cache_dir)
    assert cached.cache_hit is True
