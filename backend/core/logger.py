"""
ClinScribe AI - Centralised Logging
====================================
Usage in any module:
    from core.logger import get_logger
    log = get_logger(__name__)

    log.info("Something happened")
    log.warning("Watch out: %s", msg)
    log.error("Failed to do X", exc_info=True)

Log files are written to  backend/logs/clinscribe.log
with automatic daily rotation and 7-day retention.
"""

import json
import logging
import logging.handlers
import sys
from datetime import datetime, timezone
from pathlib import Path

# ── paths ──────────────────────────────────────────────────────────────────────
LOG_DIR = Path(__file__).parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "clinscribe.log"

# ── log levels ─────────────────────────────────────────────────────────────────
CONSOLE_LEVEL = logging.DEBUG
FILE_LEVEL = logging.DEBUG


# ── JSON formatter for the file handler ───────────────────────────────────────
class JsonFormatter(logging.Formatter):
    """
    Emits one JSON object per line so log files can be ingested by log
    aggregators (e.g. Datadog, ELK, Loki) without further parsing.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload: dict = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "func": record.funcName,
            "line": record.lineno,
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack"] = self.formatStack(record.stack_info)
        # Any extra kwargs passed via log.xxx(..., extra={"key": "val"})
        for key, val in record.__dict__.items():
            if key not in logging.LogRecord.__dict__ and not key.startswith("_"):
                try:
                    json.dumps(val)          # only include JSON-serialisable extras
                    payload[key] = val
                except (TypeError, ValueError):
                    payload[key] = repr(val)
        return json.dumps(payload, ensure_ascii=False)


# ── Coloured formatter for the console ────────────────────────────────────────
_COLOURS = {
    "DEBUG":    "\033[36m",   # cyan
    "INFO":     "\033[32m",   # green
    "WARNING":  "\033[33m",   # yellow
    "ERROR":    "\033[31m",   # red
    "CRITICAL": "\033[35m",   # magenta
}
_RESET = "\033[0m"


class ColourFormatter(logging.Formatter):
    FMT = "{colour}[{level:<8}]{reset} {ts}  {logger:<30}  {msg}"

    def format(self, record: logging.LogRecord) -> str:
        colour = _COLOURS.get(record.levelname, "")
        ts = datetime.fromtimestamp(record.created).strftime("%H:%M:%S")
        base = self.FMT.format(
            colour=colour,
            level=record.levelname,
            reset=_RESET,
            ts=ts,
            logger=record.name,
            msg=record.getMessage(),
        )
        if record.exc_info:
            base += "\n" + colour + self.formatException(record.exc_info) + _RESET
        return base


# ── Root logger setup (called once on import) ─────────────────────────────────
def _setup() -> None:
    root = logging.getLogger("clinscribe")
    if root.handlers:           # already configured (e.g. reloaded by uvicorn)
        return

    root.setLevel(logging.DEBUG)

    # 1. Console handler
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(CONSOLE_LEVEL)
    ch.setFormatter(ColourFormatter())
    root.addHandler(ch)

    # 2. Rotating file handler -- new file each day, keep 7 days
    fh = logging.handlers.TimedRotatingFileHandler(
        LOG_FILE,
        when="midnight",
        interval=1,
        backupCount=7,
        encoding="utf-8",
        utc=True,
    )
    fh.setLevel(FILE_LEVEL)
    fh.setFormatter(JsonFormatter())
    fh.suffix = "%Y-%m-%d"
    root.addHandler(fh)

    root.propagate = False


_setup()


def get_logger(name: str) -> logging.Logger:
    """
    Return a child logger under the 'clinscribe' namespace.

    Example:
        log = get_logger(__name__)
    """
    if not name.startswith("clinscribe"):
        name = f"clinscribe.{name}"
    return logging.getLogger(name)
