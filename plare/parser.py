"""SLR(1) parser with operator-precedence conflict resolution.

This module implements an **SLR(1)** (Simple LR, 1 token of lookahead) parser.
The key characteristic of SLR(1) is that reduce actions fire on the full
FOLLOW set of the reduced non-terminal, rather than on the tighter per-item
lookahead sets used by LALR(1) or canonical LR(1).  This is an
over-approximation that can cause spurious conflicts for grammars that LALR(1)
would accept without conflict.  The LALR(1) upgrade is tracked in T6.

Construction pipeline (``Parser.__init__``):
    1. Augment the grammar with ``StartVariable(X) → X`` entry rules.
    2. Compute FIRST sets for every non-terminal.
    3. Compute FOLLOW sets for every non-terminal (requires FIRST sets).
    4. Build the LR(0) canonical collection (states + transitions) via
       ``closure`` / ``goto`` BFS.
    5. Populate the action/goto table; resolve shift/reduce and reduce/reduce
       conflicts using token precedence and associativity.
"""

from __future__ import annotations

from collections import deque
from itertools import chain
from typing import Any, Iterable, Protocol

from plare.exception import ParserError, ParsingError
from plare.token import Token
from plare.utils import logger


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

    def __eq__(self, other: Any) -> bool:
        return isinstance(other, StartVariable) and super().__eq__(other)

    def __ne__(self, other: Any) -> bool:
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

    def __eq__(self, value: Any) -> bool:
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
    """

    id: int
    items: set[Item[T]]

    def __init__(self, id: int, items: set[Item[T]]) -> None:
        self.id = id
        self.items = items

    def __hash__(self) -> int:
        return hash(frozenset(self.items))

    def __eq__(self, other: State[T] | Any) -> bool:
        return isinstance(other, State) and self.items == other.items

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

    def force_update(self, state: int, symbol: Symbol, action: Action[T]) -> None:
        """Overwrite a table entry without conflict checking.

        Used exclusively by ``Parser.__init__`` after it has decided which
        action wins a conflict.  Must not be called for any other purpose.
        """
        self.table[state][symbol] = action


class Rule[T]:
    """All RHS alternatives for a single non-terminal, together with its FIRST/FOLLOW sets.

    ``Rule`` is the unit of grammar specification.  One ``Rule`` object
    aggregates every production ``A → rhs₁ | rhs₂ | …`` for a given
    non-terminal ``A``.

    Attributes:
        left: The non-terminal name (LHS).
        rights: List of ``(rhs_symbols, maker)`` pairs, one per alternative.
        first: FIRST(A) — populated by ``calc_first``.
        follow: FOLLOW(A) — populated by ``calc_follow``.
    """

    left: str
    rights: list[tuple[list[Symbol], Maker[T], int | None]]
    definition_indices: list[int]
    first: set[type[Token]]
    follow: set[type[Token]]

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
        self.first_built = False
        self.follow_built = False

    def calc_first(self, rules: dict[str, Rule[T]]) -> set[type[Token]]:
        """Return FIRST(A), computing it via ``compute_first_sets`` if needed.

        Args:
            rules: Complete grammar mapping non-terminal name → ``Rule``.

        Returns:
            The FIRST set for this non-terminal (also stored in ``self.first``).
        """
        if not self.first_built:
            fs = compute_first_sets(rules)
            for n, r in rules.items():
                r.first = fs[n]
                r.first_built = True
        return self.first

    def calc_follow(self, rules: dict[str, Rule[T]]) -> set[type[Token]]:
        """Return FOLLOW(A), computing it via ``compute_follow_sets`` if needed.

        Args:
            rules: Complete grammar mapping non-terminal name → ``Rule``.

        Returns:
            The FOLLOW set for this non-terminal (also stored in ``self.follow``).
        """
        if not self.follow_built:
            fs = {n: r.first for n, r in rules.items()}
            fw = compute_follow_sets(rules, fs)
            for n, r in rules.items():
                r.follow = fw[n]
                r.follow_built = True
        return self.follow

    def __hash__(self) -> int:
        return hash(self.left)

    def __eq__(self, value: Any) -> bool:
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


def compute_follow_sets[T](
    rules: dict[str, Rule[T]],
    first_sets: dict[str, set[type[Token]]],
) -> dict[str, set[type[Token]]]:
    """Compute FOLLOW sets for all non-terminals via worklist fixed-point iteration.

    Seeds EOS into every augmented start symbol, then propagates terminals
    through productions until no FOLLOW set changes.  Requires FIRST sets
    to have been computed first.

    Args:
        rules: Complete grammar mapping non-terminal name → ``Rule``.
        first_sets: Precomputed FIRST sets (from ``compute_first_sets``).

    Returns:
        Mapping from non-terminal name to its FOLLOW set.
    """
    follow: dict[str, set[type[Token]]] = {name: set() for name in rules}
    for name in rules:
        if isinstance(name, StartVariable):
            follow[name].add(EOS)
    changed = True
    while changed:
        changed = False
        for lhs, rule in rules.items():
            for right, _, _ in rule.rights:
                for i, sym in enumerate(right):
                    if not isinstance(sym, str):
                        continue
                    trailer: set[type[Token]] = set()
                    all_nullable = True
                    for next_sym in right[i + 1 :]:
                        if isinstance(next_sym, type):
                            trailer.add(next_sym)
                            all_nullable = False
                            break
                        else:
                            next_first = first_sets[next_sym]
                            trailer.update(next_first - {EPSILON})
                            if EPSILON not in next_first:
                                all_nullable = False
                                break
                    if all_nullable:
                        trailer.update(follow[lhs])
                    added = trailer - follow[sym]
                    if added:
                        follow[sym].update(added)
                        changed = True
    return follow


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


class Parser[T]:
    """SLR(1) parser that builds a parse table from a grammar and drives LR parsing.

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

    Attributes:
        table: The completed LR action/goto table.
        entry_state: Mapping from non-terminal name → initial state id for that
            entry point (one entry point per top-level key in the grammar).
    """

    table: Table[T]
    entry_state: dict[str, int]

    def __init__(
        self,
        grammar: dict[
            str,
            list[
                tuple[list[type[Token] | str], type[T] | None, list[int]]
                | tuple[list[type[Token] | str], type[T] | None, list[int], type[Token]]
            ],
        ],
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
                    norm_rights.append((right, action, args, prec_token.precedence))
                else:
                    right, action, args = entry
                    norm_rights.append((right, action, args, None))
            rules[left] = Rule[T](left, norm_rights, global_idx)
            start_var = StartVariable(left)
            augmented = Rule[T](start_var, [([left], None, [0], None)], 0)
            rules[start_var] = augmented
            entry_rules.append((start_var, augmented))
            start_variables.add(start_var)
            global_idx += len(norm_rights)

        # ── Phase 2: Compute FIRST sets ──────────────────────────────────────
        # FIRST(A) is needed to propagate ε through nullable non-terminals
        # when computing FOLLOW sets in Phase 3.
        first_sets = compute_first_sets(rules)
        for name, rule in rules.items():
            rule.first = first_sets[name]
            rule.first_built = True

        # ── Phase 3: Compute FOLLOW sets (SLR(1) lookaheads) ─────────────────
        # In SLR(1), a reduce action for rule A → α fires on every token in
        # FOLLOW(A).  This is the defining over-approximation of SLR(1):
        # it uses the global follow set rather than per-item lookaheads.
        # Spurious conflicts arise when FOLLOW(A) contains tokens that cannot
        # actually follow A in the specific state.  LALR(1) (T6) eliminates
        # this by computing per-item lookaheads.
        follow_sets = compute_follow_sets(rules, first_sets)
        for name, rule in rules.items():
            rule.follow = follow_sets[name]
            rule.follow_built = True

        all_items = {left: rule.items for left, rule in rules.items()}
        all_tokens = set[type[Token]]()
        for rule in rules.values():
            for right, _, _ in rule.rights:
                all_tokens.update(t for t in right if isinstance(t, type))

        # ── Phase 4: Build LR(0) canonical collection ────────────────────────
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

        # ── Phase 5: Populate action/goto table ──────────────────────────────
        # Shift and Goto actions come directly from the automaton edges.
        self.table = Table(len(state_list))
        for prev, symbol, next in edges:
            if isinstance(symbol, type):
                self.table[prev.id, symbol] = Shift(next.id)

            else:
                self.table[prev.id, symbol] = Goto(next.id)

        # Reduce and Accept actions come from complete items (dot at end).
        # SLR(1): a reduce for A → α fires on every token in FOLLOW(A).
        # Conflicts are resolved by precedence and associativity:
        #   Shift/Reduce: prefer shift unless the production has higher
        #     precedence than the lookahead token, or equal precedence with
        #     left associativity.
        #   Reduce/Reduce: prefer the higher-precedence production; when
        #     precedences are equal, the earlier-defined production wins
        #     (yacc/bison convention).  This may resolve conflicts that LALR(1)
        #     would handle correctly via per-item lookaheads, but for those
        #     grammars the SLR(1) choice may still be wrong for some inputs.
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
                        for symbol in rules[item.left].follow:
                            reduce_action = Reduce(
                                item.left,
                                len(item.right),
                                item.maker,
                                item.precedence,
                                item.definition_index,
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
                                    self.table.force_update(
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
                                    self.table.force_update(
                                        state.id, symbol, reduce_action
                                    )
                                elif item.precedence == e.precedence:
                                    if item.definition_index < e.definition_index:
                                        self.table.force_update(
                                            state.id, symbol, reduce_action
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
        while True:
            if token is None:
                token = next(lexbuf, None)
            if token is None:
                raise ParsingError("Unexpected end of input")
            if key is None:
                key = type(token)

            try:
                action = self.table[state, key]
            except KeyError:
                raise ParsingError(f"Unexpected symbol: {key}") from None
            logger.debug("State: %d, Symbol: %s, Action: %s", state, key, action)
            key = None
            match action:
                case Shift(next=n):
                    state = n
                    stack.append(state)
                    symbols.append(token)
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
                        raise ParsingError(f"Unexpected symbol parsed: {symbol}")
                    break

                case _:
                    raise ParsingError(f"No action for state {state} and symbol {key}")

        return symbols[-1]
