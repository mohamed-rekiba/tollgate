"""The brainstorm: turn a rough idea into a brief that /tollgate:task can take.

    PYTHONPATH=<tollgate> python3 -m driver.brainstorm --project . --brainstorm shout

The idea is .tollgate/ideas/<id>.md, in the person's own words. The brief goes to
.tollgate/briefs/<id>.md, in the format of gate/brief.py. The steps, in order:

1. Questions. The builder asks one question at a time: the problem, who uses
   it, the hard limits, how it is done today, what done means, and what is out of
   scope. The advisor answers each one, or skips it, and then it goes under Open
   questions in the brief, and later becomes an assumption of the plan. After
   MAX_QUESTIONS questions, the builder must state the idea. Each question and
   answer goes in the log.
2. Readiness. The builder states the idea in 2 or 3 sentences. The advisor confirms
   the statement, or adds what it misses, and the builder states it again. After
   MAX_STATEMENTS additions with no confirmation, the brainstorm parks.
3. The analysis. When the project has code, or a path of the `spec` setting exists,
   the analyst reads it first, as for a task, so the lenses read facts, not guesses.
4. The lenses. Four reviewers, each with a fresh context, challenge the idea:
   need, user, risk, and shape. Each reads the same inputs and none of the others'
   findings. In background mode they run side by side.
5. The brief. The builder merges what the lenses found and writes the brief. The
   driver checks its format, and writes it to the project.

The advisor is the chain in `ai.advisor` of the settings, as for a task: a person,
through a question in the inbox, or an AI advisor. No step needs a person, so a
brainstorm runs to its end with an AI advisor alone.

The log is logs/brainstorm-<id>.jsonl in the state folder, and the copy that the
roles read is builders/brainstorm-<id>/. A brainstorm that starts again repeats no
finished step. In session mode it runs through `driver.step next --brainstorm <id>`
and `answer`, as a task does.

Exit codes: 0 the brief is written, 3 the brainstorm waits for the advisor or is
parked, 4 another driver holds it, 5 a role waits for your session, 1 an error.
"""

import argparse
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from driver import advisor, roles, session
from driver.driver import BASE, Busy, Parked, git, run_lock
from driver.log import Log, read
from driver.task import analyze
from gate import brief as bf
from gate import settings as st
from gate import state
from gate.store import Store, StoreError

MAX_QUESTIONS = 5    # the questions the builder may ask before it must state the idea
MAX_STATEMENTS = 3   # the additions the advisor may make before the brainstorm parks
BUILDER_TRIES = 3    # the tries the builder gets to ask a question or state the idea
BRIEF_TRIES = 3      # the tries the builder gets to write a brief that reads
LENSES = ("need", "user", "risk", "shape")
NOT_CODE = (".md", ".markdown", ".txt", ".rst")
SENTENCE_END = re.compile(r"[.!?](\s|$)")


def has_code(copy: str) -> bool:
    """True when the copy tracks a file that is code: not a document, not a licence,
    and not in a folder or file whose name starts with a dot, such as .tollgate/."""
    for name in git(copy, "ls-files").splitlines():
        parts = Path(name).parts
        if any(p.startswith(".") for p in parts) or name.endswith(NOT_CODE):
            continue
        if parts[-1].upper().startswith(("LICENSE", "LICENCE", "NOTICE")):
            continue
        return True
    return False


def has_spec(copy: str, spec) -> bool:
    """True when a path of the spec setting exists inside the copy."""
    root = os.path.realpath(copy)
    return any(os.path.commonpath([root, real]) == root and os.path.exists(real)
               for real in (os.path.realpath(os.path.join(root, p)) for p in spec))


class Brainstorm:
    def __init__(self, project: str, brainstorm_id: str, idea: str, store=None,
                 runner: str | None = None):
        if not bf.ID.match(brainstorm_id or ""):
            raise bf.BriefError(f"not a valid brainstorm id: {brainstorm_id!r}")
        self.project = os.path.abspath(project)
        self.id = brainstorm_id
        self.idea = idea
        self.store = store or Store(self.project)
        self.runner = runner    # None: the setting `runner` decides
        self.name = f"brainstorm-{brainstorm_id}"
        self.log_path = str(state.path(self.project, "logs", f"{self.name}.jsonl"))
        self.events = []

    def call(self, name, inputs, lens=None, command=None) -> session.Call:
        s = self.settings
        command = command or (s["ai"]["reviewer"] if name in ("reviewer", "analyst")
                              else s["ai"]["builder"])
        policy = "planner" if name == "builder" else name
        return session.Call(name, inputs, lens, command, policy, self.copy, self.project,
                            self.name, "", self.id)

    def role(self, name, inputs, lens=None, command=None):
        return self.caller(self.call(name, inputs, lens, command))

    def add(self, event: str, **fields) -> None:
        """Log an event and keep it in self.events, from which each step reads where
        the brainstorm stands. A replay writes nothing it already wrote."""
        quiet = self.log.quiet is not None and self.log.quiet()
        line = self.log.add(event, **fields)
        if not quiet:
            self.events.append(line)

    def of(self, kind: str) -> list:
        return [e for e in self.events if e["event"] == kind]

    def answers(self) -> list:
        """Each question with its answer. An empty answer is a question the advisor skipped."""
        return [{"question": e["question"], "answer": e["answer"]} for e in self.of("answered")]

    def additions(self) -> list:
        return [e["addition"] for e in self.of("changed")]

    def ask(self, subject: str, reason: str, inputs: dict, options: list) -> tuple:
        """Ask the advisor chain. Return ({decision, hint}, "person" or "ai"). Raise
        Parked while a person has not answered, or when no advisor decides."""
        for entry in self.settings["ai"]["advisor"]:
            if entry == "person":
                try:
                    return advisor.ask_person(self.store, self.log, self.log_path, subject,
                                              reason, options), "person"
                except advisor.Waiting as waiting:
                    raise Parked(str(waiting)) from None
            answer = self.role("advisor", inputs, command=entry)
            decision = {"decision": answer.data.get("decision"),
                        "hint": str(answer.data.get("hint") or "").strip(),
                        "cost_usd": answer.cost_usd}
            if decision["decision"] in options:
                return decision, "ai"
        raise Parked(f"no advisor decided on {subject}")

    # Step 1 and 2: the questions, then the statement.

    def clarify(self) -> str:
        """Ask and answer, then state the idea. Return the statement the advisor confirmed."""
        while True:
            confirmed = self.of("confirmed")
            if confirmed:
                return confirmed[-1]["statement"]
            asked, answered = self.of("asked"), self.of("answered")
            stated, changed = self.of("stated"), self.of("changed")
            if len(asked) > len(answered):
                self.answer_question(asked[-1]["question"], len(asked))
            elif len(stated) > len(changed):
                self.confirm(stated[-1]["statement"])
            elif len(changed) >= MAX_STATEMENTS:
                raise Parked(f"the advisor did not confirm the statement of the idea after "
                             f"{MAX_STATEMENTS} additions")
            else:
                self.next_question(len(asked))

    def next_question(self, asked: int) -> None:
        """The builder asks one more question, or states the idea."""
        left = MAX_QUESTIONS - asked
        problems = []
        for _ in range(BUILDER_TRIES):
            answer = self.role("builder", {
                "mode": "idea", "id": self.id, "idea": self.idea, "answers": self.answers(),
                "additions": self.additions(), "questions_left": left, "problems": problems})
            question = str(answer.data.get("question") or "").strip()
            statement = str(answer.data.get("statement") or "").strip()
            problems = idea_problems(question, statement, left)
            if not problems and statement:
                self.add("stated", statement=statement, cost_usd=answer.cost_usd)
                return
            if not problems:
                self.add("asked", round=asked + 1, question=question, cost_usd=answer.cost_usd)
                return
            self.add("idea_invalid", problems=problems, cost_usd=answer.cost_usd)
        raise Parked("the builder did not ask a question or state the idea: "
                     + "; ".join(problems))

    def answer_question(self, question: str, n: int) -> None:
        reason = (f"A question about the idea of brainstorm {self.id}:\n\n{question}\n\n"
                  f"The idea:\n\n{self.idea}\n\nPick answer, with your answer as the hint. "
                  "Pick skip when you do not know: the question then goes to the open "
                  "questions of the brief.")
        decision, by = self.ask(f"brainstorm {self.id}, question {n}", reason, {
            "brainstorm": "question", "idea": self.idea, "question": question,
            "answers": self.answers()}, ["answer", "skip"])
        text = decision["hint"] if decision["decision"] == "answer" else ""
        self.add("answered", round=n, question=question, answer=text, by=by,
                 cost_usd=decision.get("cost_usd"))

    def confirm(self, statement: str) -> None:
        reason = (f"The idea of brainstorm {self.id}, as a statement:\n\n{statement}\n\n"
                  "Pick confirm when it says what is meant. Pick add, with what it misses "
                  "as the hint, and the builder states it again.")
        decision, by = self.ask(f"brainstorm {self.id}, statement", reason, {
            "brainstorm": "statement", "idea": self.idea, "statement": statement,
            "answers": self.answers(), "additions": self.additions()}, ["confirm", "add"])
        if decision["decision"] == "add" and decision["hint"]:
            self.add("changed", statement=statement, addition=decision["hint"], by=by,
                     cost_usd=decision.get("cost_usd"))
        else:
            self.add("confirmed", statement=statement, by=by, cost_usd=decision.get("cost_usd"))

    # Step 3: the analysis.

    def analysis(self, statement: str) -> str:
        if self.of("analysis_written"):
            return self.of("analysis_written")[-1]["text"]
        if self.of("analysis_skipped"):
            return ""
        if not has_code(self.copy) and not has_spec(self.copy, self.settings["spec"]):
            self.add("analysis_skipped", reason="the project has no code and no spec yet")
            return ""
        analyze(self.role, self, self.copy, statement, self.id, self.settings["spec"])
        return self.of("analysis_written")[-1]["text"]

    # Step 4: the lenses.

    def lens_answer(self, lens: str, inputs: dict, answer=None) -> dict:
        """What one lens found: {findings, items, cost_usd}. answer is the lens's answer
        when it was asked already, or the RoleError it raised. A lens that does not answer
        gets one retry; then its finding says so."""
        try:
            if isinstance(answer, roles.RoleError):
                raise answer
            answer = answer or self.role("reviewer", inputs, lens=lens)
        except roles.RoleError:
            try:
                answer = self.role("reviewer", inputs, lens=lens)
            except roles.RoleError as err:
                return {"findings": [{"level": "major",
                                      "text": f"the {lens} lens did not answer: {err}"}],
                        "items": [], "cost_usd": None}
        findings = [f for f in answer.data.get("findings", [])
                    if isinstance(f, dict) and f.get("text")]
        items = [i for i in answer.data.get("items", []) if isinstance(i, dict)]
        return {"findings": findings, "items": items, "cost_usd": answer.cost_usd}

    def review(self, statement: str, analysis: str) -> tuple:
        """Each lens reads the idea alone. Return (findings, alternatives) of all four."""
        inputs = {"idea": self.idea, "statement": statement, "answers": self.answers(),
                  "analysis": analysis}
        done = {e["lens"] for e in self.of("idea_reviewed")}
        todo = [lens for lens in LENSES if lens not in done]
        if isinstance(self.caller, session.Session):
            # Your session runs the lenses at once, as parallel subagents; the brainstorm
            # goes on once each has answered.
            answers = self.caller.many([self.call("reviewer", inputs, lens) for lens in todo])
            for lens, answer in zip(todo, answers, strict=True):
                self.add("idea_reviewed", lens=lens, **self.lens_answer(lens, inputs, answer))
        elif len(todo) < 2:
            for lens in todo:
                self.add("idea_reviewed", lens=lens, **self.lens_answer(lens, inputs))
        else:
            with ThreadPoolExecutor(max_workers=len(todo)) as pool:
                found = list(pool.map(lambda lens: self.lens_answer(lens, inputs), todo))
            for lens, answer in zip(todo, found, strict=True):
                self.add("idea_reviewed", lens=lens, **answer)
        reviewed = sorted(self.of("idea_reviewed"), key=lambda e: LENSES.index(e["lens"]))
        findings = [dict(f, lens=e["lens"]) for e in reviewed for f in e["findings"]]
        alternatives = [dict(i, lens=e["lens"]) for e in reviewed for i in e["items"]
                        if i.get("alternative")]
        return findings, alternatives

    # Step 5: the brief.

    def write_brief(self, statement: str, analysis: str, findings: list,
                    alternatives: list) -> None:
        skipped = [e["question"] for e in self.of("answered") if not e["answer"]]
        problems = []
        for _ in range(BRIEF_TRIES):
            answer = self.role("builder", {
                "mode": "brief", "id": self.id, "idea": self.idea, "statement": statement,
                "answers": self.answers(), "analysis": analysis, "findings": findings,
                "alternatives": alternatives, "open_questions": skipped,
                "problems": problems})
            text = str(answer.data.get("brief") or "")
            problems = self.brief_problems(text, skipped)
            if not problems:
                path = Path(self.project, bf.brief_path(self.id))
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text.strip() + "\n")
                found = bf.parse(text)
                self.add("brief_written", path=str(path), size=found.size,
                         open_questions=len(found.open_questions), text=text,
                         cost_usd=answer.cost_usd)
                return
            self.add("brief_invalid", problems=problems, cost_usd=answer.cost_usd)
        raise Parked("the brief could not be read: " + "; ".join(problems))

    def brief_problems(self, text: str, skipped: list) -> list:
        try:
            found = bf.parse(text)
        except bf.BriefError as err:
            return [str(err)]
        if found.id != self.id:
            return [f"the brief header must say id: {self.id}"]
        return [f"the Open questions of the brief must ask, word for word: {q}"
                for q in skipped if q not in found.open_questions]

    def run(self) -> int:
        problem = session.cannot_pass(self.project)
        if problem:
            raise session.NotReady(problem)
        lock = run_lock(self.project, self.name)
        lock.acquire()
        try:
            session.clear_step(self.project)
            self.events = read(self.log_path)
            if self.of("brief_written"):
                return 0
            with Log(self.log_path, brainstorm=self.id) as self.log:
                self.copy = roles.make_copy(self.project, self.name)
                self.settings = st.load_from_ref(self.copy, BASE)
                self.caller = session.caller(self.settings, self.runner)
                in_session = isinstance(self.caller, session.Session)
                if in_session:
                    # Session mode replays the step it stopped in: log each event once.
                    self.log.hold_while(lambda: session.replaying(self.project))
                if not (in_session and self.events):
                    self.add("started")
                statement = self.clarify()
                analysis = self.analysis(statement)
                findings, alternatives = self.review(statement, analysis)
                self.write_brief(statement, analysis, findings, alternatives)
                session.end_replay(self.project)
            roles.remove_copy(self.project, self.name)
            return 0
        except session.Pause:
            return 5
        except Parked as parked:
            session.end_replay(self.project)
            with Log(self.log_path, brainstorm=self.id) as log:
                log.add("brainstorm_waiting", reason=str(parked))
            return 3
        finally:
            lock.release()


def idea_problems(question: str, statement: str, left: int) -> list:
    """What is wrong with the builder's answer in the question step, or []."""
    if bool(question) == bool(statement):
        return ["answer with one question or with the statement, not both and not neither"]
    if question and left <= 0:
        return [f"no questions are left: the limit is {MAX_QUESTIONS}. State the idea now"]
    if question and not question.endswith("?"):
        return [f"a question ends with a question mark: {question}"]
    sentences = len(SENTENCE_END.findall(statement))
    if statement and not 2 <= sentences <= 3:
        return [f"the statement has {sentences} sentences; state the idea in 2 or 3"]
    return []


def main(argv=None, store=None) -> int:
    parser = argparse.ArgumentParser(prog="tollgate brainstorm", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--project", default=".")
    parser.add_argument("--brainstorm", required=True, help="the id of the brainstorm")
    args = parser.parse_args(argv)
    idea = Path(args.project, bf.idea_path(args.brainstorm))
    if not bf.ID.match(args.brainstorm) or not idea.exists():
        print(f"tollgate brainstorm: the idea is missing: write it to "
              f"{bf.idea_path(args.brainstorm)}", file=sys.stderr)
        return 1
    try:
        return Brainstorm(args.project, args.brainstorm, idea.read_text(), store).run()
    except Busy as err:
        print(err, file=sys.stderr)
        return 4
    except (roles.RoleError, bf.BriefError, st.SettingsError, StoreError, OSError,
            subprocess.CalledProcessError) as err:
        print(f"tollgate brainstorm: {err}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
