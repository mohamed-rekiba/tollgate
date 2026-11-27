"""Two real processes at once against Tollgate's locks.

Each test starts separate processes with multiprocessing and lines them up with a
barrier or an event, so that they truly overlap. No test sleeps to wait for
another process.
"""

import json
import multiprocessing
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.helpers import within

CTX = multiprocessing.get_context("fork")
WAIT = 20  # seconds: the most a process waits for another before the test fails


def _start(target, *args):
    proc = CTX.Process(target=target, args=args)
    proc.start()
    return proc


def _join(procs):
    for proc in procs:
        proc.join(WAIT)
        if proc.is_alive():
            proc.kill()
            raise AssertionError("a process did not end")


def _results(queue, n):
    return [queue.get(timeout=WAIT) for _ in range(n)]


def _dead_pid() -> int:
    done = subprocess.run([sys.executable, "-c", "import os; print(os.getpid())"],
                          capture_output=True, text=True, check=True)
    return int(done.stdout)


# The run lock.

def _take_and_hold(path, barrier, results, release):
    from driver.driver import Busy, TicketLock
    lock = TicketLock(path)
    barrier.wait(WAIT)
    try:
        lock.acquire()
    except Busy:
        results.put("busy")
        return
    results.put("got")
    release.wait(WAIT)
    lock.release()


def _take_once(path, results):
    from driver.driver import Busy, TicketLock
    lock = TicketLock(path)
    try:
        lock.acquire()
    except Busy:
        results.put("busy")
        return
    results.put("got")
    lock.release()


def _take_slowly(path, started, go_on, results):
    """Take the lock, but stop at its first write, before the lock is whole."""
    from driver import driver
    real = os.write

    def write(fd, data):
        started.set()
        go_on.wait(WAIT)
        return real(fd, data)

    with mock.patch.object(driver.os, "write", write):
        try:
            driver.TicketLock(path).acquire()
            found = "got"
        except driver.Busy:
            found = "busy"
    results.put(found)


def _take_after_stale_check(path, checked, go_on, results):
    """Take the lock, but stop once it has found the holder dead."""
    from driver import driver
    real = driver._alive

    def alive(pid):
        found = real(pid)
        checked.set()
        go_on.wait(WAIT)
        return found

    with mock.patch.object(driver, "_alive", alive):
        try:
            driver.TicketLock(path).acquire()
            found = "got"
        except driver.Busy:
            found = "busy"
    results.put(found)


class RunLockTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = str(Path(tmp.name, "run", "task-demo.lock"))

    def test_one_of_eight_processes_gets_the_lock_and_the_rest_are_busy(self):
        with within(10):
            barrier, results, release = CTX.Barrier(8), CTX.Queue(), CTX.Event()
            procs = [_start(_take_and_hold, self.path, barrier, results, release)
                     for _ in range(8)]
            found = _results(results, 8)
            release.set()
            _join(procs)
            self.assertEqual(sorted(found), ["busy"] * 7 + ["got"])
            self.assertFalse(Path(self.path).exists())
            results = CTX.Queue()
            _join([_start(_take_once, self.path, results)])
            self.assertEqual(results.get(timeout=WAIT), "got")

    def test_a_lock_left_by_a_dead_process_is_taken_by_exactly_one_of_eight(self):
        with within(10):
            Path(self.path).parent.mkdir(parents=True)
            Path(self.path).write_text(str(_dead_pid()))
            barrier, results, release = CTX.Barrier(8), CTX.Queue(), CTX.Event()
            procs = [_start(_take_and_hold, self.path, barrier, results, release)
                     for _ in range(8)]
            found = _results(results, 8)
            release.set()
            _join(procs)
            self.assertEqual(sorted(found), ["busy"] * 7 + ["got"])

    def test_a_lock_being_taken_is_never_taken_by_a_second_process_too(self):
        with within(10):
            started, go_on, results = CTX.Event(), CTX.Event(), CTX.Queue()
            first = _start(_take_slowly, self.path, started, go_on, results)
            self.assertTrue(started.wait(WAIT))
            # While the first stops in the middle of taking it, a second takes and holds it.
            hold, release = CTX.Queue(), CTX.Event()
            second = _start(_take_and_hold, self.path, CTX.Barrier(1), hold, release)
            got = hold.get(timeout=WAIT)
            go_on.set()
            found = results.get(timeout=WAIT)
            release.set()
            _join([first, second])
            self.assertEqual(sorted([got, found]), ["busy", "got"])

    def test_two_processes_that_find_the_same_dead_holder_do_not_both_get_the_lock(self):
        with within(10):
            Path(self.path).parent.mkdir(parents=True)
            Path(self.path).write_text(str(_dead_pid()))
            checked, go_on, results = CTX.Event(), CTX.Event(), CTX.Queue()
            first = _start(_take_after_stale_check, self.path, checked, go_on, results)
            self.assertTrue(checked.wait(WAIT))
            # While the first stops, a second takes the stale lock and holds it.
            hold, release = CTX.Queue(), CTX.Event()
            second = _start(_take_and_hold, self.path, CTX.Barrier(1), hold, release)
            got = hold.get(timeout=WAIT)
            go_on.set()
            found = results.get(timeout=WAIT)
            release.set()
            _join([first, second])
            self.assertEqual(sorted([got, found]), ["busy", "got"])


# The log.

def _append(path, name, barrier, n):
    from driver.log import Log, LogBusy
    barrier.wait(WAIT)
    for i in range(n):
        while True:
            try:
                log = Log(path, writer=name)
            except LogBusy:
                continue
            with log:
                log.add("line", n=i, pad="x" * 200)
            break


def _hold_log(path, held, release):
    from driver.log import Log
    with Log(path, writer="holder") as log:
        log.add("line", n=0)
        held.set()
        release.wait(WAIT)


def _write_once(path, results):
    from driver.log import Log, LogBusy
    try:
        with Log(path, writer="second") as log:
            log.add("line", n=0)
    except LogBusy:
        results.put("busy")
        return
    results.put("wrote")


class LogTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = str(Path(tmp.name, "logs", "T-1.jsonl"))

    def test_two_processes_that_append_at_once_lose_and_tear_no_line(self):
        with within(10):
            barrier = CTX.Barrier(2)
            _join([_start(_append, self.path, name, barrier, 200) for name in ("a", "b")])
            lines = Path(self.path).read_text().splitlines()
            self.assertEqual(len(lines), 400)
            events = [json.loads(line) for line in lines]
            for name in ("a", "b"):
                self.assertEqual([e["n"] for e in events if e["writer"] == name],
                                 list(range(200)))

    def test_a_second_process_cannot_write_a_log_another_holds(self):
        with within(10):
            held, release, results = CTX.Event(), CTX.Event(), CTX.Queue()
            holder = _start(_hold_log, self.path, held, release)
            self.assertTrue(held.wait(WAIT))
            _join([_start(_write_once, self.path, results)])
            release.set()
            _join([holder])
            self.assertEqual(results.get(timeout=WAIT), "busy")
            from driver.log import read
            self.assertEqual([e["writer"] for e in read(self.path)], ["holder"])


# driver.step next.

def _next(project, barrier, holding, other_done, results):
    from driver import roles, step
    from tests.driver_fakes import FakeStore
    real = roles.make_copy

    def make_copy(*args, **kw):
        # Called under the task's run lock: hold it until the other next has ended.
        holding.set()
        other_done.wait(WAIT)
        return real(*args, **kw)

    with mock.patch.object(roles, "make_copy", make_copy):
        barrier.wait(WAIT)
        out, code = step.next_step(project, "demo", FakeStore(project))
    if code:
        other_done.set()
    results.put((code, out))


class StepNextTest(unittest.TestCase):
    def test_two_nexts_at_once_run_one_and_the_other_is_busy(self):
        from driver import session
        from driver.step import answer
        from tests.driver_fakes import FakeStore, Sample
        from tests.test_session import fake_answer
        with within(10), Sample(ticket=False, runner="session") as s:
            project = str(s.project)
            Path(project, ".tollgate/requests").mkdir(parents=True)
            Path(project, ".tollgate/requests/demo.md").write_text("Add shout and whisper.\n")
            barrier, holding, other_done = CTX.Barrier(2), CTX.Event(), CTX.Event()
            results = CTX.Queue()
            _join([_start(_next, project, barrier, holding, other_done, results)
                   for _ in range(2)])
            found = sorted(_results(results, 2), key=lambda r: r[0])
            (ran_code, ran), (busy_code, busy) = found
            self.assertEqual(ran_code, 0, ran)
            self.assertEqual(ran["agent"], "tollgate:analyst")
            self.assertEqual(busy_code, 1)
            self.assertIn("another driver", busy["error"])
            step = session.read_step(project)
            self.assertEqual(step["key"], ran["key"])
            self.assertEqual(step["nonce_sha256"], session.digest(ran["nonce"]))
            following, code = answer(project, ran["key"], ran["nonce"], fake_answer(ran),
                                     FakeStore(project))
            self.assertEqual(code, 0, following)
            self.assertNotEqual(following["key"], ran["key"])


if __name__ == "__main__":
    unittest.main()
