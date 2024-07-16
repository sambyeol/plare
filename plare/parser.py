from __future__ import annotations

from itertools import chain
from typing import Any, Iterable, Protocol

from plare.exception import ParserError, ParsingError
from plare.token import Token
from plare.utils import logger


class EOS(Token):
    pass


class EPSILON(Token):
    pass


type Symbol = type[Token] | str


class Maker[T](Protocol):
    def __call__(self, *xs: T | Token) -> T | Token: ...


class TMaker[T](Maker[T]):
    def __init__(self, type: type[T], args: list[int]) -> None:
        self.type = type
        self.args = args

    def __call__(self, *xs: T | Token) -> T:
        return self.type(*[xs[i] for i in self.args])

    def __str__(self) -> str:
        args = ", ".join(map(lambda a: f"${a}", self.args))
        return f"{self.type.__name__}({args})"


class IDMaker[T](Maker[T]):
    def __init__(self, arg: int) -> None:
        self.arg = arg

    def __call__(self, *xs: T | Token) -> T | Token:
        return xs[self.arg]

    def __str__(self) -> str:
        return f"${self.arg}"


class StartVariable(str):
    def __init__(self, variable: str) -> None:
        self.orig = variable

    def __hash__(self) -> int:
        return super().__hash__()

    def __eq__(self, other: Any) -> bool:
        return isinstance(other, StartVariable) and super().__eq__(other)

    def __ne__(self, other: Any) -> bool:
        return not isinstance(other, StartVariable) or super().__ne__(other)


class Item[T]:
    left: str | StartVariable
    right: list[Symbol]
    loc: int
    maker: Maker[T]
    precedence: int

    def __init__(
        self,
        left: str | StartVariable,
        right: list[Symbol],
        maker: Maker[T],
        loc: int = 0,
    ) -> None:
        self.left = left
        self.right = right
        self.loc = loc
        self.maker = maker
        self.precedence = 0
        terminals = [t for t in right if isinstance(t, type)]
        for token in terminals:
            if token.precedence > 0:
                self.precedence = token.precedence
                break
        else:
            for token in terminals:
                if token.precedence < 0:
                    self.precedence = token.precedence
                    break

    @property
    def next(self) -> Symbol | None:
        return self.right[self.loc] if self.loc < len(self.right) else None

    def move(self, symbol: Symbol) -> Item[T] | None:
        next = self.next
        if type(symbol) == type(next) and symbol == next:
            return Item(
                self.left,
                self.right,
                self.maker,
                self.loc + 1,
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
        return hash(self.left) + sum(map(hash, self.right)) + hash(self.loc)

    def __eq__(self, value: Any) -> bool:
        return (
            isinstance(value, Item)
            and self.left == value.left
            and self.right == value.right
            and self.loc == value.loc
        )


class State[T]:
    id: int
    items: set[Item[T]]

    def __init__(self, id: int, items: set[Item[T]]) -> None:
        self.id = id
        self.items = items

    def __hash__(self) -> int:
        return sum(map(hash, (item for item in self.items)))

    def __eq__(self, other: State[T] | Any) -> bool:
        return isinstance(other, State) and self.items == other.items

    def __str__(self) -> str:
        return "\n".join(map(str, self.items))


class Shift:
    __match_args__ = ("next",)

    next: int

    def __init__(self, next: int) -> None:
        self.next = next

    def __str__(self) -> str:
        return f"Shift({self.next})"


class Reduce[T]:
    __match_args__ = ("left", "n", "maker")

    left: str
    n: int
    maker: Maker[T]
    precedence: int

    def __init__(self, left: str, n: int, maker: Maker[T], precedence: int) -> None:
        self.left = left
        self.n = n
        self.maker = maker
        self.precedence = precedence

    def __str__(self) -> str:
        return f"Reduce({self.n}, {self.maker})"


class Accept:
    __match_args__ = ("symbol",)

    symbol: str

    def __init__(self, symbol: str) -> None:
        self.symbol = symbol

    def __str__(self) -> str:
        return f"Accept({self.symbol})"


class Goto:
    __match_args__ = ("next",)

    next: int

    def __init__(self, next: int) -> None:
        self.next = next

    def __str__(self) -> str:
        return f"Goto({self.next})"


type Action[T] = Shift | Reduce[T] | Accept | Goto


class Conflict(Exception):
    pass


class ShiftReduceConflict(Conflict):
    pass


class ReduceReduceConflict(Conflict):
    def __init__(self, left: str, precedence: int) -> None:
        self.left = left
        self.precedence = precedence


class Table[T]:
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
                        raise ReduceReduceConflict(exist.left, exist.precedence)
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
        self.table[state][symbol] = action


class Rule[T]:
    left: str
    rights: list[tuple[list[Symbol], Maker[T]]]
    first: set[type[Token]]
    follow: set[type[Token]]

    def __init__(
        self,
        left: str,
        rights: list[tuple[list[Symbol], type[T] | None, list[int]]],
    ) -> None:
        self.left = left
        self.rights = [
            (right, TMaker(action, args) if action is not None else IDMaker(*args))
            for right, action, args in rights
        ]
        self.first_built = False
        self.follow_built = False

    def calc_first(self, rules: dict[str, Rule[T]]) -> set[type[Token]]:
        if self.first_built:
            return self.first

        recursive_rights = list[list[Symbol]]()
        self.first = set()
        for right, _ in self.rights:
            if len(right) == 0:
                self.first.add(EPSILON)
                continue
            for i, token in enumerate(right):
                if isinstance(token, type):
                    if token == EPSILON:
                        continue
                    self.first.add(token)
                    break

                else:
                    if token == self.left:
                        recursive_rights.append(right[i + 1 :])
                        break
                    token_first = rules[token].calc_first(rules)
                    self.first.update(token_first)
                    if EPSILON not in token_first:
                        break

        if EPSILON in self.first:
            for right in recursive_rights:
                for token in right:
                    if isinstance(token, type):
                        if token == EPSILON:
                            continue
                        self.first.add(token)
                        break

                    else:
                        if token == self.left:
                            continue
                        token_first = rules[token].calc_first(rules)
                        self.first.update(token_first)
                        if EPSILON not in token_first:
                            break

        self.first_built = True
        logger.debug("First(%s) = %s", self.left, self.first)
        return self.first

    def calc_follow(self, rules: dict[str, Rule[T]]) -> set[type[Token]]:
        if self.follow_built:
            return self.follow

        self.follow = set()
        if isinstance(self.left, StartVariable):
            self.follow.add(EOS)

        else:
            for rule in rules.values():
                for right, _ in rule.rights:
                    for i, token in enumerate(right):
                        if not isinstance(token, str) or token != self.left:
                            continue

                        if i + 1 < len(right):
                            next_token = right[i + 1]
                            if isinstance(next_token, type):
                                self.follow.add(next_token)
                            else:
                                next_first = rules[next_token].first
                                self.follow.update(next_first - set([EPSILON]))
                                if EPSILON in next_first and next_token != self.left:
                                    self.follow.update(
                                        rules[next_token].calc_follow(rules)
                                    )
                        else:
                            if rule.left != self.left:
                                self.follow.update(rule.calc_follow(rules))

        self.follow_built = True
        logger.debug("Follow(%s) = %s", self.left, self.follow)
        return self.follow

    def __hash__(self) -> int:
        return hash(self.left)

    def __eq__(self, value: Any) -> bool:
        return isinstance(value, Rule) and self.left == value.left

    def __repr__(self) -> str:
        return f"Rule({self.left})"

    @property
    def items(self) -> set[Item[T]]:
        return set(Item(self.left, right, maker) for right, maker in self.rights)


def closure[T](items: set[Item[T]], all_items: dict[str, set[Item[T]]]) -> set[Item[T]]:
    items = set(items)
    worklist = set(items)
    while len(worklist) > 0:
        item = worklist.pop()
        next = item.next
        if next is None or isinstance(next, type):
            continue
        to_update = all_items[next] - items
        if len(to_update) > 0:
            worklist.update(to_update)
            items.update(to_update)
    return items


def goto[
    T
](
    items: set[Item[T]],
    symbol: Symbol,
    all_items: dict[str, set[Item[T]]],
) -> set[
    Item[T]
]:
    return closure(
        set(next for item in items if (next := item.move(symbol)) is not None),
        all_items,
    )


class Parser[T]:
    table: Table[T]
    entry_state: dict[str, int]

    def __init__(
        self,
        grammar: dict[
            str,
            list[tuple[list[type[Token] | str], type[T] | None, list[int]]],
        ],
    ) -> None:
        entry_rules = {
            StartVariable(left): Rule[T](StartVariable(left), [([left], None, [0])])
            for left in grammar.keys()
        }
        start_variables = set(entry_rules.keys())

        rules = {left: Rule[T](left, rights) for left, rights in grammar.items()}
        rules |= entry_rules
        for rule in rules.values():
            rule.calc_first(rules)
        for rule in rules.values():
            rule.calc_follow(rules)
        all_items = {left: rule.items for left, rule in rules.items()}
        all_tokens = set[type[Token]]()
        for rule in rules.values():
            for right, _ in rule.rights:
                all_tokens.update(t for t in right if isinstance(t, type))

        states = set[State[T]]()
        self.entry_state = {}
        for i, (left, rule) in enumerate(entry_rules.items()):
            self.entry_state[left.orig] = i
            states.add(State(i, closure(rule.items, all_items)))
        edges = set[tuple[State[T], Symbol, State[T]]]()

        worklist = set(states)
        while len(worklist) > 0:
            logger.debug("Worklist: %d items", len(worklist))
            state = worklist.pop()
            logger.debug("State %d:\n%s", state.id, state)
            nexts = {next for item in state.items if (next := item.next) is not None}
            logger.debug("Nexts: %s", nexts)

            for symbol in nexts:
                len_prev_states = len(states)
                len_prev_edges = len(edges)

                next_state = State(len(states), goto(state.items, symbol, all_items))
                states.add(next_state)
                for exist in states:
                    if exist == next_state:
                        next_state = exist
                        break
                edges.add((state, symbol, next_state))

                if len(states) != len_prev_states or len(edges) != len_prev_edges:
                    worklist.update({next_state})

        self.table = Table(len(states))
        for prev, symbol, next in edges:
            if isinstance(symbol, type):
                self.table[prev.id, symbol] = Shift(next.id)

            else:
                self.table[prev.id, symbol] = Goto(next.id)

        for state in states:
            for item in state.items:
                if item.next is None:
                    if item.left in start_variables:
                        self.table[state.id, EOS] = Accept(item.left.orig)
                    else:
                        for symbol in rules[item.left].follow:
                            reduce_action = Reduce(
                                item.left, len(item.right), item.maker, item.precedence
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
                                    raise ParserError(
                                        f"Reduce-Reduce conflict in state {state.id}: {e.left} vs {item.left}"
                                    ) from None
        logger.info("Parser created")

    def parse(self, var: str, lexbuf: Iterable[Token]) -> T | Token:
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
