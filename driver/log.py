"""The log: one JSON line for each event, one writer for each file.

A log in session mode holds its events while the run replays what an earlier run
of `driver.step next` already logged, and writes only those the file does not
have: see driver/session.py.
"""

import fcntl
import json
import os
from collections import Counter
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
        self.quiet = None
        self._held = []

    def hold_while(self, quiet) -> None:
        """Session mode: hold each event while quiet() is true, the replay of a step.
        A held event is written once quiet() ends, or when the log closes, unless the
        file already has it. So a replay that never reaches the step it waits for,
        because the path changed, loses no event and writes none twice."""
        self.quiet = quiet
        self._held = []

    def add(self, event: str, **fields) -> dict:
        line = {"at": now(), **self.fixed, "event": event, **fields}
        if self.quiet is not None and self.quiet():
            self._held.append(line)
            return line
        self._write_held()
        self._write(line)
        return line

    def _write(self, line: dict) -> None:
        self._file.write(json.dumps(line, sort_keys=False) + "\n")
        self._file.flush()
        os.fsync(self._file.fileno())

    def _write_held(self) -> None:
        """Write each held event that the file does not have yet. Events are compared
        without their time, and each line of the file matches one held event at most."""
        if not self._held:
            return
        held, self._held = self._held, []
        logged = Counter(_same(e) for e in read(self.path))
        for line in held:
            found = _same(line)
            if logged[found]:
                logged[found] -= 1
                continue
            self._write(line)

    def close(self):
        if not self._file.closed:
            self._write_held()
            fcntl.flock(self._file, fcntl.LOCK_UN)
            self._file.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def _same(event: dict) -> str:
    """An event as text without its time: two runs that log the same fact give the same."""
    return json.dumps({k: v for k, v in event.items() if k != "at"}, sort_keys=True)


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
