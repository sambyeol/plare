"""Advanced lexer tests covering scenarios not in test_lexer.py.

Covers: multiline position tracking, column accuracy after whitespace,
block-comment state machine, string-literal state machine, user_state threading,
error position inside a non-start state, and various edge cases.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import NoneType

import pytest

from plare.exception import LexingError
from plare.lexer import Lexer
from plare.token import Token

# ---------------------------------------------------------------------------
# Shared token classes
# ---------------------------------------------------------------------------


class WORD(Token):
    def __init__(self, value: str, *, lineno: int, offset: int) -> None:
        super().__init__(value, lineno=lineno, offset=offset)
        self.value = value


class NUM_A(Token):
    def __init__(self, value: str, *, lineno: int, offset: int) -> None:
        super().__init__(value, lineno=lineno, offset=offset)
        self.value = int(value)


# Lexer that recognises lowercase words; skips newlines and horizontal whitespace.
word_lexer: Lexer[None] = Lexer(
    {
        "start": [
            (r"\n", "start"),
            (r"[ \t]+", "start"),
            (r"[a-z]+", WORD),
        ]
    }
)

# ---------------------------------------------------------------------------
# Section 1: Multiline lineno tracking
# ---------------------------------------------------------------------------


def test_multiline_lineno() -> None:
    """Three words on separate lines each have lineno 1, 2, 3."""
    tokens = list(word_lexer.lex("start", "aa\nbb\ncc"))
    assert len(tokens) == 3
    assert tokens[0].lineno == 1
    assert tokens[1].lineno == 2
    assert tokens[2].lineno == 3


def test_multiline_lineno_blank_lines() -> None:
    """Blank lines between tokens still increment lineno correctly."""
    tokens = list(word_lexer.lex("start", "aa\n\nbb"))
    assert len(tokens) == 2
    assert tokens[0].lineno == 1
    assert tokens[1].lineno == 3


def test_second_line_offset_zero() -> None:
    """First token on a new line has offset=0 after the newline resets the column."""
    tokens = list(word_lexer.lex("start", "ab\ncd"))
    assert len(tokens) == 2
    assert tokens[1].lineno == 2
    assert tokens[1].offset == 0


def test_mid_line_offset() -> None:
    """A token after leading spaces on the same line has the correct column offset."""
    tokens = list(word_lexer.lex("start", "ab  cd"))
    assert len(tokens) == 2
    assert tokens[0].offset == 0
    assert tokens[1].offset == 4


def test_second_line_mid_offset() -> None:
    """A token after leading spaces on line 2 has the right column offset."""
    tokens = list(word_lexer.lex("start", "ab\n   cd"))
    assert len(tokens) == 2
    assert tokens[1].lineno == 2
    assert tokens[1].offset == 3


def test_tab_counts_as_one_column() -> None:
    """A tab character advances the column offset by exactly one."""
    tokens = list(word_lexer.lex("start", "\tab"))
    assert len(tokens) == 1
    assert tokens[0].offset == 1


# ---------------------------------------------------------------------------
# Section 2: Block-comment state machine
# ---------------------------------------------------------------------------

# Lexer with C-style /* ... */ block comments:
#   start → on "/*" → comment state
#   comment → on "*/" → back to start
block_comment_lexer: Lexer[None] = Lexer(
    {
        "start": [
            (r"/\*", "comment"),
            (r"[ \t\n]+", "start"),
            (r"\d+", NUM_A),
        ],
        "comment": [
            (r"\*/", "start"),
            (r"[^*]+", "comment"),
            (r"\*(?!/)", "comment"),
        ],
    }
)


def test_block_comment_ignored() -> None:
    """/* ... */ is consumed without emitting any token."""
    tokens = list(block_comment_lexer.lex("start", "/* hello */ 42"))
    assert len(tokens) == 1
    assert isinstance(tokens[0], NUM_A)
    assert tokens[0].value == 42


def test_block_comment_between_tokens() -> None:
    """Tokens before and after a block comment are both captured."""
    tokens = list(block_comment_lexer.lex("start", "1 /* skip */ 2"))
    assert len(tokens) == 2
    assert isinstance(tokens[0], NUM_A) and tokens[0].value == 1
    assert isinstance(tokens[1], NUM_A) and tokens[1].value == 2


def test_block_comment_multiline_advances_lineno() -> None:
    """A comment spanning two lines gives the token after it lineno=2."""
    tokens = list(block_comment_lexer.lex("start", "/* line1\nline2 */ 99"))
    assert len(tokens) == 1
    assert isinstance(tokens[0], NUM_A)
    assert tokens[0].lineno == 2


def test_block_comment_unclosed_silently_ends() -> None:
    """An unclosed /* reaches EOF without raising — the lexer exits regardless of state.

    The Lexer has no concept of a "required end state", so EOF in the middle of
    a comment simply terminates tokenisation.  Only the token before the comment
    is emitted.
    """
    tokens = list(block_comment_lexer.lex("start", "1 /* unclosed"))
    assert len(tokens) == 1
    assert isinstance(tokens[0], NUM_A) and tokens[0].value == 1


def test_block_comment_adjacent_to_token() -> None:
    """A comment immediately adjacent (no space) to a number is handled correctly."""
    tokens = list(block_comment_lexer.lex("start", "/*x*/7"))
    assert len(tokens) == 1
    assert isinstance(tokens[0], NUM_A) and tokens[0].value == 7


# ---------------------------------------------------------------------------
# Section 3: String-literal state machine
# ---------------------------------------------------------------------------


class STR(Token):
    def __init__(self, value: str, *, lineno: int, offset: int) -> None:
        super().__init__(value, lineno=lineno, offset=offset)
        self.content = value


def make_str(matched: str, state: None, lineno: int, offset: int) -> STR:
    return STR(matched[1:-1], lineno=lineno, offset=offset)


str_lexer: Lexer[None] = Lexer(
    {
        "start": [
            (r"[ \t]+", "start"),
            (r'"[^"]*"', make_str),
        ]
    }
)


def test_string_literal_single() -> None:
    """A double-quoted string produces a single STR token with inner content."""
    tokens = list(str_lexer.lex("start", '"hello world"'))
    assert len(tokens) == 1
    assert isinstance(tokens[0], STR)
    assert tokens[0].content == "hello world"


def test_string_literal_multiple() -> None:
    """Two adjacent strings produce two separate STR tokens."""
    tokens = list(str_lexer.lex("start", '"foo" "bar"'))
    assert len(tokens) == 2
    assert isinstance(tokens[0], STR) and tokens[0].content == "foo"
    assert isinstance(tokens[1], STR) and tokens[1].content == "bar"


def test_string_literal_offset() -> None:
    """The STR token's offset points to the opening quote character."""
    tokens = list(str_lexer.lex("start", '   "hi"'))
    assert len(tokens) == 1
    assert tokens[0].offset == 3


def test_string_literal_empty() -> None:
    """An empty string literal produces a STR token with content == ''."""
    tokens = list(str_lexer.lex("start", '""'))
    assert len(tokens) == 1
    assert isinstance(tokens[0], STR)
    assert tokens[0].content == ""


# ---------------------------------------------------------------------------
# Section 4: user_state threading
# ---------------------------------------------------------------------------


@dataclass
class Counter:
    count: int = 0


class TOK_US(Token):
    pass


def test_user_state_is_threaded() -> None:
    """A callable handler receives and mutates the user state across all calls."""
    counter = Counter()

    def handler(matched: str, state: Counter, lineno: int, offset: int) -> TOK_US:
        state.count += 1
        return TOK_US(matched, lineno=lineno, offset=offset)

    lexer: Lexer[Counter] = Lexer(
        {"start": [(r"\w+", handler), (r" +", "start")]},
        state_factory=lambda: counter,
    )
    tokens = list(lexer.lex("start", "a b c"))
    assert len(tokens) == 3
    assert counter.count == 3


def test_user_state_factory_called_per_lex() -> None:
    """state_factory is called once per lex() invocation, not per token."""
    call_count = 0

    def factory() -> None:
        nonlocal call_count
        call_count += 1

    lexer: Lexer[None] = Lexer(
        {"start": [(r"\w+", WORD), (r" +", "start")]},
        state_factory=factory,
    )
    list(lexer.lex("start", "a b"))
    list(lexer.lex("start", "c d"))
    assert call_count == 2


# ---------------------------------------------------------------------------
# Section 5: Edge cases
# ---------------------------------------------------------------------------


def test_empty_input_produces_no_tokens() -> None:
    """An empty string yields no tokens."""
    lexer: Lexer[None] = Lexer({"start": [(r"\d+", NUM_A)]})
    tokens = list(lexer.lex("start", ""))
    assert tokens == []


def test_single_char_token_position() -> None:
    """A single-character token has lineno=1 and offset=0."""

    class PLUS_EC(Token):
        pass

    lexer: Lexer[NoneType] = Lexer({"start": [(r"\+", PLUS_EC)]}, NoneType)
    tokens = list(lexer.lex("start", "+"))
    assert len(tokens) == 1
    assert tokens[0].lineno == 1
    assert tokens[0].offset == 0


def test_lex_error_reports_correct_position() -> None:
    """LexingError carries the correct lineno and offset of the unrecognised character."""
    with pytest.raises(LexingError) as exc_info:
        list(word_lexer.lex("start", "aa\nbb\n@"))
    err = exc_info.value
    assert err.lineno == 3
    assert err.offset == 0


def test_lex_error_mid_line_offset() -> None:
    """LexingError offset matches the column of the bad character within its line."""
    with pytest.raises(LexingError) as exc_info:
        list(word_lexer.lex("start", "abc @"))
    err = exc_info.value
    assert err.lineno == 1
    assert err.offset == 4


def test_multiple_tokens_same_line() -> None:
    """Several tokens on one line have monotonically increasing offsets."""
    tokens = list(word_lexer.lex("start", "ab cd ef"))
    assert len(tokens) == 3
    assert tokens[0].offset < tokens[1].offset < tokens[2].offset
    assert tokens[0].lineno == tokens[1].lineno == tokens[2].lineno == 1
