"""Plare — a Python lexer/parser framework.

Public API
----------
* ``Lexer`` (:mod:`plare.lexer`) — regex-driven stateful tokeniser.
* ``Parser`` (:mod:`plare.parser`) — LALR(1) parser with operator-precedence
  conflict resolution.
* ``Token`` (:mod:`plare.token`) — base class for all terminal symbols.
* ``PlareException``, ``LexingError``, ``ParserError``, ``ParsingError``
  (:mod:`plare.exception`) — exception hierarchy.

See ``examples/calc/calc.py`` and ``examples/sum_of_list/sum.py`` for
end-to-end usage examples.
"""

__version__ = "1.6.0"
