import logging
import os
from typing import override

from rich.console import Console
from rich.logging import RichHandler
from rich.text import Text

console = Console()


class CustomHandler(RichHandler):
    @override
    def get_level_text(self, record: logging.LogRecord) -> Text:
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
