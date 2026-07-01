"""Structured JSON logging shipped to VictoriaLogs, off the caller's hot path."""

from __future__ import annotations

import logging
import logging.handlers
import queue
import time
import urllib.request

from pythonjsonlogger.json import JsonFormatter

DEFAULT_VL_URL = "http://127.0.0.1:9428"


class VictoriaLogsHandler(logging.Handler):
    """Ships each formatted JSON log line to VictoriaLogs' /insert/jsonline.

    Never raises: a log call must not be able to break the caller just because
    the log sink is unreachable.
    """

    def __init__(self, url: str = DEFAULT_VL_URL, stream_field: str = "name"):
        super().__init__()
        self._insert_url = (
            f"{url}/insert/jsonline"
            f"?_stream_fields={stream_field}&_time_field=_time&_msg_field=_msg"
        )
        formatter = JsonFormatter(
            "%(asctime)s %(levelname)s %(name)s %(message)s",
            rename_fields={"asctime": "_time", "levelname": "level", "message": "_msg"},
            datefmt="%Y-%m-%dT%H:%M:%SZ",
        )
        formatter.converter = time.gmtime  # asctime in UTC, not localtime
        self.setFormatter(formatter)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            line = (self.format(record) + "\n").encode()
            req = urllib.request.Request(
                self._insert_url, data=line, method="POST",
                headers={"Content-Type": "application/stream+json"},
            )
            urllib.request.urlopen(req, timeout=2).close()
        except Exception:
            pass  # best-effort; logging must never take the caller down


def init_logging(
    name: str, url: str = DEFAULT_VL_URL, level: int = logging.INFO,
) -> logging.Logger:
    """Return a logger named `name` that ships structured JSON logs to VictoriaLogs.

    Emission happens on a background thread via a queue, so callers never block
    on the HTTP round trip to the log sink.
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)
    log_queue: queue.Queue = queue.Queue(-1)
    logger.addHandler(logging.handlers.QueueHandler(log_queue))
    listener = logging.handlers.QueueListener(log_queue, VictoriaLogsHandler(url))
    listener.start()
    return logger
