"""A sample project on a local server, and a fake server that freezes locally."""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from action import checks, freeze, plantag, prepare
from action import manifest as mf
from action import settings as st
from tests.helpers import sh

FAKE_ROLE = str(Path(__file__).resolve().parent / "fake_role.py")
GOOD_RUN = {"path": ".github/workflows/tollgate-freeze.yml", "head_branch": "main",
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


def settings(builder="pass2", reviewer="ok", advisor=("person",), image="", extra=None, **stop):
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
    """The server side, done locally: the freeze runs the same code as the workflow."""

    def __init__(self, bare: Path):
        self.bare = bare
        self.prs = []
        self.merged = []
        self.freezes = 0
        # Runs live next to the bare repository, as GitHub keeps them across driver restarts.
        self.runs_file = Path(bare, "tollgate-runs.json")

    @property
    def runs(self) -> dict:
        return json.loads(self.runs_file.read_text()) if self.runs_file.exists() else {}

    def freeze(self, ticket: str) -> str:
        with tempfile.TemporaryDirectory() as d:
            sh(d, "git", "clone", "-q", str(self.bare), ".")
            sh(d, "git", "checkout", "-q", f"tg/{ticket}")
            commit = sh(d, "git", "rev-parse", "HEAD").strip()
            prepare.restore(d, "origin/main")
            s = st.load_from_ref(d, "origin/main")
            results = checks.run(s, d, ["tests"])
            Path(d, "results.json").write_text(results.to_json())
            run_id = str(len(self.runs) + 1)
            name, message = freeze.message(d, ticket, commit, str(Path(d, "results.json")), run_id)
            self._record(run_id, f"tollgate freeze {ticket}", ".github/workflows/tollgate-freeze.yml",
                         mf.loads(message))
            Path(d, "msg").write_text(message)
            sh(d, "git", "tag", "-a", name, "-F", "msg", commit)
            sh(d, "git", "push", "-q", "origin", f"refs/tags/{name}")
        self.freezes += 1
        return name

    def _record(self, run_id, title, path, manifest):
        runs = self.runs
        runs[run_id] = [title, path, manifest]
        self.runs_file.write_text(json.dumps(runs))

    def run(self, run_id):
        title, path, manifest = self.runs[str(run_id)]
        return dict(GOOD_RUN, title=title, path=path, manifest=manifest)

    def lock_plan(self, task: str) -> str:
        with tempfile.TemporaryDirectory() as d:
            sh(d, "git", "clone", "-q", str(self.bare), ".")
            sh(d, "git", "fetch", "-q", "origin", f"refs/heads/tg-plan/{task}")
            commit = sh(d, "git", "rev-parse", "FETCH_HEAD").strip()
            run_id = str(len(self.runs) + 1)
            name, message = plantag.message(d, task, commit, run_id)
            Path(d, "msg").write_text(message)
            sh(d, "git", "tag", "-a", name, "-F", "msg", commit)
            sh(d, "git", "push", "-q", "origin", f"refs/tags/{name}")
        self._record(run_id, f"tollgate plan {task}", ".github/workflows/tollgate-plan.yml",
                     mf.loads(message))
        return name

    # Questions to a person: kept in a file next to the bare repository.
    @property
    def _questions(self) -> Path:
        return Path(self.bare, "tollgate-questions.json")

    def _load(self) -> dict:
        return json.loads(self._questions.read_text()) if self._questions.exists() else {}

    def ask(self, title, body):
        q = self._load()
        number = len(q) + 1
        q[str(number)] = {"title": title, "body": body, "comments": [], "open": True}
        self._questions.write_text(json.dumps(q))
        return number

    def answer(self, issue, body, user="owner", user_type="User"):
        q = self._load()
        q[str(issue)]["comments"].append({"user": user, "user_type": user_type, "body": body})
        self._questions.write_text(json.dumps(q))

    def issue_comments(self, issue):
        return self._load()[str(issue)]["comments"]

    def close_question(self, issue):
        q = self._load()
        q[str(issue)]["open"] = False
        self._questions.write_text(json.dumps(q))

    def open_questions(self) -> dict:
        return {k: v for k, v in self._load().items() if v["open"]}

    def pull(self, pr):
        return {"author": "owner", "head": ""}

    def approvals(self, pr):
        return []

    def check_passed(self, sha, name):
        return None

    def open_pr(self, branch, title, body):
        self.prs.append({"branch": branch, "title": title, "body": body})
        return len(self.prs)

    def wait_gate(self, sha):
        return "success"

    def merge(self, pr):
        self.merged.append(pr)


def driver_env(sample: Sample) -> dict:
    import os
    env = dict(os.environ)
    env["HOME"] = str(sample.env_home)
    env["GIT_CONFIG_GLOBAL"] = str(sample.env_home / ".gitconfig")
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


def run_task(sample: Sample, task="demo", request="Add shout and whisper.") -> subprocess.CompletedProcess:
    """Run the task loop as its own process with the local server."""
    code = ("import sys; from driver.task import main; from tests.fakes import LocalServer; "
            "from pathlib import Path; "
            f"sys.exit(main(['--project', {str(sample.project)!r}, '--task', {task!r}, "
            f"'--request', {request!r}], server=LocalServer(Path({str(sample.bare)!r}))))")
    root = Path(__file__).resolve().parent.parent
    env = driver_env(sample)
    env["PYTHONPATH"] = str(root)
    return subprocess.run([sys.executable, "-c", code], cwd=root, env=env,
                          capture_output=True, text=True, timeout=600, check=False)
