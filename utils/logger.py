"""
Logging Configuration
======================
Structured JSON logging for production.
Falls back to coloured console logging in development.
"""

import os
import logging
import sys
from datetime import datetime


LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_FORMAT = os.getenv("LOG_FORMAT", "console")   # "console" | "json"


class ColourFormatter(logging.Formatter):
    """Coloured log output for local development."""
    COLOURS = {
        "DEBUG":    "\033[36m",   # cyan
        "INFO":     "\033[32m",   # green
        "WARNING":  "\033[33m",   # yellow
        "ERROR":    "\033[31m",   # red
        "CRITICAL": "\033[35m",   # magenta
    }
    RESET = "\033[0m"

    def format(self, record):
        colour = self.COLOURS.get(record.levelname, "")
        record.levelname = f"{colour}{record.levelname:8s}{self.RESET}"
        return super().format(record)


class JSONFormatter(logging.Formatter):
    """Structured JSON logs for production / log aggregators."""
    def format(self, record):
        import json
        log = {
            "ts":      datetime.utcnow().isoformat() + "Z",
            "level":   record.levelname,
            "logger":  record.name,
            "msg":     record.getMessage(),
        }
        if record.exc_info:
            log["exc"] = self.formatException(record.exc_info)
        return json.dumps(log, ensure_ascii=False)


def setup_logging():
    root = logging.getLogger()
    root.setLevel(LOG_LEVEL)

    handler = logging.StreamHandler(sys.stdout)

    if LOG_FORMAT == "json":
        handler.setFormatter(JSONFormatter())
    else:
        fmt = "%(asctime)s %(levelname)s %(name)s │ %(message)s"
        handler.setFormatter(ColourFormatter(fmt=fmt, datefmt="%H:%M:%S"))

    root.handlers.clear()
    root.addHandler(handler)

    # Quieten noisy libraries
    for noisy in ("pymongo", "motor", "httpx", "sentence_transformers", "transformers"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    return root


logger = setup_logging()
