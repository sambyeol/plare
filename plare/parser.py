"""LALR(1) parser with operator-precedence conflict resolution.

This module implements an **LALR(1)** (Look-Ahead LR, 1 token of lookahead)
parser.  Reduce actions fire on per-item lookahead sets computed via the
spontaneous-generation and propagation algorithm (Aho-Sethi-Ullman §9.6).

Construction pipeline (``Parser.__init__``):
    1. Augment the grammar with ``StartVariable(X) → X`` entry rules.
    2. Compute FIRST sets for every non-terminal.
    3. Build the LR(0) canonical collection (states + transitions) via
       ``closure`` / ``goto`` BFS.
    4. Compute LALR(1) per-item lookahead sets (ASU §9.6).
    5. Populate the action/goto table; resolve shift/reduce and reduce/reduce
       conflicts using token precedence and associativity.

When ``cache_path`` points to a compatible table, construction stops after
grammar normalization and rebinds the cached actions to the current classes.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections import deque
from collections.abc import Mapping, Sequence
from itertools import chain
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Iterable, Protocol, TypeGuard, cast

from plare.exception import ParserError, ParsingError
from plare.token import Token
from plare.utils import logger

PARSE_TABLE_CACHE_VERSION = 1
"""Version of the on-disk parse-table schema and parser-building algorithm."""


class EOS(Token):
    """Sentinel token appended to every token stream to signal end-of-input."""


class EPSILON(Token):
    """Sentinel token representing the empty string (ε) in FIRST sets."""


class DUMMY_LOOKAHEAD(Token):
    """Sentinel lookahead used during LALR(1) spontaneous-generation detection."""


type Symbol = type[Token] | str


class Maker[T](Protocol):
    """Protocol for semantic action callables used during reduction."""

    def __call__(self, *xs: T | Token) -> T | Token: ...


class TMaker[T](Maker[T]):
    """Action maker that constructs a typed AST node from selected children.

    Args:
        type: The AST node class to instantiate.
        args: Indices into the RHS children to forward as positional arguments.
    """

    def __init__(self, type: type[T], args: list[int]) -> None:
        self.type = type
        self.args = args

    def __call__(self, *xs: T | Token) -> T:
        return self.type(*[xs[i] for i in self.args])

    def __str__(self) -> str:
        args = ", ".join(map(lambda a: f"${a}", self.args))
        return f"{self.type.__name__}({args})"


class IDMaker[T](Maker[T]):
    """Action maker that passes a single child through unchanged.

    Args:
        arg: Index of the child to return.
    """

    def __init__(self, arg: int) -> None:
        self.arg = arg

    def __call__(self, *xs: T | Token) -> T | Token:
        return xs[self.arg]

    def __str__(self) -> str:
        return f"${self.arg}"


class StartVariable(str):
    """Augmented-grammar start symbol wrapper.

    Wraps a non-terminal string so that the augmented production
    ``StartVariable(X) → X`` is distinct from any user-defined rule
    named ``X``.  Equality is strict: a ``StartVariable`` only compares
    equal to another ``StartVariable`` with the same underlying string,
    never to a plain ``str``.

    Attributes:
        orig: The original non-terminal name before wrapping.
    """

    def __init__(self, variable: str) -> None:
        self.orig = variable

    def __hash__(self) -> int:
        return super().__hash__()

    def __eq__(self, other: object) -> bool:
        return isinstance(other, StartVariable) and super().__eq__(other)

    def __ne__(self, other: object) -> bool:
        return not isinstance(other, StartVariable) or super().__ne__(other)


class Item[T]:
    """An LR(0) item ``[A → α • β]``.

    An item records a grammar rule together with the *dot position* (``loc``)
    indicating how much of the RHS has been recognised so far.  Items are the
    building blocks of LR automaton states.

    ``precedence`` is used for shift/reduce conflict resolution.  By default it
    is the precedence of the *rightmost* terminal in ``right`` with a non-zero
    precedence value (yacc/bison convention).  When ``prec_override`` is given
    (analogous to yacc's ``%prec``), it replaces that derivation entirely.

    ``definition_index`` is the zero-based ordinal assigned to this production
    during grammar construction (counting across all non-terminals in definition
    order).  It is used to break ties when two reduce actions have equal
    precedence: the production with the lower index wins.

    Attributes:
        left: The non-terminal on the LHS of the rule.
        right: The full RHS symbol sequence (terminals are ``type[Token]``
            subclasses; non-terminals are ``str``).
        loc: Dot position (0 = dot before first symbol).
        maker: The semantic action to invoke on reduction.
        precedence: Effective precedence of this production for conflict
            resolution; ``0`` means no precedence.
        definition_index: Grammar-wide ordinal of this production (0 = first
            defined).
    """

    left: str | StartVariable
    right: list[Symbol]
    loc: int
    maker: Maker[T]
    precedence: int
    definition_index: int

    def __init__(
        self,
        left: str | StartVariable,
        right: list[Symbol],
        maker: Maker[T],
        definition_index: int,
        loc: int = 0,
        prec_override: int | None = None,
    ) -> None:
        self.left = left
        self.right = right
        self.loc = loc
        self.maker = maker
        self.definition_index = definition_index
        if prec_override is not None:
            self.precedence = prec_override
        else:
            self.precedence = 0
            terminals = [t for t in right if isinstance(t, type)]
            for token in reversed(terminals):
                if token.precedence != 0:
                    self.precedence = token.precedence
                    break

    @property
    def next(self) -> Symbol | None:
        """The symbol immediately after the dot, or ``None`` if the item is complete."""
        return self.right[self.loc] if self.loc < len(self.right) else None

    def move(self, symbol: Symbol) -> Item[T] | None:
        """Return a new item with the dot advanced past ``symbol``, or ``None`` if it doesn't match."""
        next = self.next
        if type(symbol) == type(next) and symbol == next:
            return Item(
                self.left,
                self.right,
                self.maker,
                self.definition_index,
                self.loc + 1,
                self.precedence,
            )
        return None

    def __str__(self) -> str:
        before_dot = " ".join(
            map(
                lambda v: v if isinstance(v, str) else v.__name__,
                self.right[: self.loc],
            )
        )
        after_dot = " ".join(
            map(
                lambda v: v if isinstance(v, str) else v.__name__,
                self.right[self.loc :],
            )
        )
        arrow = "=>" if isinstance(self.left, StartVariable) else "->"
        return f"{self.left} {arrow} {before_dot} . {after_dot}"

    def __hash__(self) -> int:
        return hash((self.left, tuple(self.right), self.loc))

    def __eq__(self, value: object) -> bool:
        return (
            isinstance(value, Item)
            and self.left == value.left
            and self.right == value.right
            and self.loc == value.loc
        )


class State[T]:
    """An LR(0) automaton state: a set of LR(0) items with a unique integer id.

    Attributes:
        id: Index used to look up rows in the ``Table``.
        items: The closed set of LR(0) items that define this state.
        lookaheads: LALR(1) lookahead sets keyed by item.  For each complete
            item ``[A → α •]`` in this state, ``lookaheads[item]`` is the set
            of tokens on which the reduction fires.  Populated during Phase 5
            of ``Parser.__init__``.
    """

    id: int
    items: set[Item[T]]
    lookaheads: dict[Item[T], set[type[Token]]]

    def __init__(self, id: int, items: set[Item[T]]) -> None:
        self.id = id
        self.items = items
        self.lookaheads = {}

    def __hash__(self) -> int:
        return hash(frozenset(self.items))

    def is_instance(self, obj: object) -> TypeGuard[State[T]]:
        return isinstance(obj, State)

    def __eq__(self, other: object) -> bool:
        return self.is_instance(other) and self.items == other.items

    def __str__(self) -> str:
        return "\n".join(map(str, self.items))


class Shift:
    """LR table action: shift the lookahead token and push state ``next``."""

    __match_args__ = ("next",)

    next: int

    def __init__(self, next: int) -> None:
        self.next = next

    def __str__(self) -> str:
        return f"Shift({self.next})"


class Reduce[T]:
    """LR table action: pop ``n`` symbols, apply ``maker``, push non-terminal ``left``."""

    __match_args__ = ("left", "n", "maker")

    left: str
    n: int
    maker: Maker[T]
    precedence: int
    definition_index: int

    def __init__(
        self,
        left: str,
        n: int,
        maker: Maker[T],
        precedence: int,
        definition_index: int,
    ) -> None:
        self.left = left
        self.n = n
        self.maker = maker
        self.precedence = precedence
        self.definition_index = definition_index

    def __str__(self) -> str:
        return f"Reduce({self.n}, {self.maker})"


class Accept:
    """LR table action: the parse of non-terminal ``symbol`` is complete."""

    __match_args__ = ("symbol",)

    symbol: str

    def __init__(self, symbol: str) -> None:
        self.symbol = symbol

    def __str__(self) -> str:
        return f"Accept({self.symbol})"


class Goto:
    """LR table action: after a reduction, push state ``next`` for a non-terminal."""

    __match_args__ = ("next",)

    next: int

    def __init__(self, next: int) -> None:
        self.next = next

    def __str__(self) -> str:
        return f"Goto({self.next})"


type Action[T] = Shift | Reduce[T] | Accept | Goto


class Conflict(Exception):
    """Internal signal raised inside ``Table.__setitem__`` on an LR conflict."""


class ShiftReduceConflict(Conflict):
    """Signals a shift/reduce conflict; caught and resolved by precedence rules."""


class ReduceReduceConflict(Conflict):
    """Signals a reduce/reduce conflict; carries the existing reduce's metadata.

    Args:
        left: LHS of the already-registered reduce action.
        precedence: Precedence of the already-registered reduce action.
        definition_index: Grammar-wide ordinal of the already-registered production.
    """

    def __init__(self, left: str, precedence: int, definition_index: int) -> None:
        self.left = left
        self.precedence = precedence
        self.definition_index = definition_index


class Table[T]:
    """LR action/goto table indexed by ``(state_id, symbol)``.

    ``symbol`` is a ``type[Token]`` subclass for action entries (shift, reduce,
    accept) and a plain ``str`` for goto entries.  Inserting a duplicate entry
    raises ``ShiftReduceConflict`` or ``ReduceReduceConflict`` so the caller
    can attempt resolution before committing.

    Attributes:
        table: Row-per-state list of ``{symbol: action}`` dicts.
    """

    table: list[dict[Symbol, Action[T] | None]]

    def __init__(self, states: int) -> None:
        self.table = [{} for _ in range(states)]

    def __setitem__(self, key: tuple[int, Symbol], action: Action[T]) -> None:
        state, symbol = key
        logger.debug("[%d, %s] -> %s", state, symbol, action)

        if isinstance(symbol, type):
            if isinstance(action, Goto):
                raise ParserError(
                    f"Unknown parser error in state {state}: {action.__class__.__name__} action for {symbol} is given"
                )

            try:
                exist = self.table[state][symbol]
                match exist, action:
                    case Shift(), Reduce():
                        raise ShiftReduceConflict()
                    case Reduce(), Reduce():
                        raise ReduceReduceConflict(
                            exist.left, exist.precedence, exist.definition_index
                        )
                    case _:
                        raise ParserError(
                            f"Unknown parser error in state {state}: action for {symbol} is already determined to {exist}, but new action {action} is given"
                        )
            except KeyError:
                pass

            self.table[state][symbol] = action

        else:
            if not isinstance(action, Goto):
                raise ParserError(
                    f"Unknown parser error in state {state}: {action.__class__.__name__} action for {symbol} is given"
                )

            if symbol in self.table[state]:
                raise ParserError(
                    f"Unknown parser error in state {state}: Goto action for {symbol} is already determined to {self.table[state][symbol]}, but new action {action} is given"
                )

            self.table[state][symbol] = action

    def __getitem__(self, key: tuple[int, Symbol]) -> Action[T] | None:
        state, symbol = key
        return self.table[state][symbol]

    def expected_tokens(self, state: int) -> list[type[Token]]:
        """Return terminal classes that have an action in *state*."""
        return [sym for sym in self.table[state] if isinstance(sym, type)]

    def resolve_conflict(self, state: int, symbol: Symbol, winner: Action[T]) -> None:
        """Overwrite a table entry with the winning action from a resolved conflict."""
        self.table[state][symbol] = winner


class Rule[T]:
    """All RHS alternatives for a single non-terminal.

    ``Rule`` is the unit of grammar specification.  One ``Rule`` object
    aggregates every production ``A → rhs₁ | rhs₂ | …`` for a given
    non-terminal ``A``.

    Attributes:
        left: The non-terminal name (LHS).
        rights: List of ``(rhs_symbols, maker, prec_override)`` triples.
        definition_indices: Grammar-wide ordinal for each production alternative.
    """

    left: str
    rights: list[tuple[list[Symbol], Maker[T], int | None]]
    definition_indices: list[int]

    def __init__(
        self,
        left: str,
        rights: list[tuple[list[Symbol], type[T] | None, list[int], int | None]],
        start_index: int,
    ) -> None:
        self.left = left
        self.rights = [
            (
                right,
                TMaker(action, args) if action is not None else IDMaker(*args),
                prec_override,
            )
            for right, action, args, prec_override in rights
        ]
        self.definition_indices = list(range(start_index, start_index + len(rights)))

    def __hash__(self) -> int:
        return hash(self.left)

    def __eq__(self, value: object) -> bool:
        return isinstance(value, Rule) and self.left == value.left

    def __repr__(self) -> str:
        return f"Rule({self.left})"

    @property
    def items(self) -> set[Item[T]]:
        """Initial items ``[A → • rhs]`` for all alternatives of this rule."""
        return set(
            Item(self.left, right, maker, idx, prec_override=prec_override)
            for (right, maker, prec_override), idx in zip(
                self.rights, self.definition_indices
            )
        )


def compute_first_sets[T](rules: dict[str, Rule[T]]) -> dict[str, set[type[Token]]]:
    """Compute FIRST sets for all non-terminals via worklist fixed-point iteration.

    Iterates over all productions until no FIRST set changes.  Handles
    ε-productions and nullable non-terminals by continuing past them in the
    symbol sequence.

    Args:
        rules: Complete grammar mapping non-terminal name → ``Rule``.

    Returns:
        Mapping from non-terminal name to its FIRST set.
    """
    first: dict[str, set[type[Token]]] = {name: set() for name in rules}
    changed = True
    while changed:
        changed = False
        for name, rule in rules.items():
            for right, _, _ in rule.rights:
                if not right:
                    if EPSILON not in first[name]:
                        first[name].add(EPSILON)
                        changed = True
                    continue
                for sym in right:
                    if isinstance(sym, type):
                        if sym is EPSILON:
                            continue
                        if sym not in first[name]:
                            first[name].add(sym)
                            changed = True
                        break
                    else:
                        added = first[sym] - {EPSILON} - first[name]
                        if added:
                            first[name].update(added)
                            changed = True
                        if EPSILON not in first[sym]:
                            break
                else:
                    if EPSILON not in first[name]:
                        first[name].add(EPSILON)
                        changed = True
    return first


def symbol_sort_key(s: Symbol) -> tuple[int, str]:
    """Return a sort key that gives a stable total order over grammar symbols.

    Terminals (token classes) sort before non-terminals (strings); within each
    group items are ordered alphabetically by name.  This ensures that the BFS
    expansion of each state visits successor symbols in the same order on every
    Python run, regardless of hash randomization.
    """
    if isinstance(s, type):
        return (0, s.__name__)
    return (1, s)


def closure[T](items: set[Item[T]], all_items: dict[str, set[Item[T]]]) -> set[Item[T]]:
    """Compute the LR(0) closure of an item set.

    This is the standard LR(0) closure operation (Aho-Sethi-Ullman §4.6):
    for every item ``[A → α • B β]`` in the set, add the initial items
    ``[B → • γ]`` for every production of B.  Repeat until no new items
    are added.

    Invariant: ``all_items`` must contain the complete initial item set for
    every non-terminal reachable from the grammar's start symbols.  Missing
    non-terminals will silently produce an incomplete closure.

    Args:
        items: The kernel item set to close.
        all_items: Mapping from non-terminal name → its initial items ``{[A → • rhs]}``.

    Returns:
        The closed item set (a new ``set`` that is a superset of ``items``).
    """
    items = set(items)
    worklist: deque[Item[T]] = deque(items)
    while worklist:
        item = worklist.popleft()
        next = item.next
        if next is None or isinstance(next, type):
            continue
        to_update = all_items[next] - items
        if to_update:
            worklist.extend(to_update)
            items.update(to_update)
    return items


def goto[T](
    items: set[Item[T]],
    symbol: Symbol,
    all_items: dict[str, set[Item[T]]],
) -> set[Item[T]]:
    """Compute the LR(0) goto set: the successor state on ``symbol``.

    Advances the dot past ``symbol`` in every item that has ``symbol``
    immediately after its dot, then takes the closure of the resulting kernel.
    This defines the transition function of the LR(0) automaton and is used
    during the canonical-collection BFS in ``Parser.__init__``.

    Args:
        items: The current state's closed item set.
        symbol: The grammar symbol (terminal class or non-terminal string) to
            transition on.
        all_items: Forwarded to ``closure``.

    Returns:
        The closed item set for the successor state, or an empty set if no
        item in ``items`` has ``symbol`` after its dot.
    """
    return closure(
        set(next for item in items if (next := item.move(symbol)) is not None),
        all_items,
    )


def intern_state[T](
    itemset: set[Item[T]],
    state_index: dict[frozenset[Item[T]], int],
    state_list: list[State[T]],
) -> tuple[State[T], bool]:
    """Register *itemset* as an LR(0) state if not yet seen; return (state, is_new).

    Looks up the closed item set in *state_index* for O(1) deduplication.
    If the itemset is new, assigns the next available id, appends a new
    ``State`` to *state_list*, and records the mapping in *state_index*.

    Args:
        itemset: The closed item set that defines a candidate state.
        state_index: Mapping from ``frozenset[Item]`` to already-assigned state id.
        state_list: Ordered list of states; index equals state id.

    Returns:
        A tuple ``(state, is_new)`` where ``is_new`` is ``True`` when the
        itemset was not previously registered.
    """
    key = frozenset(itemset)
    if key in state_index:
        return state_list[state_index[key]], False
    sid = len(state_list)
    state = State(sid, itemset)
    state_index[key] = sid
    state_list.append(state)
    return state, True


def first_of_sequence[T](
    syms: list[Symbol],
    lookahead: type[Token],
    first_sets: dict[str, set[type[Token]]],
) -> set[type[Token]]:
    """Return the set of tokens that can begin the sequence ``syms lookahead``.

    Computes FIRST(syms) and, if every symbol in ``syms`` is nullable (or
    ``syms`` is empty), includes ``lookahead``.  Used by ``closure_lr1`` to
    derive the lookahead set for newly added LR(1) items.

    Args:
        syms: Suffix of a production RHS (β in ``[A → α • B β, a]``).
        lookahead: The inherited lookahead ``a`` to include when ``syms``
            derives ε.
        first_sets: Precomputed FIRST sets from ``compute_first_sets``.

    Returns:
        The set of token classes that can begin ``syms`` followed by
        ``lookahead``.
    """
    result: set[type[Token]] = set()
    for sym in syms:
        if isinstance(sym, type):
            result.add(sym)
            return result
        sym_first = first_sets[sym]
        result.update(sym_first - {EPSILON})
        if EPSILON not in sym_first:
            return result
    result.add(lookahead)
    return result


def closure_lr1[T](
    lr1_kernel: set[tuple[Item[T], type[Token]]],
    all_items: dict[str, set[Item[T]]],
    first_sets: dict[str, set[type[Token]]],
) -> set[tuple[Item[T], type[Token]]]:
    """Compute the LR(1) closure of a set of LR(1) items.

    Each LR(1) item is a pair ``(item, lookahead)``.  For every item
    ``[A → α • B β, a]`` in the set, adds ``[B → • γ, b]`` for every
    production ``B → γ`` and every ``b ∈ first_of_sequence(β, a, first_sets)``.
    Repeats until no new items are added (ASU §9.5).

    Args:
        lr1_kernel: Seed LR(1) items as ``(Item, lookahead-token-class)`` pairs.
        all_items: Mapping from non-terminal name to its initial LR(0) items.
        first_sets: Precomputed FIRST sets from ``compute_first_sets``.

    Returns:
        The closed set of LR(1) items (superset of ``lr1_kernel``).
    """
    result: set[tuple[Item[T], type[Token]]] = set(lr1_kernel)
    worklist: deque[tuple[Item[T], type[Token]]] = deque(lr1_kernel)
    while worklist:
        item, lookahead = worklist.popleft()
        next_sym = item.next
        if next_sym is None or isinstance(next_sym, type):
            continue
        beta = item.right[item.loc + 1 :]
        for b in first_of_sequence(beta, lookahead, first_sets):
            for init_item in all_items[next_sym]:
                pair: tuple[Item[T], type[Token]] = (init_item, b)
                if pair not in result:
                    result.add(pair)
                    worklist.append(pair)
    return result


def compute_lalr1_lookaheads[T](
    state_list: list[State[T]],
    entry_rules: list[tuple[StartVariable, Rule[T]]],
    entry_state_ids: list[int],
    goto_map: dict[tuple[int, Symbol], int],
    all_items: dict[str, set[Item[T]]],
    first_sets: dict[str, set[type[Token]]],
) -> dict[tuple[int, Item[T]], set[type[Token]]]:
    """Compute LALR(1) lookahead sets for all kernel items in the LR(0) automaton.

    Implements the spontaneous-generation and propagation algorithm from
    Aho-Sethi-Ullman §9.6.  Kernel items are items with ``loc > 0`` plus the
    augmented start items (``loc == 0`` with a ``StartVariable`` LHS).

    The algorithm has four phases:

    1. Initialise empty lookahead sets and propagation lists for every kernel item.
    2. Seed ``EOS`` into the lookahead sets of the entry-state kernel items.
    3. For each kernel item k, run ``closure_lr1({(k, DUMMY_LOOKAHEAD)}, ...)``.
       Items in the result whose lookahead is a real token contribute that token
       spontaneously to the target kernel item; items whose lookahead is still
       ``DUMMY_LOOKAHEAD`` record a propagation link from k to the target.
    4. Propagate lookaheads along the links to a fixed point.

    Args:
        state_list: All LR(0) states (index equals state id).
        entry_rules: Augmented start rules paired with their ``StartVariable``.
        entry_state_ids: State id for the initial state of ``entry_rules[i]``.
        goto_map: Mapping ``(state_id, symbol)`` → target state id.
        all_items: Mapping non-terminal name → its initial LR(0) items.
        first_sets: Precomputed FIRST sets from ``compute_first_sets``.

    Returns:
        Mapping ``(state_id, kernel_item)`` → set of LALR(1) lookahead token
        classes.
    """
    lookahead_table: dict[tuple[int, Item[T]], set[type[Token]]] = {}
    propagates: dict[tuple[int, Item[T]], list[tuple[int, Item[T]]]] = {}

    for state in state_list:
        for item in state.items:
            if (
                item.loc > 0
                or isinstance(item.left, StartVariable)
                or item.next is None
            ):
                key: tuple[int, Item[T]] = (state.id, item)
                lookahead_table[key] = set()
                propagates[key] = []

    for i, (_, rule) in enumerate(entry_rules):
        sid = entry_state_ids[i]
        for item in rule.items:
            entry_key: tuple[int, Item[T]] = (sid, item)
            if entry_key in lookahead_table:
                lookahead_table[entry_key].add(EOS)

    for state in state_list:
        for item in state.items:
            if not (item.loc > 0 or isinstance(item.left, StartVariable)):
                continue
            src_key: tuple[int, Item[T]] = (state.id, item)
            j = closure_lr1({(item, DUMMY_LOOKAHEAD)}, all_items, first_sets)
            for lr1_item, b in j:
                sym = lr1_item.next
                if sym is None:
                    closure_key: tuple[int, Item[T]] = (state.id, lr1_item)
                    if closure_key not in lookahead_table:
                        lookahead_table[closure_key] = set()
                    if closure_key not in propagates:
                        propagates[closure_key] = []
                    if b is DUMMY_LOOKAHEAD:
                        propagates[src_key].append(closure_key)
                    else:
                        lookahead_table[closure_key].add(b)
                    continue
                target_id = goto_map.get((state.id, sym))
                if target_id is None:
                    continue
                moved = lr1_item.move(sym)
                if moved is None:
                    continue
                target_key: tuple[int, Item[T]] = (target_id, moved)
                if target_key not in lookahead_table:
                    lookahead_table[target_key] = set()
                if target_key not in propagates:
                    propagates[target_key] = []
                if b is DUMMY_LOOKAHEAD:
                    propagates[src_key].append(target_key)
                else:
                    lookahead_table[target_key].add(b)

    changed = True
    while changed:
        changed = False
        for src_key, dst_keys in propagates.items():
            for dst_key in dst_keys:
                new = lookahead_table[src_key] - lookahead_table[dst_key]
                if new:
                    lookahead_table[dst_key].update(new)
                    changed = True

    return lookahead_table


class InvalidParseTableCache(ValueError):
    """Internal signal for a stale, corrupt, or incompatible cache file."""


class StaleParseTableCache(InvalidParseTableCache):
    """Internal signal for a valid cache built for another grammar or version."""


def _cache_digest(value: object) -> str:
    """Return a deterministic SHA-256 digest for a JSON-compatible value."""
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _cache_list(value: object) -> list[object]:
    if not isinstance(value, list):
        raise InvalidParseTableCache("expected a list")
    return cast(list[object], value)


def _cache_dict(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise InvalidParseTableCache("expected an object with string keys")
    mapping = cast(dict[object, object], value)
    if not all(isinstance(key, str) for key in mapping):
        raise InvalidParseTableCache("expected an object with string keys")
    return cast(dict[str, object], mapping)


def _cache_int(value: object) -> int:
    if type(value) is not int:
        raise InvalidParseTableCache("expected an integer")
    return value


def _cache_str(value: object) -> str:
    if not isinstance(value, str):
        raise InvalidParseTableCache("expected a string")
    return value


def _encode_cache_symbol(
    symbol: Symbol, token_ids: dict[type[Token], int]
) -> list[str | int]:
    if symbol is EOS:
        return ["eos"]
    if isinstance(symbol, type):
        return ["token", token_ids[symbol]]
    return ["nonterminal", symbol]


def _decode_cache_symbol(value: object, tokens: list[type[Token]]) -> Symbol:
    encoded = _cache_list(value)
    if not encoded:
        raise InvalidParseTableCache("empty symbol")
    kind = _cache_str(encoded[0])
    if kind == "eos" and len(encoded) == 1:
        return EOS
    if kind == "token" and len(encoded) == 2:
        token_id = _cache_int(encoded[1])
        if 0 <= token_id < len(tokens):
            return tokens[token_id]
    if kind == "nonterminal" and len(encoded) == 2:
        return _cache_str(encoded[1])
    raise InvalidParseTableCache("invalid symbol")


def _encode_cache_action[T](action: Action[T] | None) -> list[str | int]:
    match action:
        case Shift(next=next_state):
            return ["shift", next_state]
        case Reduce(definition_index=definition_index):
            return ["reduce", definition_index]
        case Accept(symbol=symbol):
            return ["accept", symbol]
        case Goto(next=next_state):
            return ["goto", next_state]
        case _:
            raise ValueError(f"Unsupported parse-table action: {action}")


def _copy_reduce[T](reduction: Reduce[T]) -> Reduce[T]:
    """Return a distinct reduce action bound to the same current-grammar maker."""
    return Reduce(
        reduction.left,
        reduction.n,
        reduction.maker,
        reduction.precedence,
        reduction.definition_index,
    )


def _decode_cache_action[T](
    value: object,
    state_count: int,
    reductions: dict[int, Reduce[T]],
    entry_names: list[str],
) -> Action[T]:
    encoded = _cache_list(value)
    if len(encoded) != 2:
        raise InvalidParseTableCache("invalid action")
    kind = _cache_str(encoded[0])
    target = encoded[1]
    if kind in {"shift", "goto"}:
        next_state = _cache_int(target)
        if not 0 <= next_state < state_count:
            raise InvalidParseTableCache("state target out of range")
        return Shift(next_state) if kind == "shift" else Goto(next_state)
    if kind == "reduce":
        definition_index = _cache_int(target)
        try:
            return _copy_reduce(reductions[definition_index])
        except KeyError:
            raise InvalidParseTableCache("unknown production") from None
    if kind == "accept":
        symbol = _cache_str(target)
        if symbol not in entry_names:
            raise InvalidParseTableCache("unknown accept symbol")
        return Accept(symbol)
    raise InvalidParseTableCache("unknown action")


def _encode_parse_table_cache[T](
    fingerprint: str,
    table: Table[T],
    entry_state: dict[str, int],
    token_ids: dict[type[Token], int],
) -> dict[str, object]:
    rows: list[object] = []
    for row in table.table:
        rows.append(
            [
                [
                    _encode_cache_symbol(symbol, token_ids),
                    _encode_cache_action(action),
                ]
                for symbol, action in row.items()
            ]
        )
    data: dict[str, object] = {
        "entry_state": entry_state,
        "table": rows,
    }
    return {
        "version": PARSE_TABLE_CACHE_VERSION,
        "grammar": fingerprint,
        "checksum": _cache_digest(data),
        "data": data,
    }


def _decode_parse_table_cache[T](
    raw: object,
    fingerprint: str,
    tokens: list[type[Token]],
    reductions: dict[int, Reduce[T]],
    entry_names: list[str],
) -> tuple[Table[T], dict[str, int]]:
    payload = _cache_dict(raw)
    if _cache_int(payload.get("version")) != PARSE_TABLE_CACHE_VERSION:
        raise StaleParseTableCache("cache version mismatch")
    if _cache_str(payload.get("grammar")) != fingerprint:
        raise StaleParseTableCache("grammar mismatch")

    data = _cache_dict(payload.get("data"))
    if _cache_str(payload.get("checksum")) != _cache_digest(data):
        raise InvalidParseTableCache("checksum mismatch")

    encoded_rows = _cache_list(data.get("table"))
    state_count = len(encoded_rows)
    encoded_entry_state = _cache_dict(data.get("entry_state"))
    if set(encoded_entry_state) != set(entry_names):
        raise InvalidParseTableCache("entry symbols mismatch")
    entry_state: dict[str, int] = {}
    for symbol in entry_names:
        state = _cache_int(encoded_entry_state[symbol])
        if not 0 <= state < state_count:
            raise InvalidParseTableCache("entry state out of range")
        entry_state[symbol] = state

    table = Table[T](state_count)
    for state, encoded_row in enumerate(encoded_rows):
        for encoded_cell in _cache_list(encoded_row):
            cell = _cache_list(encoded_cell)
            if len(cell) != 2:
                raise InvalidParseTableCache("invalid table cell")
            symbol = _decode_cache_symbol(cell[0], tokens)
            action = _decode_cache_action(cell[1], state_count, reductions, entry_names)
            if isinstance(symbol, type):
                if isinstance(action, Goto):
                    raise InvalidParseTableCache("goto action for a token")
            else:
                if symbol not in entry_names:
                    raise InvalidParseTableCache("unknown nonterminal")
                if not isinstance(action, Goto):
                    raise InvalidParseTableCache("non-goto action for a nonterminal")
            if symbol in table.table[state]:
                raise InvalidParseTableCache("duplicate table cell")
            table.table[state][symbol] = action
    return table, entry_state


def _load_parse_table_cache[T](
    path: Path,
    fingerprint: str,
    tokens: list[type[Token]],
    reductions: dict[int, Reduce[T]],
    entry_names: list[str],
) -> tuple[Table[T], dict[str, int]] | None:
    try:
        with path.open(encoding="utf-8") as cache_file:
            raw = cast(object, json.load(cache_file))
        return _decode_parse_table_cache(
            raw, fingerprint, tokens, reductions, entry_names
        )
    except FileNotFoundError:
        return None
    except StaleParseTableCache as error:
        logger.info("Rebuilding stale parse-table cache %s: %s", path, error)
        return None
    except (OSError, RecursionError, UnicodeDecodeError, ValueError) as error:
        logger.warning("Ignoring parse-table cache %s: %s", path, error)
        return None


def _parse_table_cache_identity[T](
    rules: list[Rule[T]],
) -> tuple[str, list[type[Token]], dict[type[Token], int]]:
    """Build the grammar fingerprint and terminal registry used by the cache."""
    tokens: list[type[Token]] = []
    token_ids: dict[type[Token], int] = {}
    encoded_rules: list[object] = []
    for rule in rules:
        encoded_productions: list[object] = []
        for right, _, prec_override in rule.rights:
            encoded_right: list[object] = []
            for symbol in right:
                if isinstance(symbol, type):
                    if symbol not in token_ids:
                        token_ids[symbol] = len(tokens)
                        tokens.append(symbol)
                    encoded_right.append(["token", token_ids[symbol]])
                else:
                    encoded_right.append(["nonterminal", symbol])
            encoded_productions.append(
                {
                    "right": encoded_right,
                    "precedence": prec_override,
                }
            )
        encoded_rules.append(
            {
                "left": rule.left,
                "productions": encoded_productions,
            }
        )

    token_descriptors = [
        {
            "module": token.__module__,
            "qualname": token.__qualname__,
            "name": token.__name__,
            "precedence": token.precedence,
            "associative": token.associative,
        }
        for token in tokens
    ]
    fingerprint = _cache_digest(
        {
            "rules": encoded_rules,
            "tokens": token_descriptors,
        }
    )
    return fingerprint, tokens, token_ids


def _write_parse_table_cache[T](
    path: Path,
    fingerprint: str,
    table: Table[T],
    entry_state: dict[str, int],
    token_ids: dict[type[Token], int],
) -> None:
    temporary_path: Path | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = _encode_parse_table_cache(fingerprint, table, entry_state, token_ids)
        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as cache_file:
            temporary_path = Path(cache_file.name)
            json.dump(
                payload,
                cache_file,
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
                sort_keys=True,
            )
            cache_file.flush()
            os.fsync(cache_file.fileno())
        os.replace(temporary_path, path)
        temporary_path = None
    except (KeyError, OSError, TypeError, ValueError) as error:
        logger.warning("Unable to write parse-table cache %s: %s", path, error)
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass


class Parser[T]:
    """LALR(1) parser that builds a parse table from a grammar and drives LR parsing.

    Construct a ``Parser`` once from a grammar dict; then call ``parse``
    repeatedly for different inputs.

    Grammar format::

        {
            "non_terminal": [
                ([SYM1, SYM2, "other_nt"], ASTNodeClass, [0, 1]),
                ...
            ],
            ...
        }

    Each rule tuple is ``(rhs, action_type, arg_indices)``:
      * ``rhs``: list of ``type[Token]`` subclasses (terminals) and ``str``
        (non-terminal names).
      * ``action_type``: class to construct on reduction, or ``None`` to pass
        through a single child unchanged.
      * ``arg_indices``: which RHS children to forward to ``action_type.__init__``.

    Pass ``cache_path`` to persist the generated table. Compatible cache files
    are rebound to the current grammar's token and semantic-action classes.

    Attributes:
        table: The completed LR action/goto table.
        entry_state: Mapping from non-terminal name → initial state id for that
            entry point (one entry point per top-level key in the grammar).
        cache_hit: Whether this instance loaded its parse table from
            ``cache_path`` instead of building it.
    """

    table: Table[T]
    entry_state: dict[str, int]
    cache_hit: bool

    def __init__(
        self,
        grammar: Mapping[
            str,
            Sequence[
                tuple[Sequence[type[Token] | str], type[T] | None, list[int]]
                | tuple[
                    Sequence[type[Token] | str], type[T] | None, list[int], type[Token]
                ]
            ],
        ],
        *,
        cache_path: str | os.PathLike[str] | None = None,
    ) -> None:
        # ── Phase 1: Augment grammar ─────────────────────────────────────────
        # For each entry non-terminal X, add an augmented rule
        #   StartVariable(X) → X
        # so the parser has a distinguished start state per entry point.
        # Using StartVariable ensures these rules are never confused with
        # user-defined rules, even if a user names a rule identically.
        #
        # A 3-tuple (right, action, args) is accepted unchanged; a 4-tuple
        # (right, action, args, prec_token) is rewritten to
        # (right, action, args, prec_token.precedence) so Rule receives a plain
        # int override.  Each production is assigned a grammar-wide
        # definition_index (global counter) so equal-precedence R/R conflicts
        # can be resolved by definition order.
        rules: dict[str, Rule[T]] = {}
        user_rules: list[Rule[T]] = []
        entry_rules: list[tuple[StartVariable, Rule[T]]] = []
        start_variables: set[StartVariable] = set()
        global_idx = 0
        for left, productions in grammar.items():
            norm_rights: list[
                tuple[list[type[Token] | str], type[T] | None, list[int], int | None]
            ] = []
            for entry in productions:
                if len(entry) == 4:
                    right, action, args, prec_token = entry
                    prec_override = prec_token.precedence
                else:
                    right, action, args = entry
                    prec_override = None
                normalized_right = list(right)
                norm_rights.append((normalized_right, action, args, prec_override))
            rule = Rule[T](left, norm_rights, global_idx)
            rules[left] = rule
            user_rules.append(rule)
            start_var = StartVariable(left)
            augmented = Rule[T](start_var, [([left], None, [0], None)], 0)
            rules[start_var] = augmented
            entry_rules.append((start_var, augmented))
            start_variables.add(start_var)
            global_idx += len(norm_rights)

        reductions: dict[int, Reduce[T]] = {}
        for rule in user_rules:
            for (right, maker, prec_override), definition_index in zip(
                rule.rights, rule.definition_indices
            ):
                item = Item(
                    rule.left,
                    right,
                    maker,
                    definition_index,
                    prec_override=prec_override,
                )
                reductions[definition_index] = Reduce(
                    rule.left,
                    len(right),
                    maker,
                    item.precedence,
                    definition_index,
                )

        self.cache_hit = False
        cache_file = Path(cache_path) if cache_path is not None else None
        cache_fingerprint: str | None = None
        cache_token_ids: dict[type[Token], int] = {}
        entry_names = [left.orig for left, _ in entry_rules]
        if cache_file is not None:
            cache_fingerprint, cache_tokens, cache_token_ids = (
                _parse_table_cache_identity(user_rules)
            )
            cached = _load_parse_table_cache(
                cache_file,
                cache_fingerprint,
                cache_tokens,
                reductions,
                entry_names,
            )
            if cached is not None:
                self.table, self.entry_state = cached
                self.cache_hit = True
                logger.info("Parser loaded from cache: %s", cache_file)
                return

        # ── Phase 2: Compute FIRST sets ──────────────────────────────────────
        # FIRST(A) is needed to propagate ε through nullable non-terminals
        # during LALR(1) lookahead propagation in Phase 4.
        first_sets = compute_first_sets(rules)

        all_items = {left: rule.items for left, rule in rules.items()}

        # ── Phase 3: Build LR(0) canonical collection ────────────────────────
        # BFS over the LR(0) automaton.  ``state_index`` maps a frozenset of
        # items to the assigned state id, giving O(1) deduplication instead of
        # a linear scan.  ``worklist`` is a deque so processing order is
        # deterministic (FIFO) and independent of Python's hash randomization.
        # Symbols leaving each state are sorted by ``symbol_sort_key`` so state
        # id assignment is stable across runs for the same grammar.
        state_index: dict[frozenset[Item[T]], int] = {}
        state_list: list[State[T]] = []
        edges: list[tuple[State[T], Symbol, State[T]]] = []

        self.entry_state = {}
        bfs: deque[State[T]] = deque()
        for i, (left, rule) in enumerate(entry_rules):
            self.entry_state[left.orig] = i
            init_state, _ = intern_state(
                closure(rule.items, all_items), state_index, state_list
            )
            bfs.append(init_state)

        while bfs:
            state = bfs.popleft()
            logger.debug("Worklist: %d items", len(bfs))
            logger.debug("State %d:\n%s", state.id, state)
            nexts = sorted(
                {sym for item in state.items if (sym := item.next) is not None},
                key=symbol_sort_key,
            )
            logger.debug("Nexts: %s", nexts)
            for symbol in nexts:
                target_state, is_new = intern_state(
                    goto(state.items, symbol, all_items), state_index, state_list
                )
                edges.append((state, symbol, target_state))
                if is_new:
                    bfs.append(target_state)

        # ── Phase 4: Compute LALR(1) per-item lookaheads ────────────────────
        # Build a flat goto_map from the edges collected in Phase 3 and call
        # compute_lalr1_lookaheads (ASU §9.6).  entry_state_ids[i] equals i
        # because entry states are the first interned during Phase 3 BFS.
        goto_map: dict[tuple[int, Symbol], int] = {
            (src.id, sym): tgt.id for src, sym, tgt in edges
        }
        entry_state_ids = [self.entry_state[left.orig] for left, _ in entry_rules]
        lookahead_table = compute_lalr1_lookaheads(
            state_list, entry_rules, entry_state_ids, goto_map, all_items, first_sets
        )
        for state in state_list:
            state.lookaheads = {
                item: lookahead_table[(state.id, item)]
                for item in state.items
                if (state.id, item) in lookahead_table
            }

        # ── Phase 5: Populate action/goto table ──────────────────────────────
        # Shift and Goto actions come directly from the automaton edges.
        self.table = Table(len(state_list))
        for prev, symbol, next in edges:
            if isinstance(symbol, type):
                self.table[prev.id, symbol] = Shift(next.id)

            else:
                self.table[prev.id, symbol] = Goto(next.id)

        # Reduce and Accept actions come from complete items (dot at end).
        # LALR(1): state.lookaheads[item] holds the per-item lookahead set
        # computed in Phase 4.  A reduce for A → α fires only on the tokens
        # in that set.
        # Conflicts are resolved by precedence and associativity:
        #   Shift/Reduce: prefer shift unless the production has higher
        #     precedence than the lookahead token, or equal precedence with
        #     left associativity.
        #   Reduce/Reduce: prefer the higher-precedence production; when
        #     precedences are equal, the earlier-defined production wins
        #     (yacc/bison convention).
        for state in state_list:
            for item in state.items:
                if item.next is None:
                    if item.left in start_variables:
                        self.table[state.id, EOS] = Accept(
                            item.left.orig
                            if isinstance(item.left, StartVariable)
                            else item.left
                        )
                    else:
                        for symbol in state.lookaheads.get(item, set()):
                            reduce_action = _copy_reduce(
                                reductions[item.definition_index]
                            )
                            try:
                                self.table[state.id, symbol] = reduce_action
                            except ShiftReduceConflict:
                                logger.info(
                                    "Shift-Reduce conflict in state %d: %s vs %s",
                                    state.id,
                                    symbol,
                                    item.left,
                                )
                                if item.precedence > symbol.precedence or (
                                    item.precedence == symbol.precedence
                                    and symbol.associative == "left"
                                ):
                                    self.table.resolve_conflict(
                                        state.id, symbol, reduce_action
                                    )
                            except ReduceReduceConflict as e:
                                logger.info(
                                    "Reduce-Reduce conflict in state %d: %s vs %s",
                                    state.id,
                                    e.left,
                                    item.left,
                                )
                                if item.precedence > e.precedence:
                                    self.table.resolve_conflict(
                                        state.id, symbol, reduce_action
                                    )
                                elif item.precedence == e.precedence:
                                    if item.definition_index < e.definition_index:
                                        self.table.resolve_conflict(
                                            state.id, symbol, reduce_action
                                        )
        if cache_file is not None and cache_fingerprint is not None:
            _write_parse_table_cache(
                cache_file,
                cache_fingerprint,
                self.table,
                self.entry_state,
                cache_token_ids,
            )
        logger.info("Parser created")

    def parse(self, var: str, lexbuf: Iterable[Token]) -> T | Token:
        """Parse ``lexbuf`` as the non-terminal ``var`` and return the root AST node.

        Implements the standard LR parsing algorithm (Aho-Sethi-Ullman §4.6):
        maintain a state stack and a symbol stack; on each step look up the
        action for the current state and lookahead token class.

        The ``key`` variable holds the current lookahead *class* (not instance).
        After a ``Reduce`` the driver does *not* consume a new token; instead it
        sets ``key = left`` (the reduced non-terminal) and re-enters the action
        lookup, which will find a ``Goto`` action to push the new state.

        Args:
            var: The entry non-terminal to parse (must be a key in the grammar
                passed to ``__init__``).
            lexbuf: An iterable of ``Token`` instances produced by the lexer.
                An ``EOS`` sentinel is appended automatically.

        Returns:
            The root value produced by the top-level semantic action.

        Raises:
            ParsingError: On unexpected token, missing action, or wrong
                acceptance symbol.
        """
        lexbuf = chain(iter(lexbuf), [EOS("", lineno=0, offset=0)])

        state = self.entry_state[var]
        stack = [state]
        symbols = list[T | Token]()

        key: type[Token] | str | None = None
        token: Token | None = None
        last_token: Token | None = None
        while True:
            if token is None:
                token = next(lexbuf, None)
            if token is None:
                raise ParsingError(
                    "Unexpected end of input",
                    token=None,
                    lineno=last_token.lineno if last_token else 0,
                    offset=last_token.offset if last_token else 0,
                    expected=self.table.expected_tokens(state),
                )
            if key is None:
                key = type(token)

            try:
                action = self.table[state, key]
            except KeyError:
                raise ParsingError(
                    f"Unexpected token: {type(token).__name__}",
                    token=token,
                    lineno=token.lineno,
                    offset=token.offset,
                    expected=self.table.expected_tokens(state),
                ) from None
            logger.debug("State: %d, Symbol: %s, Action: %s", state, key, action)
            key = None
            match action:
                case Shift(next=n):
                    state = n
                    stack.append(state)
                    symbols.append(token)
                    last_token = token
                    token = None

                case Reduce(left, n, maker):
                    if n > 0:
                        # Pop stack
                        stack = stack[:-n]

                        # Pop symbols
                        poped_symbols = symbols[-n:]
                        symbols = symbols[:-n]

                        # Make new symbol
                        symbols.append(maker(*poped_symbols))

                    else:
                        symbols.append(maker())

                    # Prepare next
                    state = stack[-1]
                    key = left

                case Goto(next=n):
                    state = n
                    stack.append(state)

                case Accept(symbol):
                    if symbol != var:
                        raise ParsingError(
                            f"Unexpected symbol parsed: {symbol}",
                            token=token,
                            lineno=token.lineno,
                            offset=token.offset,
                            expected=self.table.expected_tokens(state),
                        )
                    break

                case _:
                    raise ParsingError(
                        f"No action for state {state} and symbol {key}",
                        token=token,
                        lineno=token.lineno,
                        offset=token.offset,
                        expected=self.table.expected_tokens(state),
                    )

        return symbols[-1]
