# Build contract

This file is for the build only. It is removed before the pull request merges.

## The goal

Tollgate runs on your machine. No product file calls GitHub, `gh`, or any outside service. Two layers enforce the rules: Claude Code hooks and permission policies, and pre-commit. The gate and the signed records are the real checks: they hold even when a role ignores its hooks.

## The 14 rules, in 8 groups

1. Plan first: fresh reviewers check the plan, up to 4 rounds, before code. A large request starts with the base, then one thin path, then one feature at a time. Each ticket has a checklist; a must-have item cannot fail.
2. Tests first: one test for each must-have item, locked before any code. The AI cannot change them.
3. Build from the best try: below 70%, the AI gets the reasons and tries again from its best try so far (the hill-climb loop).
4. The gate judges: a program with no AI checks every try; the AI never grades its own work; score = share of checklist items that pass; 70% passes; a failed must-have fails; only the gate says done.
5. Stop when stuck: after 3 tries, or the same failure twice, the advisor decides (a second AI, or you).
6. Risk sets the checks: tier 1 to 4 from the files a change touches; you merge tiers 3 and 4.
7. Mistakes become rules: at most 3 lessons a task; rules never get looser.
8. Always: code enforces the rules; plain words for people.

## Shared modules (built, do not change their interface)

- `gate/state.py`: `state_dir(project)`, `path(project, kind, *parts)`, `key_dir()`, `dumps(record)`. Kinds: locks, plans, passes, approvals, questions, builders, logs, reports, lessons, run. Tests set `TOLLGATE_STATE` and `TOLLGATE_KEYS`.
- `gate/sign.py`: `ensure_key()`, `sign()`, `verify()`, `write(path, record, namespace)`, `read(path, namespace, signers)`. Namespaces: tollgate-lock, tollgate-plan, tollgate-pass, tollgate-approval. Verify with `signers` from the settings on **main**, never from the change.
- `gate/store.py`: the `Store` class and its method names. The store stream fills the bodies.

## Formats

JSON with sorted keys (`state.dumps`); the signature covers the exact bytes.

- Lock, `locks/<ticket>.json`: `{ticket, base_commit, commit, manifest: {"files": {path: sha256}, "tests": [test ids], "keeps_behavior": [...]}, number, at}`
- Plan lock, `plans/<task>.json`: `{task, commit, files: {path: sha256}, at}`
- Pass, `passes/<commit>.json`: `{commit, ticket, tier, lock_sha256, checks: {name: bool}, score, at}`
- Approval, `approvals/<commit>.json`: `{commit, ticket, approver, at}`, signed with the owner's SSH key, namespace tollgate-approval.
- Question, `questions/<n>.json`: `{n, title, body, options, answer: null | {decision, hint, at}}`

## Settings

Add: `signers` (public key lines), `isolation` ("container" or "sandbox"). Remove: `action`, `version`, `approvers`, `sandbox`, `check_minutes` if unused. Keep the rest.

## Who owns which files

Each stream changes only its own files and their tests. A stream that needs a change in another stream's file writes it down in its report instead.

| Stream | Owns |
| --- | --- |
| 1 Store | `gate/store.py`, `gate/freeze.py`, `gate/prepare.py`, `gate/plantag.py`, `gate/gitio.py`, `tests/fakes.py`, tests for these |
| 2 Gate | `gate/gate.py`, `gate/review.py`, `gate/approval.py`, `gate/checks.py`, `gate/manifest.py`, `gate/tiers.py`, `gate/settings.py`, `gate/server.py` (delete), tests for these |
| 3 Driver | `driver/`, `roles/`, `lenses/` (not `lenses/change.md` Writing section), `hooks/` (new), tests for these |
| 4 Setup | `setup/`, `skills/`, `workflows/` (delete), `.github/workflows/tollgate.yml` (delete), `tests/lint_workflows.sh` (delete), `.claude-plugin/`, `pyproject.toml`, pre-commit templates, tests for these |
| 5 Docs and diagrams (later) | `diagram/`, `docs/`, `README.md`, `CONTEXT.md` |

## Working rules

- Python 3.11, standard library only. Tests use `unittest`, in the style of `tests/test_gate.py`: each rule has a passing and a failing case.
- `python3 -m pytest -q` must pass in your worktree before you finish, except tests another stream owns, which you list.
- Commit in your worktree with `git -c user.name="Mohamed Rekiba" -c user.email="muhammad.shaban.dev@gmail.com" commit`. Subject `type(scope): subject`. No AI attribution lines.
- Never push. Never touch GitHub.
- Write every comment, docstring, and message in the project voice: `lenses/change.md`, section Writing. Lead with the point, short sentences, one word for each thing (`CONTEXT.md`), no filler, no long dash.
- State plainly in code and in your report what is unfinished or untested.
- `claude -p` has no model access on this machine. Use the fake roles in `tests/fakes.py` and `tests/fake_role.py`.
- When the plan does not decide something, pick the smallest choice that keeps the 14 rules, and list it under "Decisions" in your report.
