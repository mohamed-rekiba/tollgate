"""The report of a task, and the status of every ticket, read from the logs.

The logs and the reports are in the project's state folder.

    PYTHONPATH=<tollgate> python3 -m driver.report --project .            # status
    PYTHONPATH=<tollgate> python3 -m driver.report --project . --task retries
"""

import argparse
import sys
from pathlib import Path

from driver import history, roles
from driver.log import read
from gate import state


def logs_dir(project: str) -> Path:
    """The logs, in the project's state folder."""
    return state.path(project, "logs")


def ticket_row(events: list) -> dict:
    t = history.replay(events)
    question = history.open_question(events)
    return {"question": question["question"] if question else None, "ticket": t.ticket or "?",
            "state": t.state, "tier": t.tier, "attempts": t.attempts,
            "score": t.best_score if t.best_score >= 0 else None,
            "cost_usd": history.cost(events) if history.cost_known(events) else None, "minutes": history.minutes(events),
            "ready": t.ready or None, "reason": t.reason, "task": t.task}


def usd(cost) -> str:
    """A cost for a person: the number, or "unknown" in session mode."""
    return "unknown" if cost is None else str(cost)


def rows(project: str, task: str | None = None) -> list:
    out = []
    for path in history.logs(logs_dir(project)):
        if path.name.startswith("task-"):
            continue
        events = read(str(path))
        if events and (task is None or events[0].get("task") == task):
            out.append(ticket_row(events))
    return out


def render(project: str, task: str) -> str:
    task_events = read(str(logs_dir(project) / f"task-{task}.jsonl"))
    tickets = rows(project, task)
    all_events = task_events + [e for p in history.logs(logs_dir(project))
                                if not p.name.startswith("task-")
                                for e in read(str(p)) if e.get("task") == task]
    plan_cost = history.cost(task_events) if history.cost_known(task_events) else None
    total = roles.add_cost(plan_cost, *(r["cost_usd"] for r in tickets))
    waiting = still_waiting(task_events)
    pic = ('<picture>\n'
           f'  <source media="(prefers-color-scheme: dark)" srcset="{task}-dark.svg">\n'
           f'  <img alt="Task {task}: where each ticket stands" src="{task}.svg">\n'
           '</picture>')
    lines = [f"# Report: task {task}", "", brief(project, task), "", pic, "", "## Details", "",
             (f"- Cost: {total} USD ({plan_cost} USD for the plan)." if total is not None else
              "- Cost: unknown. Your own Claude Code session ran the roles, so it knows the cost."),
             f"- Time: {history.minutes(all_events)} minutes from the first event to the last.",
             f"- Plan: {'locked' if any(e['event'] == 'plan_locked' for e in task_events) else 'not locked'}.",
             _analysis_line(task_events), ""]
    if waiting:
        lines += [f"The task waits: {waiting[-1]['reason']}", ""]
    lines += ["| Ticket | State | Tier | Tries | Score | Cost USD | Minutes | Ready change | Why |",
              "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for r in tickets:
        lines.append(f"| {r['ticket']} | {r['state']} | {r['tier'] or ''} | {r['attempts']} | "
                     f"{'' if r['score'] is None else r['score']} | {usd(r['cost_usd'])} | {r['minutes']} | "
                     f"{_ready(r)} | {r['reason']} |")
    advisor_events = [e for e in all_events if e["event"] in ("waiting_for_advisor",
                                                              "advisor_decided")]
    asked = sum(1 for e in advisor_events if e["event"] == "waiting_for_advisor")
    decided = sum(1 for e in advisor_events if e["event"] == "advisor_decided")
    lines += ["", f"The advisor was asked {asked} times and decided {decided} times."]
    reviewed = [e for e in task_events if e["event"] == "task_reviewed"]
    if reviewed:
        lines += ["", "## The review of the whole task", "", reviewed[-1]["text"]]
    return "\n".join(lines) + "\n"


def still_waiting(task_events: list) -> list:
    """The task's last task_waiting, while nothing but a new start or a question that
    still waits came after it; [] once the task went on."""
    for i in range(len(task_events) - 1, -1, -1):
        kind = task_events[i]["event"]
        if kind == "task_waiting":
            return [task_events[i]]
        if kind not in ("started", "still_waiting"):
            return []
    return []


def _analysis_line(task_events: list) -> str:
    written = [e for e in task_events if e["event"] == "analysis_written"]
    if not written:
        return "- Analysis: not written."
    missing = written[-1].get("not_found") or []
    return ("- Analysis: written. Every citation was found." if not missing else
            f"- Analysis: written. Not found, so made assumptions: {', '.join(missing)}.")


# How each state looks in the picture: who acts, and the label over the title.
LOOKS = {"merged": ("server", "MERGED", "merge"),
         "ready to merge": ("check", "READY TO MERGE", "pull-request"),
         "building": ("ai", "BUILDING", "ai"), "tests written": ("ai", "TESTS WRITTEN", "test"),
         "frozen": ("server", "TESTS LOCKED", "lock"), "started": ("ai", "STARTED", "ai"),
         "waits for a person": ("advisor", "WAITS FOR YOU", "advisor"),
         "parked": ("advisor", "PARKED", "warning"), "stopped": ("advisor", "STOPPED", "warning"),
         "not started": ("neutral", "NOT STARTED", "ticket")}


def _short(text: str, size: int = 40) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= size else text[:size - 1].rstrip() + "…"


def picture(project: str, task: str) -> dict:
    """A diagram spec of the task: the plan, then one box per ticket, in build order."""
    task_events = read(str(logs_dir(project) / f"task-{task}.jsonl"))
    locked = any(e["event"] == "plan_locked" for e in task_events)
    found = {r["ticket"]: r for r in rows(project, task)}
    order = _planned(project, task)
    order += [t for t in found if t not in order]
    nodes = [{"id": "plan", "text": f"The plan\n{len(order)} tickets", "col": 0, "row": 0,
              "kind": "server" if locked else "ai",
              "tag": "PLAN · LOCKED" if locked else "PLAN · IN REVIEW", "icon": "plan"}]
    counts = {}
    for i, tid in enumerate(order):
        r = found.get(tid) or {"state": "not started", "tier": None, "attempts": 0,
                               "cost_usd": 0, "ready": None, "reason": ""}
        kind, tag, mark = LOOKS.get(r["state"], ("neutral", r["state"].upper(), "ticket"))
        counts[r["state"]] = counts.get(r["state"], 0) + 1
        if r["state"] == "building":
            tag += f" · TRY {r['attempts'] + 1}"
        facts = [f"tier {r['tier']}" if r["tier"] else "", (f"{r['attempts']} tr{'y' if r['attempts'] == 1 else 'ies'}") if r["attempts"]
                 else "", f"{r['cost_usd']} USD" if r["cost_usd"] else ""]
        lines = [tid, " · ".join(f for f in facts if f) or "nothing yet"]
        if r["reason"]:
            lines.append(_short(r["reason"]))
        nodes.append({"id": f"t{i}", "text": "\n".join(lines), "col": i % 3, "row": 1 + i // 3,
                      "kind": kind, "icon": mark, "tag": f"{i + 1} · {tag}"})
    summary = ", ".join(f"{n} {state}" for state, n in counts.items()) or "no tickets yet"
    return {"title": f"Task {task}: where each ticket stands",
            "desc": f"The plan is {'locked' if locked else 'in review'}. "
                    f"{len(order)} tickets, in build order: {summary}.",
            "nodes": nodes, "edges": [],
            "groups": [{"label": "Tickets, in build order", "kind": "neutral", "icon": "ticket",
                        "nodes": [n["id"] for n in nodes[1:]]}] if len(nodes) > 1 else []}


def write(project: str, task: str) -> str:
    """Write the report, and its picture in a light and a dark SVG next to it."""
    from diagram import draw
    path = state.path(project, "reports", f"{task}.md")
    spec = picture(project, task)
    for theme, suffix in (("light", ""), ("dark", "-dark")):
        path.with_name(f"{task}{suffix}.svg").write_text(draw(spec, theme))
    path.write_text(render(project, task))
    return str(path)


def _ready(row: dict) -> str:
    return f"tg/{row['ticket']} at {row['ready'][:12]}" if row["ready"] else ""


def _planned(project: str, task: str) -> list:
    """The ticket ids the task's plan lists, in build order, or [] with no plan.
    The task's log has them once the plan is locked; before that, the plan file
    in the task's copy or in the project."""
    from gate import plan as pl
    locked = [e for e in read(str(logs_dir(project) / f"task-{task}.jsonl"))
              if e["event"] == "plan_locked" and e.get("tickets")]
    if locked:
        return list(locked[-1]["tickets"])
    path = state.path(project, "builders", f"task-{task}", pl.plan_path(task))
    if not path.exists():
        path = Path(project, pl.plan_path(task))
    try:
        return pl.parse(path.read_text()).tickets
    except (OSError, pl.PlanError):
        return []


def _sentence(text: str) -> str:
    text = (text or "").strip()
    return (text[:1].upper() + text[1:] + ("" if text.endswith(".") else ".")) if text else ""


def roadmap_progress(project: str) -> tuple:
    """(done, still_to_do) for each roadmap: its base, its tasks in order, and its end."""
    from gate import roadmap as rm
    done, todo = [], []
    for path in sorted(logs_dir(project).glob("roadmap-*.jsonl")):
        rid = path.name[len("roadmap-"):-len(".jsonl")]
        events = read(str(path))
        kinds = [e["event"] for e in events]
        finished = [e["task"] for e in events if e["event"] == "task_done" and e.get("code") == 0]
        try:
            tasks = rm.parse(Path(project, rm.roadmap_path(rid)).read_text()).tasks
        except (OSError, rm.RoadmapError):
            tasks = None  # the roadmap file is not here: count what the log shows
        name = f"Roadmap {rid}"
        if "base_passed" in kinds:
            done.append(f"{name}: the base passes all five checks.")
        if kinds and kinds[-1] == "roadmap_done":
            what = "its task" if len(set(finished)) == 1 else f"all {len(set(finished))} tasks"
            done.append(f"{name}: done. {what.capitalize()} and the checklist for the whole "
                        f"request pass.")
            continue
        plural = "task" if len(finished) == 1 else "tasks"
        count = (f"{len(finished)} of {len(tasks)} tasks done" if tasks is not None
                 else f"{len(finished)} {plural} done so far")
        if kinds and kinds[-1] == "roadmap_waiting":
            todo.append(f"{name}: stopped, {count}. {_sentence(events[-1].get('reason', ''))}"
                        .strip())
            continue
        following = next(((stage, tid) for stage, tid, _ in tasks or [] if tid not in finished),
                         None)
        now = f" Now: {following[1]} ({following[0].lower()})." if following else ""
        todo.append(f"{name}: {count}.{now}")
    return done, todo


def progress(project: str, task: str | None = None) -> tuple:
    """Return (done, still_to_do): two lists of short sentences for a person."""
    done, todo = roadmap_progress(project) if task is None else ([], [])
    tasks = [task] if task else sorted({r["task"] for r in rows(project) if r["task"]} | {
        p.name[len("task-"):-len(".jsonl")] for p in history.logs(logs_dir(project), "task-*.jsonl")})
    for t in tasks:
        task_events = read(str(logs_dir(project) / f"task-{t}.jsonl"))
        kinds = [e["event"] for e in task_events]
        if "plan_locked" in kinds:
            done.append(f"Plan for {t}: approved and locked.")
        elif task_events:
            asked = history.open_question(task_events)
            if asked:
                todo.append(f"Plan for {t}: waits for your approval in question "
                            f"{asked['question']}.")
            else:
                todo.append(f"Plan for {t}: being written and reviewed.")
        seen = set()
        for r in rows(project, t):
            seen.add(r["ticket"])
            name = r["ticket"]
            if r["state"] == "merged":
                done.append(f"{name}: merged.")
            elif r["state"] == "ready to merge":
                need = (f" It needs your approval: tier {r['tier']}." if r["tier"] in (3, 4)
                        else "")
                todo.append(f"{name}: built, branch tg/{name} waits to merge.{need}")
            elif r["state"] == "waits for a person":
                where = f" in question {r['question']}" if r["question"] else ""
                todo.append(f"{name}: waits for your decision{where}. {_sentence(r['reason'])}".strip())
            elif r["state"] == "parked":
                todo.append(f"{name}: parked. {_sentence(r['reason'])}".strip())
            elif r["state"] == "building":
                todo.append(f"{name}: being built, try {r['attempts'] + 1}.")
            else:
                todo.append(f"{name}: {r['state']}.")
        for tid in _planned(project, t):
            if tid not in seen:
                todo.append(f"{tid}: not started.")
    return done, todo


def brief(project: str, task: str | None = None) -> str:
    """Done and still to do, as two short lists a person reads in seconds."""
    done, todo = progress(project, task)
    lines = ["Done"] + [f"- {d}" for d in done or ["Nothing yet."]]
    lines += ["", "Still to do"] + [f"- {t}" for t in todo or ["Nothing. Everything is done."]]
    return "\n".join(lines)


def status(project: str) -> str:
    found = rows(project)
    if not found:
        return "Tollgate: no tickets have run in this project yet."
    lines = [brief(project), "", "Details", "", "| Task | Ticket | State | Tier | Tries | Score | Cost USD | Minutes | Ready change |",
             "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for r in found:
        lines.append(f"| {r['task']} | {r['ticket']} | {r['state']} | {r['tier'] or ''} | "
                     f"{r['attempts']} | {'' if r['score'] is None else r['score']} | "
                     f"{usd(r['cost_usd'])} | {r['minutes']} | {_ready(r)} |")
    waiting = [r for r in found if r["state"] in ("waits for a person", "parked")]
    if waiting:
        lines += ["", "Waiting for a decision:"] + [f"- {r['ticket']}: {r['reason']}" for r in waiting]
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="tollgate report", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--project", default=".")
    parser.add_argument("--task")
    parser.add_argument("--brief", action="store_true", help="only done and still to do")
    args = parser.parse_args(argv)
    if args.brief:
        print(brief(args.project, args.task))
    elif args.task:
        print(write(args.project, args.task))
    else:
        print(status(args.project))
    return 0


if __name__ == "__main__":
    sys.exit(main())
