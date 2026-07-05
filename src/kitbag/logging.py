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

    def __init__(
        self,
        url: str = DEFAULT_VL_URL,
        stream_fields: str | list[str] = "module",
        app: str | None = None,
    ):
        super().__init__()
        self._app = app
        fields = stream_fields if isinstance(stream_fields, str) else ",".join(stream_fields)
        self._insert_url = (
            f"{url}/insert/jsonline"
            f"?_stream_fields={fields}&_time_field=_time&_msg_field=_msg"
        )
        # %(name)s is the logger's dotted name (e.g. "rektbot.plugins.summary") - rename
        # it to "module" in the shipped JSON since "name" reads as a generic/ambiguous key
        # once multiple apps share one VictoriaLogs instance.
        formatter = JsonFormatter(
            "%(asctime)s %(levelname)s %(name)s %(message)s",
            rename_fields={
                "asctime": "_time", "levelname": "level", "message": "_msg", "name": "module",
            },
            datefmt="%Y-%m-%dT%H:%M:%SZ",
        )
        formatter.converter = time.gmtime  # asctime in UTC, not localtime
        self.setFormatter(formatter)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            if self._app is not None:
                record.app = self._app
            line = (self.format(record) + "\n").encode()
            req = urllib.request.Request(
                self._insert_url, data=line, method="POST",
                headers={"Content-Type": "application/stream+json"},
            )
            urllib.request.urlopen(req, timeout=2).close()
        except Exception:
            pass  # best-effort; logging must never take the caller down


def init_logging(
    name: str,
    url: str = DEFAULT_VL_URL,
    level: int = logging.INFO,
    app: str | None = None,
    stream_fields: str | list[str] = "module",
) -> logging.Logger:
    """Return a logger named `name` that ships structured JSON logs to VictoriaLogs.

    `app` tags every shipped record with a static "app" field (e.g. "rektbot") so logs
    from multiple projects sharing one VictoriaLogs instance stay distinguishable. Defaults
    to `name` when omitted.

    `stream_fields` controls which field(s) VictoriaLogs indexes/groups streams by (its
    `_stream_fields` param) - pass a single field name or a list for multi-field grouping,
    e.g. `["app", "module"]` to group by app first. Any field named here must actually be
    present on emitted records (a rename_fields target, or an `extra=` key) or VictoriaLogs
    just won't have anything to group on for it.

    Emission happens on a background thread via a queue, so callers never block
    on the HTTP round trip to the log sink.
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)
    log_queue: queue.Queue = queue.Queue(-1)
    logger.addHandler(logging.handlers.QueueHandler(log_queue))
    listener = logging.handlers.QueueListener(
        log_queue, VictoriaLogsHandler(url, stream_fields=stream_fields, app=app or name)
    )
    listener.start()
    return logger
