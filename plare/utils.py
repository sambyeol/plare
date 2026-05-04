"""Rich-backed logging utilities for the Plare library.

Provides a pre-configured ``logger`` (named ``"plare"``) that writes to the
console via Rich.  The log level is read from the ``LOG_LEVEL`` environment
variable (default: ``"WARNING"``).  Set ``LOG_LEVEL=DEBUG`` to see detailed
traces of lexing, parsing, and table construction.
"""

import logging
import os
from typing import override

from rich.console import Console
from rich.logging import RichHandler
from rich.text import Text

console = Console()


class CustomHandler(RichHandler):
    """Rich logging handler that prepends a bracketed logger name to each record.

    Overrides ``get_level_text`` to prefix the logger's name (truncated to
    three characters plus ``"…"`` if longer than six) before the standard Rich
    level label.  This keeps multi-module output scannable without truncating
    the level indicator.
    """

    @override
    def get_level_text(self, record: logging.LogRecord) -> Text:
        """Return a Rich ``Text`` object combining the logger name and log level."""
        name = record.name if len(record.name) < 7 else f"{record.name[:3]}..."
        name = f"\\[{name}]".ljust(8)
        rv = Text.from_markup(f"[bold]{name}[/] ")
        rv = rv.append_text(super().get_level_text(record))
        return rv


FORMAT = "%(message)s"
DATE_FORMAT = "[%X]"

_log_level = os.environ.get("LOG_LEVEL", "WARNING").upper()

_hander = CustomHandler(
    console=console,
    show_path=_log_level == "DEBUG",
)
_hander.setFormatter(logging.Formatter(fmt=FORMAT, datefmt=DATE_FORMAT))

logger = logging.getLogger("plare")
logger.addHandler(_hander)
logger.setLevel(_log_level)
