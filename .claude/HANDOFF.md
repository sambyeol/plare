# Plare Improvement Handoff

This document drives a sequential, multi-agent improvement of the Plare parser.
Each task below is sized for a single agent session. Pick up the **first task
whose status is `TODO` and whose dependencies are `DONE`**. When you finish,
flip your task's checkbox, fill in `Notes:`, and stop — do not start the next
task in the same session.

The motivating analysis lives at `~/.claude/plans/yacc-floofy-pine.md` (planner
output). Background: this codebase implements **SLR(1)** parsing with operator
precedence/associativity for conflict resolution. The improvements below move
it toward a more correct, deterministic, and ergonomic LALR(1) implementation.

## Common Guardrails

- Stay in your task's scope. Do not touch files outside `Files:` unless
  unavoidable, and if so, explain in `Notes:`.
- If a previously green test goes red and you cannot make it pass within your
  scope, **stop and report**. Do not weaken or `xfail` the test to move on.
- Every comment, docstring, log message, and commit message you add must be in
  **English**.
- Match existing code style (PEP 695 generics, structural pattern matching,
  `from __future__ import annotations`, `rich` for logging).

## Within-Session Commit Rules

- A single task = a single session, but inside that session split work into
  **meaningful, self-contained commits**. Never produce one giant commit.
- Pure refactors (no behavior change) and behavior changes go in **separate
  commits**.
- Extracting a function/module is one commit; migrating call sites is the next.
- Every commit must independently pass `pytest -q`. **No WIP commits.**
- Commit messages: English, conventional style. Examples:
  - `docs(parser): document SLR(1) invariants on closure/goto`
  - `refactor(parser): extract compute_first_sets`
  - `test(parser): cover dangling-else (xfail)`
  - `feat(parser): use LALR(1) lookaheads for reduce actions`
- Update **this file's** Status/Notes for your task in the *last* commit of
  your series.

## Verification Baseline

From the repo root:

```
pytest -q
```

All tests must be green before you start and before you finish your task
(except items explicitly marked `xfail` by an earlier task — those should stay
`xfail` until T6 turns them green).

---

## Dependency Graph

```
T0 (English docstrings/comments)
  └─ T1 (test safety net)
       └─ T2 (FIRST/FOLLOW fixed-point)
            └─ T3 (state indexing + determinism)
                 └─ T4 (hash & Token semantics)
                      └─ T5 (yacc-style conflict resolution + %prec)
                           └─ T6 (LALR(1) upgrade)
                                └─ T7 (error reporting + API cleanup)
```

---

## T0 — English docstrings & comments

- [x] Status: DONE
- Depends on: —
- Scope: Pure documentation pass over `plare/*.py`. **No behavior changes.**
- Files: `plare/parser.py`, `plare/lexer.py`, `plare/token.py`,
  `plare/exception.py`, `plare/utils.py`
- Acceptance:
  - Every public class and function has a docstring (one-line summary,
    plus Args/Returns when non-trivial).
  - Core LR routines (`closure`, `goto`, `Rule.calc_first`, `Rule.calc_follow`,
    the staged blocks inside `Parser.__init__`, `Parser.parse`) carry comments
    that state **this is SLR(1)**, what invariants the code relies on, and
    *why* — not what each line does.
  - Any existing Korean strings/comments are translated to English.
  - `git diff --stat` after the task shows changes are dominantly in
    docstrings and comments. No logic edits, no renames.
  - `pytest -q` is green and unchanged from before the task.
- Verify:
  - `pytest -q`
  - `git log --oneline` shows a small series of commits (e.g., one per file or
    one per logical chunk).
- Notes: No Korean strings were present; the entire task was adding missing
  docstrings and SLR(1) algorithm comments. Six source files updated in six
  commits on branch `task/t0-english-docs`. All 8 tests remain green.

---

## T1 — Test safety net

- [x] Status: DONE
- Depends on: T0
- Scope: Expand `tests/test_parser.py` (and add new test files if helpful).
  **Do not modify `plare/` source.**
- Files: `tests/test_parser.py` (and possibly new `tests/test_*.py`)
- Acceptance:
  - New cases cover, at minimum: ε-productions, left recursion, right
    recursion, operator precedence, left & right associativity, multiple
    grammar entry points, currently-working shift/reduce resolution.
  - Add **at least 2 cases that LALR(1) should accept but SLR(1) cannot**
    (e.g., dangling-else variants, classic LALR-but-not-SLR grammars). Mark
    them with `pytest.mark.xfail(strict=True, reason="requires LALR(1)")`.
  - `pytest -q` is green; xfail cases are reported as `xfailed`, not `xpassed`.
- Verify: `pytest -q`
- Notes: Added `tests/test_parser_safety_net.py` with 10 tests (8 passing, 2 xfail).
  The 2 xfail tests use the Aho/Sethi/Ullman LALR(1)-only grammar where
  FOLLOW(A_nt) == FOLLOW(B_nt) causes an unresolvable SLR(1) R/R conflict.
  Result: `16 passed, 2 xfailed` on branch `task/t1-test-safety-net`.

---

## T2 — FIRST/FOLLOW as fixed-point iteration

- [x] Status: DONE
- Depends on: T1
- Files: `plare/parser.py` (replace `Rule.calc_first` and `Rule.calc_follow`
  in `parser.py:298-377`); add unit tests under `tests/test_first_follow.py`
- Acceptance:
  - Replace the self-recursion-guarded computations with standard worklist /
    "iterate until no change" fixed-point algorithms over the full ruleset.
  - Extract pure functions (e.g., `compute_first_sets(rules)` and
    `compute_follow_sets(rules, first_sets)`) so they are unit-testable
    independently of `Parser.__init__`.
  - Add a unit test for **mutual recursion that the previous code could
    infinite-loop on**: e.g., `A → B α | a`, `B → A β | b`, with α/β nullable
    where relevant. The test must terminate quickly (`pytest --timeout=5`).
  - Add textbook-grammar tests with hand-computed expected FIRST/FOLLOW sets.
  - All previous tests (T1) still pass.
- Verify: `pytest -q`
- Notes: Added `compute_first_sets` and `compute_follow_sets` as module-level
  pure functions in `plare/parser.py`; `Parser.__init__` Phase 2/3 now calls
  these functions and assigns results directly to `rule.first`/`rule.follow`;
  `Rule.calc_first` and `Rule.calc_follow` are retained as thin wrappers.
  Added `tests/test_first_follow.py` with 5 tests (mutual-recursion termination
  with `@pytest.mark.timeout(5)`, ε-propagation, nullable chain, Dragon Book
  expression grammar FIRST and FOLLOW). Added `pytest-timeout>=2` to
  `pyproject.toml` test dependencies.
  Result: `21 passed, 2 xfailed` on branch `task/t2-first-follow-fixpoint`.

---

## T3 — State indexing & determinism

- [ ] Status: TODO
- Depends on: T2
- Files: `plare/parser.py` (canonical-collection construction at
  `parser.py:448-485`, `State` class at `parser.py:137-152`)
- Acceptance:
  - Replace the linear scan `for exist in states: if exist == next_state` with
    a `dict[frozenset[Item], int]` mapping itemset → state id.
  - Replace the `set`-based `worklist` with a deterministic structure
    (`collections.deque`, or list + index) so processing order does not depend
    on hash randomization.
  - State id assignment is **deterministic across runs** for the same grammar
    input. Add a test that builds the same parser twice and asserts identical
    `entry_state` and table action sequences.
  - Note in `Notes:` a rough before/after build-time measurement for a
    moderately sized grammar (50+ rules — write a tiny generator if needed).
  - All previous tests pass.
- Verify: `pytest -q` plus the new determinism test.
- Notes:

---

## T4 — Hash & Token semantics

- [ ] Status: TODO
- Depends on: T3
- Files: `plare/parser.py`, `plare/token.py`
- Acceptance:
  - `Item.__hash__` (currently `parser.py:125-126`, sum-based) → tuple-based:
    `hash((self.left, tuple(self.right), self.loc))`.
  - `State.__hash__` derives from a `frozenset` of items (delegating to the
    cache key chosen in T3 if applicable).
  - Audit every use of `Token.__eq__` / `Token.__hash__` in
    `plare/`, `tests/`, and `examples/`. Decide whether instance-level
    equality (current: same class + lineno + offset) is intentional or a
    leak. Document the chosen contract in `Token`'s docstring. The parser
    keys on token *classes*, not instances — make that explicit.
  - All previous tests pass; add a small test that two `Item` objects
    constructed independently from equal data hash equally and compare equal.
- Verify: `pytest -q`
- Notes:

---

## T5 — yacc-conventional conflict resolution + `%prec`

- [ ] Status: TODO
- Depends on: T4
- Files: `plare/parser.py` (`Item.__init__` precedence rule at
  `parser.py:83-92`, conflict resolution at `parser.py:502-530`, grammar
  signature in `Parser.__init__`), `examples/calc/calc.py` (only if needed)
- Acceptance:
  - **Production precedence = the precedence of the *last* terminal in the
    production** (not the first non-zero one).
  - Extend the grammar tuple to allow a per-production precedence override:
    `(rhs, action, args)` and `(rhs, action, args, prec_token)` both accepted.
    When `prec_token` is given, its `precedence` and `associative` fix the
    production. Keep the 3-tuple form working (backwards compatible).
  - **Reduce/Reduce resolution: earlier-defined production wins**, leveraging
    the deterministic ordering established in T3. Same-precedence R/R between
    *different* productions still raises `ParserError` only when neither rule
    can be deterministically picked under this convention.
  - Add a test for unary minus using a `prec_token` override on a `MINUS exp`
    production.
  - Add a test asserting deterministic R/R winner under definition order.
  - The existing `examples/calc/calc.py` keeps producing the same outputs
    (it currently sidesteps unary minus in the lexer; do not regress that).
- Verify:
  - `pytest -q`
  - `python examples/calc/calc.py <example input>` still prints expected AST
    and result (write a tiny throwaway input file or reuse one in the repo).
- Notes:

---

## T6 — LALR(1) upgrade

- [ ] Status: TODO
- Depends on: T5
- Files: `plare/parser.py` (`Item` adds a `lookahead` attribute on kernel
  items; lookahead computation phase added between LR(0) state construction
  and reduce-action placement; reduce placement at `parser.py:486-501`
  switches from `rules[item.left].follow` to `item.lookahead`)
- Approach: kernel-based LALR(1) using DeRemer-Pennello or the
  Aho-Sethi-Ullman §9.6 spontaneous-generation + propagation method:
    1. Build LR(0) automaton (already done by current code).
    2. Determine spontaneously generated lookaheads and propagation links per
       kernel item.
    3. Iterate to a fixed point.
    4. Place reduce actions per `(state, item)` using `item.lookahead`.
- Acceptance:
  - All `xfail` cases marked in T1 now pass (remove `xfail` markers).
  - Every grammar SLR(1) accepted still parses identically (run T1 suite +
    examples). Verify by running both `examples/calc/calc.py` and
    `examples/sum_of_list/sum.py` end-to-end on representative inputs.
  - No regression in determinism or build time beyond a constant factor.
- Verify:
  - `pytest -q`
  - `python examples/calc/calc.py <input>`
  - `python examples/sum_of_list/sum.py <input>`
- Notes:

---

## T7 — Error reporting & API cleanup

- [ ] Status: TODO
- Depends on: T6
- Files: `plare/parser.py` (`Parser.parse` error paths at `parser.py:550-553`
  and `parser.py:592`; `Table.force_update` at `parser.py:275-276`),
  `plare/exception.py`
- Acceptance:
  - `ParsingError` carries: offending token, `lineno`, `offset`, and the list
    of expected token classes (the keys of `self.table[state]` filtered to
    `type[Token]`). Provide a readable `__str__`.
  - `LexingError` and `ParsingError` share a consistent format.
  - `Table.force_update` is either renamed to `_force_update` and only used
    inside `Table`, or removed in favor of a proper `Table.resolve_conflict`
    method that takes the conflict context and updates internally.
  - Add at least 2 unit tests asserting the error message contents (token,
    location, expected set).
  - Public API surface (anything imported in `plare/__init__.py` or in
    examples) is documented in module-level docstrings.
- Verify: `pytest -q`
- Notes:

---

## When all tasks are DONE

- All checkboxes ticked, all `Notes:` filled.
- `pytest -q` green with **no `xfail`** entries remaining (T6 should have
  cleared them).
- `examples/calc/calc.py` and `examples/sum_of_list/sum.py` run successfully
  on representative inputs.
- Open a summary PR (or commit on `master`) referencing this file's final
  state. The handoff file itself can stay in the repo as historical record or
  be archived under `.claude/handoff-archive/` — that decision is up to the
  user, not an agent.
