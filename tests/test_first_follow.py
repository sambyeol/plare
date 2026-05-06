"""Unit tests for compute_first_sets and compute_follow_sets."""

from __future__ import annotations
from typing import Any

import pytest

from plare.parser import (
    EOS,
    EPSILON,
    Maker,
    Rule,
    StartVariable,
    Symbol,
    compute_first_sets,
    compute_follow_sets,
)
from plare.token import Token


class Null:
    """A dummy value for testing — the makers are stubs never called by the pure functions."""

    def __init__(self, *xs: Any) -> None:
        pass


class ATok(Token):
    def __init__(self, value: str, *, lineno: int, offset: int) -> None:
        self.value = value
        self.lineno = lineno
        self.offset = offset


class BTok(Token):
    def __init__(self, value: str, *, lineno: int, offset: int) -> None:
        self.value = value
        self.lineno = lineno
        self.offset = offset


class CTok(Token):
    def __init__(self, value: str, *, lineno: int, offset: int) -> None:
        self.value = value
        self.lineno = lineno
        self.offset = offset


class DTok(Token):
    def __init__(self, value: str, *, lineno: int, offset: int) -> None:
        self.value = value
        self.lineno = lineno
        self.offset = offset


class XTok(Token):
    def __init__(self, value: str, *, lineno: int, offset: int) -> None:
        self.value = value
        self.lineno = lineno
        self.offset = offset


class IdTok(Token):
    def __init__(self, value: str, *, lineno: int, offset: int) -> None:
        self.value = value
        self.lineno = lineno
        self.offset = offset


class PlusTok(Token):
    def __init__(self, value: str, *, lineno: int, offset: int) -> None:
        self.value = value
        self.lineno = lineno
        self.offset = offset


class StarTok(Token):
    def __init__(self, value: str, *, lineno: int, offset: int) -> None:
        self.value = value
        self.lineno = lineno
        self.offset = offset


class LParen(Token):
    def __init__(self, value: str, *, lineno: int, offset: int) -> None:
        self.value = value
        self.lineno = lineno
        self.offset = offset


class RParen(Token):
    def __init__(self, value: str, *, lineno: int, offset: int) -> None:
        self.value = value
        self.lineno = lineno
        self.offset = offset


def make_rule(left: str, rights: list[list[Symbol]]) -> Rule[Null]:
    """Build a Rule for testing — the makers are stubs never called by the pure functions."""
    r: Rule[Null] = Rule(left, [(list(rhs), Null, []) for rhs in rights])
    return r


@pytest.mark.timeout(5)
def test_mutual_recursion_first_terminates() -> None:
    """Mutual left-recursion A↔B must not cause an infinite loop."""
    # A → B a | a
    # B → A b | b
    # FIRST(A) = {a, b}  (a from A→a; b from B→b which feeds into A→Ba)
    # FIRST(B) = {a, b}  (b from B→b; a from A→a which feeds into B→Ab)
    rules: dict[str, Rule[Null]] = {
        "A": make_rule("A", [["B", ATok], [ATok]]),
        "B": make_rule("B", [["A", BTok], [BTok]]),
    }
    first = compute_first_sets(rules)

    assert ATok in first["A"]
    assert BTok in first["A"]
    assert ATok in first["B"]
    assert BTok in first["B"]
    assert EPSILON not in first["A"]
    assert EPSILON not in first["B"]


def test_epsilon_production_propagates_to_first() -> None:
    """ε-production on B causes C's FIRST to appear in A's FIRST."""
    # A → B C | a
    # B → b | ε
    # C → c
    # FIRST(A) = {b, c, a}  (b and ε from B; since B nullable, c from C)
    rules: dict[str, Rule[Null]] = {
        "A": make_rule("A", [["B", "C"], [ATok]]),
        "B": make_rule("B", [[BTok], []]),
        "C": make_rule("C", [[CTok]]),
    }
    first = compute_first_sets(rules)

    assert BTok in first["A"]
    assert CTok in first["A"]
    assert ATok in first["A"]
    assert EPSILON not in first["A"]
    assert EPSILON in first["B"]
    assert EPSILON not in first["C"]


def test_chain_ofnullable_nonterminals() -> None:
    """When B, C are nullable, D's terminal reaches FIRST(A)."""
    # A → B C D | x
    # B → ε
    # C → ε
    # D → d
    # FIRST(A) = {d, x}
    rules: dict[str, Rule[Null]] = {
        "A": make_rule("A", [["B", "C", "D"], [XTok]]),
        "B": make_rule("B", [[]]),
        "C": make_rule("C", [[]]),
        "D": make_rule("D", [[DTok]]),
    }
    first = compute_first_sets(rules)

    assert DTok in first["A"]
    assert XTok in first["A"]
    assert EPSILON not in first["A"]


def test_dragon_book_expression_grammar_first() -> None:
    """Classic Dragon Book expression grammar — textbook FIRST sets.

    Grammar (left-recursive):
        E  → E + T | T
        T  → T * F | F
        F  → ( E ) | id
    Expected:
        FIRST(E) = FIRST(T) = FIRST(F) = {LParen, IdTok}
    """
    rules: dict[str, Rule[Null]] = {
        "E": make_rule("E", [["E", PlusTok, "T"], ["T"]]),
        "T": make_rule("T", [["T", StarTok, "F"], ["F"]]),
        "F": make_rule("F", [[LParen, "E", RParen], [IdTok]]),
    }
    first = compute_first_sets(rules)

    assert first["E"] == {LParen, IdTok}
    assert first["T"] == {LParen, IdTok}
    assert first["F"] == {LParen, IdTok}


def test_dragon_book_expression_grammar_follow() -> None:
    """Classic Dragon Book expression grammar — textbook FOLLOW sets.

    Grammar (same as above, augmented with S → E):
    Expected:
        FOLLOW(E) = {PlusTok, RParen, EOS}
        FOLLOW(T) = {PlusTok, StarTok, RParen, EOS}
        FOLLOW(F) = {PlusTok, StarTok, RParen, EOS}
    """
    start = StartVariable("E")
    rules: dict[str, Rule[Null]] = {
        start: make_rule(start, [["E"]]),
        "E": make_rule("E", [["E", PlusTok, "T"], ["T"]]),
        "T": make_rule("T", [["T", StarTok, "F"], ["F"]]),
        "F": make_rule("F", [[LParen, "E", RParen], [IdTok]]),
    }
    first = compute_first_sets(rules)
    follow = compute_follow_sets(rules, first)

    assert follow["E"] == {PlusTok, RParen, EOS}
    assert follow["T"] == {PlusTok, StarTok, RParen, EOS}
    assert follow["F"] == {PlusTok, StarTok, RParen, EOS}
