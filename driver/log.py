"""The log: one JSON line for each event, one writer for each file."""

import fcntl
import json
import os
from datetime import UTC, datetime


class LogBusy(RuntimeError):
    pass


def now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class Log:
    """The writer of one log file. It holds an exclusive lock until it closes."""

    def __init__(self, path: str, **fixed):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self.path = path
        self.fixed = fixed
        self._file = open(path, "a")  # noqa: SIM115 - held open for the lock
        try:
            fcntl.flock(self._file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self._file.close()
            raise LogBusy(f"another writer holds {path}") from None

    def add(self, event: str, **fields) -> dict:
        line = {"at": now(), **self.fixed, "event": event, **fields}
        self._file.write(json.dumps(line, sort_keys=False) + "\n")
        self._file.flush()
        os.fsync(self._file.fileno())
        return line

    def close(self):
        if not self._file.closed:
            fcntl.flock(self._file, fcntl.LOCK_UN)
            self._file.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def read(path: str) -> list:
    """Return the events in the order they were added. A torn last line is dropped."""
    if not os.path.exists(path):
        return []
    events = []
    with open(path) as f:
        for line in f:
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return events
