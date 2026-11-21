"""The store: the part of Tollgate that keeps its state on your machine.

The driver, the gate, and the skills reach the state folder only through this
class. Every method names one step. UNFINISHED: each method is a stub until
the store stream builds it.
"""

from gate import state


class StoreError(RuntimeError):
    """A step of the store failed. The message says why."""


class Store:
    def __init__(self, project: str):
        self.project = project
        self.dir = state.state_dir(project)

    # Locks
    def freeze(self, ticket: str) -> str:
        """Run the ticket's tests in a clean copy with main's harness; none may pass.
        Write and sign locks/<ticket>.json. Return the lock's path."""
        raise NotImplementedError

    def lock_plan(self, task: str) -> str:
        """Sign the approved plan of a task into plans/<task>.json. Return its path."""
        raise NotImplementedError

    # Questions for you
    def ask(self, title: str, body: str) -> int:
        """Write questions/<n>.json. Return n."""
        raise NotImplementedError

    def answer(self, n: int, body: str) -> None:
        """Record your answer to question n."""
        raise NotImplementedError

    def open_questions(self) -> dict:
        """Return {n: question} for each question with no answer."""
        raise NotImplementedError

    def close_question(self, n: int) -> None:
        raise NotImplementedError

    # Ready changes, passes, approvals, merges
    def ready(self, branch: str, ticket: str) -> None:
        """Mark a branch as a ready change: it passed the gate and waits to merge."""
        raise NotImplementedError

    def record_pass(self, commit: str, record: dict) -> None:
        """Write and sign passes/<commit>.json."""
        raise NotImplementedError

    def passed(self, commit: str) -> dict | None:
        """The verified pass record of a commit, or None."""
        raise NotImplementedError

    def approvals(self, commit: str) -> list:
        """The verified approvals of a commit."""
        raise NotImplementedError

    def merge(self, commit: str) -> str:
        """Merge a ready change into main with a merge commit (--no-ff). Refuse without
        a valid pass record, and for tier 3 and 4 without an approval. Return the merge commit."""
        raise NotImplementedError
