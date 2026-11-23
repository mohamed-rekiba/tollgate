"""The log: one JSON line for each event, one writer for each file.

In session mode each `driver.step next` runs the driver again from where its log
says it stands, and the part of the step it repeats, up to the role that just
answered, logs the same events again. A log in replay mode writes none of them:
it holds each event back while the events of this run match the end of the log,
and drops them once they reach it. The first event that does not match ends the
replay, and from then on each event is written. Only what really happened is in
the log, so whatever counts its events counts each one once.
"""

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
        self._prior = None      # in replay mode: the events already logged, without "at"
        self._held = []

    def replay(self) -> None:
        """Replay mode: an event this run repeats from the end of the log is not written."""
        self._prior = [_bare(e) for e in read(self.path)]
        self._held = []

    def replaying(self) -> bool:
        return self._prior is not None

    def add(self, event: str, **fields) -> dict:
        line = {"at": now(), **self.fixed, "event": event, **fields}
        if self._prior is None:
            self._write(line)
            return line
        held = [*self._held, line]
        bare = [_bare(json.loads(json.dumps(e))) for e in held]
        n, prior = len(bare), self._prior
        if prior[len(prior) - n:] == bare:
            # The run has caught up with the end of the log: every event after this is new.
            self._prior, self._held = None, []
        elif any(prior[p:p + n] == bare for p in range(len(prior) - n)):
            self._held = held
        else:
            self._prior, self._held = None, []
            for e in held:
                self._write(e)
        return line

    def _write(self, line: dict) -> None:
        self._file.write(json.dumps(line, sort_keys=False) + "\n")
        self._file.flush()
        os.fsync(self._file.fileno())

    def close(self):
        # Events still held back match events already in the log, so they are not written.
        if not self._file.closed:
            fcntl.flock(self._file, fcntl.LOCK_UN)
            self._file.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def _bare(event: dict) -> dict:
    return {k: v for k, v in event.items() if k != "at"}


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
