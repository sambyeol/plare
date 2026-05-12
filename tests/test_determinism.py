"""Tests that Parser produces identical state ids and table contents on repeated builds.

Determinism means: for the same grammar input, two independently constructed
Parser objects must assign the same entry_state ids and the same action/goto
entries in every table cell.  Without explicit ordering in the BFS expansion,
Python's hash randomization can produce different state id assignments across
runs.
"""

from __future__ import annotations

import time

import pytest

from plare.parser import Parser
from plare.token import Token

type Grammar = dict[
    str,
    list[
        tuple[list[type[Token] | str], type[object] | None, list[int]]
        | tuple[list[type[Token] | str], type[object] | None, list[int], type[Token]]
    ],
]

# ---------------------------------------------------------------------------
# Shared token and AST types for a multi-state expression grammar
# ---------------------------------------------------------------------------


class PLUS_D(Token):
    precedence = 1
    associative = "left"


class STAR_D(Token):
    precedence = 2
    associative = "left"


class NUM_D(Token):
    pass


class LPAREN_D(Token):
    pass


class RPAREN_D(Token):
    pass


class Num:
    def __init__(self, tok: NUM_D) -> None:
        self.tok = tok


class Add:
    def __init__(self, left: object, right: object) -> None:
        self.left = left
        self.right = right


class Mul:
    def __init__(self, left: object, right: object) -> None:
        self.left = left
        self.right = right


def make_expr_grammar() -> Grammar:
    """Return a classic expression grammar with enough states to be meaningful.

    expr → expr PLUS term | term
    term → term STAR factor | factor
    factor → NUM | LPAREN expr RPAREN

    This produces around 20 LR(0) states, spanning shift, reduce, goto, and
    accept entries.  Multiple entry points (expr and term) ensure that the
    entry_state mapping is also exercised.
    """
    return {
        "expr": [
            (["expr", PLUS_D, "term"], Add, [0, 2]),
            (["term"], None, [0]),
        ],
        "term": [
            (["term", STAR_D, "factor"], Mul, [0, 2]),
            (["factor"], None, [0]),
        ],
        "factor": [
            ([NUM_D], Num, [0]),
            ([LPAREN_D, "expr", RPAREN_D], None, [1]),
        ],
    }


# ---------------------------------------------------------------------------
# Determinism tests
# ---------------------------------------------------------------------------


def test_parser_entry_state_is_deterministic() -> None:
    """Two Parser instances built from identical grammars have the same entry_state."""
    p1 = Parser(make_expr_grammar())
    p2 = Parser(make_expr_grammar())
    assert p1.entry_state == p2.entry_state


def test_parser_table_actions_are_deterministic() -> None:
    """Two Parser instances built from identical grammars have identical action tables.

    Compares every cell by its string representation so the test does not rely
    on Action subclass identity.
    """
    p1 = Parser(make_expr_grammar())
    p2 = Parser(make_expr_grammar())

    assert len(p1.table.table) == len(p2.table.table), "table row count differs"
    for state_id, (row1, row2) in enumerate(zip(p1.table.table, p2.table.table)):
        assert set(row1.keys()) == set(
            row2.keys()
        ), f"state {state_id}: key sets differ"
        for sym in row1:
            assert str(row1[sym]) == str(
                row2[sym]
            ), f"state {state_id}, symbol {sym}: {row1[sym]!r} != {row2[sym]!r}"


# ---------------------------------------------------------------------------
# Build-time measurement for 50-rule grammar (provides HANDOFF timing data)
# ---------------------------------------------------------------------------


def make_chain_grammar(
    depth: int,
) -> Grammar:
    """Return a right-recursive chain grammar with ``depth`` levels.

    Each level i has a unique token class ChainTok_i so the grammar produces
    O(depth) LR(0) states.  Used to measure parser build time at scale.
    """
    token_classes: list[type[Token]] = []
    for i in range(depth + 1):
        cls = type(f"ChainTok_{i}", (Token,), {})
        token_classes.append(cls)

    class ChainNode:
        def __init__(self, *args: object) -> None:
            pass

    grammar: Grammar = {}
    for i in range(depth):
        tok = token_classes[i]
        next_nt = f"level_{i + 1}"
        grammar[f"level_{i}"] = [
            ([tok, next_nt], ChainNode, [0, 1]),
            ([tok], ChainNode, [0]),
        ]
    grammar[f"level_{depth}"] = [
        ([token_classes[depth]], ChainNode, [0]),
    ]
    return grammar


@pytest.mark.slow
def test_parser_build_time_large_grammar() -> None:
    """Build a 50-level chain grammar and record the wall time.

    This test does not assert a specific time bound (build times vary by
    hardware).  Its purpose is to produce a timing measurement for the T3
    HANDOFF.md Notes section.  Marked slow so it can be skipped in fast CI
    runs with ``pytest -m 'not slow'``.
    """
    grammar = make_chain_grammar(50)
    start = time.perf_counter()
    p = Parser(grammar)
    elapsed = time.perf_counter() - start
    assert p.entry_state, "parser must have at least one entry state"
    print(f"\nLarge grammar (50 levels) build time: {elapsed * 1000:.1f} ms")
