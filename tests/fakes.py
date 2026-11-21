"""A sample project with its own state folder and key, and the driver's server done
with the real store. Only the AI roles are fake: see fake_role.py."""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from gate import manifest as mf
from gate.store import Store, StoreError
from tests.helpers import sh

FAKE_ROLE = str(Path(__file__).resolve().parent / "fake_role.py")
GOOD_RUN = {"path": ".github/workflows/tollgate.yml", "head_branch": "main",
            "event": "workflow_dispatch", "conclusion": "success"}

RUN_TESTS = '''"""Run the tests with unittest and write a JUnit report."""
import sys
import unittest
from xml.sax.saxutils import quoteattr

suite = unittest.defaultTestLoader.discover("tests", top_level_dir=".")
cases = []


def walk(s):
    for t in s:
        if isinstance(t, unittest.TestSuite):
            walk(t)
        else:
            cases.append(t)


walk(suite)
out, failed = [], 0
for case in cases:
    r = unittest.TestResult()
    case.run(r)
    cls = type(case).__module__
    name = case._testMethodName
    bad = r.failures or r.errors
    failed += bool(bad)
    inner = "<failure/>" if bad else ("<skipped/>" if r.skipped else "")
    out.append(f"<testcase classname={quoteattr(cls)} name={quoteattr(name)}>{inner}</testcase>")
open("report.xml", "w").write("<testsuites><testsuite>" + "".join(out) + "</testsuite></testsuites>")
sys.exit(1 if failed else 0)
'''

TICKET = """---
id: T-1
plan: demo
seams: app.shout
tests: tests/test_t1.py
---
## Current behavior
There is no shout.

## Desired behavior
shout returns the greeting in capitals.

## Checklist
- [C1, must] shout("ann") returns "HELLO ANN".
- [C2, must, keeps behavior] greet("ann") still returns "hello ann".
- [C3] shout has a docstring.

## Out of scope
Other languages.
"""


def settings(builder="pass2", reviewer="ok", advisor=("person",), image="", extra=None,
             signers=(), **stop):
    """With an image, every role runs in a container from that image, and the fake
    role is the copy of fake_role.py that the sample project holds."""
    py = sys.executable
    role = f"{py} {FAKE_ROLE}"
    if image:
        role = "python3 fake_role.py"
    return {
        "checks": {"tests": {"run": f"{py} run_tests.py", "report": "report.xml"}},
        "harness": ["run_tests.py"],
        "require_plan": False,
        "signers": list(signers),
        "approvers": ["owner"],
        "sandbox": "container" if image else "none",
        "container_image": image,
        "ai": {"builder": f"{role} {builder}",
               "reviewer": f"{role} {reviewer}",
               "advisor": list(advisor)},
        "stop": {"attempts": 3, "attempt_minutes": 1, "ticket_usd": 10, "task_usd": 60, **stop},
        **(extra or {}),
    }


class Sample:
    """A bare repository as the server, and a clone of it as the project."""

    def __init__(self, **settings_args):
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        self.bare = root / "server.git"
        self.project = root / "project"
        sh(root, "git", "init", "-q", "--bare", "-b", "main", str(self.bare))
        sh(root, "git", "clone", "-q", str(self.bare), str(self.project))
        p = self.project
        for k, v in (("user.email", "t@example.com"), ("user.name", "Test"),
                     ("commit.gpgsign", "false"), ("tag.gpgsign", "false")):
            sh(p, "git", "config", k, v)
        (p / "app.py").write_text('def greet(name):\n    return f"hello {name}"\n')
        (p / "run_tests.py").write_text(RUN_TESTS)
        if settings_args.get("image"):
            (p / "fake_role.py").write_text(Path(FAKE_ROLE).read_text())
        (p / "tests").mkdir()
        (p / "tests/__init__.py").write_text("")
        (p / ".gitignore").write_text(".tollgate/logs/\n.tollgate/work/\n.tollgate/run/\n"
                                      "report.xml\n__pycache__/\n")
        (p / ".tollgate").mkdir()
        # The sample's own state folder and key, so a test never touches yours.
        self.state, self.keys = root / "state", root / "keys"
        self.keys.mkdir(mode=0o700)
        sh(root, "ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", "tollgate",
           "-f", str(self.keys / "id_ed25519"))
        pub = (self.keys / "id_ed25519.pub").read_text().strip()
        settings_args.setdefault("signers", [pub])
        (p / ".tollgate/settings.json").write_text(json.dumps(settings(**settings_args)))
        sh(p, "git", "add", "-A")
        sh(p, "git", "commit", "-q", "-m", "sample")
        sh(p, "git", "push", "-q", "origin", "main")
        (p / ".tollgate/tickets/T-1").mkdir(parents=True)
        (p / ".tollgate/tickets/T-1/ticket.md").write_text(TICKET)
        # Every git command in the copy needs an identity.
        self.env_home = root / "home"
        self.env_home.mkdir()
        (self.env_home / ".gitconfig").write_text(
            "[user]\n\temail = t@example.com\n\tname = Test\n"
            "[commit]\n\tgpgsign = false\n[tag]\n\tgpgsign = false\n")

    def close(self):
        self._tmp.cleanup()


class LocalServer:
    """What the driver asks of its server, done with the real store.

    Only the steps the store does not have stay fake: pull requests and runs.
    UNFINISHED: those go when the driver calls the store itself.
    """

    def __init__(self, bare: Path):
        self.bare = bare
        self.store = Store(str(bare))
        self.prs = []
        self.merged = []
        self.freezes = 0

    def freeze(self, ticket: str) -> str:
        try:
            path = self.store.freeze(ticket)
        except StoreError as err:
            raise mf.FreezeError(str(err)) from None
        self.freezes += 1
        return path

    def lock_plan(self, task: str) -> str:
        return self.store.lock_plan(task)

    def ask(self, title, body):
        return self.store.ask(title, body)

    def answer(self, issue, body, user="owner", user_type="User"):
        self.store.answer(int(issue), body)

    def issue_comments(self, issue):
        """The answer as the one comment the advisor reads today."""
        found = (self.store.question(int(issue)) or {}).get("answer")
        if not found:
            return []
        return [{"user": "owner", "user_type": "User",
                 "body": f"tollgate decide {found['decision']} {found['hint']}".strip()}]

    def close_question(self, issue):
        self.store.close_question(int(issue))

    def open_questions(self) -> dict:
        return self.store.open_questions()

    # Fakes until the driver calls the store.
    def run(self, run_id):
        return dict(GOOD_RUN, title="", manifest=None)

    def pull(self, pr):
        return {"author": "owner", "head": ""}

    def approvals(self, pr):
        return []

    def check_passed(self, sha, name):
        return None

    def open_pr(self, branch, title, body):
        self.prs.append({"branch": branch, "title": title, "body": body})
        return len(self.prs)

    def merge(self, pr):
        self.merged.append(pr)


def driver_env(sample: Sample) -> dict:
    import os
    env = dict(os.environ)
    env["HOME"] = str(sample.env_home)
    env["GIT_CONFIG_GLOBAL"] = str(sample.env_home / ".gitconfig")
    env["TOLLGATE_STATE"] = str(sample.state)
    env["TOLLGATE_KEYS"] = str(sample.keys)
    return env


def run_driver(sample: Sample, ticket="T-1") -> subprocess.CompletedProcess:
    """Run the driver as its own process with the local server."""
    code = ("import sys; from driver.driver import main; from tests.fakes import LocalServer; "
            "from pathlib import Path; "
            f"sys.exit(main(['--project', {str(sample.project)!r}, '--ticket', {ticket!r}], "
            f"server=LocalServer(Path({str(sample.bare)!r}))))")
    root = Path(__file__).resolve().parent.parent
    env = driver_env(sample)
    env["PYTHONPATH"] = str(root)
    return subprocess.run([sys.executable, "-c", code], cwd=root, env=env,
                          capture_output=True, text=True, timeout=300, check=False)


def run_task(sample: Sample, task="demo", request="Add shout and whisper.",
             extra_env: dict | None = None) -> subprocess.CompletedProcess:
    """Run the task loop as its own process with the local server."""
    code = ("import sys; from driver.task import main; from tests.fakes import LocalServer; "
            "from pathlib import Path; "
            f"sys.exit(main(['--project', {str(sample.project)!r}, '--task', {task!r}, "
            f"'--request', {request!r}], server=LocalServer(Path({str(sample.bare)!r}))))")
    root = Path(__file__).resolve().parent.parent
    env = driver_env(sample)
    env["PYTHONPATH"] = str(root)
    env.update(extra_env or {})
    return subprocess.run([sys.executable, "-c", code], cwd=root, env=env,
                          capture_output=True, text=True, timeout=600, check=False)
