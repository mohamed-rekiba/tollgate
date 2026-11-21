"""Locked tests for the ticket freeze-probe-test."""

import unittest
from unittest import mock

from action.manifest import FreezeError
from driver import server as srv
from setup.gh import GhError


class FakeGh:
    def __init__(self, failed_title):
        self.failed_title = failed_title

    def api(self, method, path, body=None):
        return {}

    def get(self, path):
        if "matching-refs" in path:
            raise GhError(404, "no tags")
        if "/runs?" in path:
            return {"workflow_runs": [{
                "display_title": self.failed_title, "status": "completed",
                "conclusion": "failure", "created_at": "2999-01-01T00:00:00Z",
                "html_url": "https://github.com/o/r/actions/runs/9"}]}
        return {}


class FreezeProbe(unittest.TestCase):
    def github(self, failed_title):
        return srv.GitHub("o/r", gh=FakeGh(failed_title), sleep=lambda s: None)

    def test_c1_a_failed_run_of_the_same_ticket_stops_the_wait(self):
        with self.assertRaises(FreezeError):
            self.github("tollgate freeze T-1").freeze("T-1")

    def test_c2_a_failed_run_of_another_ticket_does_not_stop_the_wait(self):
        with mock.patch.object(srv, "WAIT_SECONDS", 15), self.assertRaises(TimeoutError):
            self.github("tollgate freeze T-2").freeze("T-1")
