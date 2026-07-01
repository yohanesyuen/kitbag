# kitbag

A personal grab-bag of reusable utilities. Grows as needed — the first module is
structured JSON logging shipped to [VictoriaLogs](https://docs.victoriametrics.com/victorialogs/).

DISCLAIMER: PARTS OF THIS REPOSITORY WERE WRITTEN WITH AI ASSISTANCE. USE AT YOUR OWN DISCRETION.

## Install

```bash
pip install -e .
```

## Usage

```python
from kitbag import init_logging

log = init_logging("my-app")  # defaults to VictoriaLogs on http://127.0.0.1:9428
log.info("something happened", extra={"key": "value"})
```

Logging never blocks the caller and never raises — if the log sink is
unreachable, the log line is silently dropped rather than crashing the app.
