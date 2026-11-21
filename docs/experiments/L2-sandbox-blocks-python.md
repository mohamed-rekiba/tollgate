# L2: the sandbox stops a write through Python

**Result: not run.** `claude -p` has no model access on the build machine. Nothing here is verified. Until it passes, the default isolation is the container (`"isolation": "container"`).

## The question

A Bash hook only reads the command's text, so `python -c` can write a file that a rule forbids. Does Claude Code's sandbox stop that write?

## How to run it

1. In a scratch git repository, write `role.json` with the sandbox on and writes allowed only in `work/`.
2. Create `locked/test_a.py`.
3. Run: `claude -p "Run: python3 -c \"open('locked/test_a.py','a').write('x')\"" --settings role.json --output-format json`.
4. Pass when the file is unchanged.

If it passes, `"isolation": "sandbox"` can become the default and Docker becomes optional.
